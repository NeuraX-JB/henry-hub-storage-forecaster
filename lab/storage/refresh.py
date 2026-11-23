"""Refresh a release-locked, versioned Lower 48 storage forecast. Python 3.11+, numpy."""
import csv
import hashlib
import io
import json
import os
import re
import tempfile
import time
from datetime import date, datetime, time as clock, timedelta, timezone
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo
from statistics import median
from model import WEEK, analog_week, walk_forward, performance

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
LEDGER = HERE / "ledger"
EASTERN = ZoneInfo("America/New_York")
RELEASE = "https://ir.eia.gov/ngs/wngsr.csv"
SCHEDULE = "https://ir.eia.gov/ngs/schedule.html"
REPO = os.environ.get("GITHUB_REPOSITORY", "NeuraX-JB/Henry-Hub-Futures-Curve-Explorer-How-the-Natural-Gas-Market-prices-winter")
PUBLIC_DIR = os.environ.get("STORAGE_LEDGER_PATH", "lab/storage/ledger")
MODEL = "seasonal-median-observed-weather-v1"


def timestamp(value):
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read_url(url, attempts=3):
    headers = {"User-Agent": "HenryHubResearch-public-data/1.0", "Accept": "*/*"}
    for n in range(attempts):
        try:
            with urlopen(Request(url, headers=headers), timeout=25) as response:
                return response.read()
        except HTTPError as err:
            if err.code < 500 and err.code != 429 or n == attempts - 1:
                raise
        except OSError:
            if n == attempts - 1:
                raise
        time.sleep(1 + n)


def atomic_write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == body:
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as fh:
        fh.write(body)
        os.fchmod(fh.fileno(), 0o644)
        temp = fh.name
    os.replace(temp, path)


def save_once(path, body):
    """A hard link publishes the whole record atomically without replacing it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as fh:
        fh.write(body)
        os.fchmod(fh.fileno(), 0o644)
        temp = fh.name
    try:
        os.link(temp, path)
    except FileExistsError:
        pass
    finally:
        os.unlink(temp)


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def clean_numbers(obj):
    return {k: round(v, 4) if isinstance(v, float) else v for k, v in obj.items()}


def parse_report(raw):
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    text = "\n".join(r[0] for r in rows[:5] if r)
    stamp = re.search(r"Released:\s*(\w+ \d+, \d{4}) at (\d{1,2}:\d{2})\s*([ap])\.?m", text, re.I)
    ending = re.search(r"Week Ending (\w+ \d+, \d{4})", text, re.I)
    release = re.search(r"Next Release:\s*(\w+ \d+, \d{4})", text, re.I)
    if not stamp or not ending or not release:
        raise ValueError("EIA release header could not be validated.")
    parsed_date = lambda value: datetime.strptime(value.strip(), "%B %d, %Y").date()
    issued = datetime.combine(parsed_date(stamp[1]), datetime.strptime(stamp[2] + stamp[3].upper() + "M", "%I:%M%p").time(), EASTERN)
    header = next(r for r in rows if any("net change" in v.lower() for v in r))
    flow_idx = next(i for i, cell in enumerate(header) if "net change" in cell.lower())
    total = next(r for r in rows if r and r[0].strip().lower() == "total")
    num = lambda idx: float(total[idx].replace(",", "").strip())
    now, prev, change = num(1), num(4), num(flow_idx)
    if abs(now-prev-change) > 1:
        raise ValueError("EIA stocks and reported change disagree.")
    return {"week": parsed_date(ending[1]), "issued": issued, "next_date": parsed_date(release[1]),
            "change": change, "stock": now, "previous_stock": prev}


def deadline(next_date, markup):
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", markup, re.I | re.S):
        cells = [unescape(re.sub(r"<[^>]+>", "", val)).strip() for val in re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.I | re.S)]
        if len(cells) < 3:
            continue
        if next_date.strftime("%B %d, %Y").replace(" 0", " ") not in cells[0]:
            continue
        tm = re.search(r"(\d{1,2}:\d\d)\s*([ap])\.?m", cells[2], re.I)
        if tm:
            return datetime.combine(next_date, datetime.strptime(tm[1] + tm[2].upper() + "M", "%I:%M%p").time(), EASTERN)
    if next_date.weekday() == 3 and "10:30" in markup and "Thursday" in markup:
        return datetime.combine(next_date, clock(10, 30), EASTERN)
    raise ValueError("Cannot verify EIA's next release time from its schedule.")


def load_shared():
    with (DATA / "storage.csv").open() as fh:
        stocks, changes = {}, {}
        for r in csv.DictReader(fh):
            k = date.fromisoformat(r["week_ending"])
            if k in stocks or k.weekday() != 4:
                raise ValueError("Invalid or duplicate storage week.")
            stocks[k] = float(r["working_gas_bcf"])
            if r["change_bcf"].strip():
                changes[k] = float(r["change_bcf"])
    with (DATA / "weather.csv").open() as fh:
        weather = {}
        for r in csv.DictReader(fh):
            k = date.fromisoformat(r["week_ending"])
            if k in weather or k.weekday() != 4 or not r["hdd"].strip() or not r["cdd"].strip():
                raise ValueError("Invalid or duplicate weather week.")
            if "period_start" in r and r["period_start"] != (k-WEEK).isoformat():
                raise ValueError("Weather start must be the previous Friday.")
            if "period_end" in r and r["period_end"] != (k-timedelta(days=1)).isoformat():
                raise ValueError("Weather end must be Thursday.")
            weather[k] = (float(r["hdd"]), float(r["cdd"]))
    return stocks, changes, weather


def reconcile_report(stocks, changes, report):
    """The weekly bulletin can reach EIA's archive before the historical XLS."""
    end = report["week"]
    latest = max(stocks)
    if latest == end and abs(stocks[end] - report["stock"]) <= 1:
        return
    if latest == end - WEEK and abs(stocks[latest] - report["previous_stock"]) <= 1:
        stocks[end] = report["stock"]
        changes[end] = report["change"]
        return
    raise ValueError("EIA history and current headline are out of sync. Refresh shared data first.")


def eligible(target, cut, downloaded_at, stocks, history_end, weather_ready):
    return (weather_ready and target == history_end + WEEK and max(stocks) == history_end
            and downloaded_at >= datetime.combine(target, clock(9), ZoneInfo("America/Chicago"))
            and downloaded_at < cut)


def verified_publication(issue_file, issue, actual_release):
    """Find an actual public Pages deploy that contained this exact frozen record."""
    issue_at = parse_stamp(issue["issued_at"])
    before = min(parse_stamp(issue["scheduled_release"]), actual_release)
    if issue_at >= before:
        return None
    root = "https://api.github.com/repos/" + REPO
    try:
        # Usually 1-10 deployments between the issued forecast and the EIA report.
        # Page back if the run is rebuilding an older proof.
        for page in range(1, 21):
            deps = json.loads(read_url(f"{root}/deployments?environment=github-pages&per_page=100&page={page}", 1))
            if not deps:
                break
            for dep in deps:
                if parse_stamp(dep["created_at"]) > before:
                    continue
                if parse_stamp(dep["created_at"]) + timedelta(days=1) < issue_at:
                    return None
                sha = dep["sha"]
                statuses = json.loads(read_url(dep["statuses_url"], 1))
                for st in statuses:
                    when = parse_stamp(st["created_at"])
                    if st["state"] != "success" or not issue_at <= when < before:
                        continue
                    raw = f"https://raw.githubusercontent.com/{REPO}/{sha}/{PUBLIC_DIR}/{issue_file.name}"
                    try:
                        content = read_url(raw, 1)
                    except HTTPError as err:
                        if err.code == 404:
                            continue
                        raise
                    if content == issue_file.read_bytes():
                        return {"deployment_id": dep["id"], "published_at": timestamp(when), "commit": sha, "source": raw}
            if len(deps) < 100:
                break
    except (OSError, ValueError, KeyError) as err:
        print("Publication verification deferred:", str(err)[:160])
    return None


def run():
    # Fetch the headline first. The issue timestamp below is taken after the inputs are loaded.
    report_bytes = read_url(RELEASE)
    report = parse_report(report_bytes)
    cut = deadline(report["next_date"], read_url(SCHEDULE).decode("utf-8", "replace"))
    stocks, changes, weather = load_shared()
    target = report["week"] + WEEK
    today = datetime.now(timezone.utc)
    if report["issued"] > today:
        raise ValueError("A release in the future cannot be used.")
    reconcile_report(stocks, changes, report)
    replay, forecast = walk_forward(changes, weather, target)
    if not replay:
        raise ValueError("Insufficient complete historical observations.")
    LEDGER.mkdir(parents=True, exist_ok=True)
    report_key = report["week"].isoformat()
    captured = LEDGER / (report_key + "-release.json")
    if (LEDGER / (report_key + ".json")).exists() and not captured.exists():
        csv_path = LEDGER / (report_key + "-release.csv")
        save_once(csv_path, report_bytes)
        actual = parse_report(csv_path.read_bytes())
        if actual["week"] != report["week"]:
            raise ValueError("Stored release week mismatch.")
        save_once(captured, json_bytes({"week": report_key, "actual": actual["change"], "reported_at": timestamp(actual["issued"]),
                                       "captured_at": timestamp(today), "raw_file": "ledger/" + csv_path.name,
                                       "source_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest()}))
    issue_file = LEDGER / (target.isoformat() + ".json")
    issue_at = datetime.now(timezone.utc)
    if not issue_file.exists() and forecast is not None and forecast["low"] is not None and eligible(target, cut, issue_at, stocks, report["week"], target in weather):
        save_once(issue_file, json_bytes({"week": target.isoformat(), "issued_at": timestamp(issue_at), "scheduled_release": timestamp(cut),
                                          "weather_start": (target-WEEK).isoformat(), "weather_end": (target-timedelta(days=1)).isoformat(),
                                          "last_report_week": report_key, "last_report_release": timestamp(report["issued"]),
                                          "data_sha256": {name: hashlib.sha256((DATA / name).read_bytes()).hexdigest() for name in ["storage.csv","weather.csv"]},
                                          "report_sha256": hashlib.sha256(report_bytes).hexdigest(), "model": MODEL, **clean_numbers(forecast)}))
    history, scored = [], []
    for f in sorted(LEDGER.glob("????-??-??.json"), reverse=True):
        issue = json.loads(f.read_text())
        if f.stem != issue["week"]:
            raise ValueError("Invalid forecast record name.")
        row = {**issue, "actual": None, "publication": None}
        outcome_path = LEDGER / (f.stem + "-release.json")
        proof_path = LEDGER / (f.stem + "-publication.json")
        if outcome_path.exists():
            act = json.loads(outcome_path.read_text())
            row.update(act)
            if not proof_path.exists():
                proof = verified_publication(f, issue, parse_stamp(act["reported_at"]))
                if proof:
                    save_once(proof_path, json_bytes(proof))
            if proof_path.exists():
                row["publication"] = json.loads(proof_path.read_text())
                scored.append(row)
        history.append(row)
    fields = ["week", "forecast", "baseline", "actual", "low", "high", "hdd", "cdd", "heating_effect", "cooling_effect", "intercept"]
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(clean_numbers(r) for r in replay)
    atomic_write(HERE / "backtest.csv", out.getvalue().encode())
    seasonal = None
    analogs = [analog_week(target, i) for i in range(1,6)]
    if all(w in changes for w in analogs):
        seasonal = median(changes[w] for w in analogs)
    current = next((r for r in history if r["week"] == target.isoformat()), None)
    snapshot = {"as_of": timestamp(today), "model": MODEL, "target": target.isoformat(), "scheduled": timestamp(cut),
                "last_report": {"week": report_key, "at": timestamp(report["issued"]), "change": report["change"], "stock": report["stock"]},
                "current": current, "seasonal_only": seasonal, "ledger": history, "live_score": performance(scored),
                "backtest": {"first": replay[0]["week"], "last": replay[-1]["week"], **performance(replay)},
                "weather_through": max(weather).isoformat(), "recent": [{k:clean_numbers(r)[k] for k in fields} for r in replay[-52:]]}
    atomic_write(HERE / "state.json", json_bytes(snapshot))
    print("Forecast week", target, "recorded", current is not None, "backtest", snapshot["backtest"])


if __name__ == "__main__":
    run()
