"""Weather-adjusted Lower 48 storage nowcast, with chronological replay."""
from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil, isfinite
from statistics import mean, median
import numpy as np

WEEK = timedelta(days=7)
MIN_TRAIN = 104
MAX_TRAIN = 156
MIN_INTERVAL = 52
MAX_INTERVAL = 104


@dataclass(frozen=True)
class Feature:
    week: date
    baseline: float
    hdd: float
    cdd: float
    typical_hdd: float
    typical_cdd: float

    @property
    def x(self):
        return [1.0, self.hdd - self.typical_hdd, self.cdd - self.typical_cdd]


def analog_week(target, years):
    """Friday closest to target's month and day, in each previous year."""
    try:
        anniversary = target.replace(year=target.year - years)
    except ValueError:
        anniversary = date(target.year - years, 2, 28)
    offset = ((4 - anniversary.weekday() + 3) % 7) - 3
    return anniversary + timedelta(days=offset)


def feature(target, actuals, weather):
    analogs = [analog_week(target, i) for i in range(1, 6)]
    if target not in weather or any(w not in actuals or w not in weather for w in analogs):
        return None
    return Feature(target, median(actuals[w] for w in analogs), *weather[target],
                   median(weather[w][0] for w in analogs),
                   median(weather[w][1] for w in analogs))


def predict(row, examples, previous_errors):
    if len(examples) < MIN_TRAIN:
        return None
    train = examples[-MAX_TRAIN:]
    weeks = [sample.week for sample, _ in train]
    if weeks != sorted(set(weeks)) or any(week >= row.week for week in weeks):
        raise ValueError("Training weeks must be distinct, chronological and precede the target.")
    values = [*row.x, row.baseline]
    for sample, actual in train:
        values.extend([*sample.x, sample.baseline, actual])
    if not all(isfinite(value) for value in values):
        raise ValueError("Model inputs must be finite numbers.")
    if any(not isfinite(error) or error < 0 for error in previous_errors):
        raise ValueError("Calibration errors must be finite, nonnegative absolute errors.")
    matrix = np.array([sample.x for sample, _ in train])
    response = np.array([actual - sample.baseline for sample, actual in train])
    intercept, hdd_beta, cdd_beta = np.linalg.lstsq(matrix, response, rcond=None)[0]
    heat = hdd_beta * row.x[1]
    cool = cdd_beta * row.x[2]
    estimate = row.baseline + intercept + heat + cool
    err = sorted(previous_errors[-MAX_INTERVAL:])
    radius = None
    if len(err) >= MIN_INTERVAL:
        radius = err[min(len(err) - 1, ceil(0.8 * (len(err) + 1)) - 1)]
    stats = {"forecast": float(estimate), "baseline": float(row.baseline),
             "hdd": row.hdd, "cdd": row.cdd, "typical_hdd": row.typical_hdd,
             "typical_cdd": row.typical_cdd, "heating_effect": float(heat),
             "cooling_effect": float(cool), "intercept": float(intercept),
             "hdd_beta": float(hdd_beta), "cdd_beta": float(cdd_beta),
             "train_n": len(train), "train_from": train[0][0].week.isoformat(),
             "train_through": train[-1][0].week.isoformat(), "interval_n": len(err),
             "low": None if radius is None else float(estimate - radius),
             "high": None if radius is None else float(estimate + radius)}
    if not all(isfinite(stats[k]) for k in ["forecast", "hdd_beta", "cdd_beta"]):
        raise ValueError("Invalid fitted model.")
    return stats


def walk_forward(actuals, weather, next_target):
    examples, errors, replay = [], [], []
    for week in sorted(actuals):
        if week >= next_target:
            continue
        row = feature(week, actuals, weather)
        if row is None:
            continue
        forecast = predict(row, examples, errors)
        actual = actuals[week]
        if forecast:
            errors.append(abs(actual - forecast["forecast"]))
            if forecast["low"] is not None:
                replay.append({"week": week.isoformat(), "actual": actual, **forecast})
        examples.append((row, actual))
    future = feature(next_target, actuals, weather)
    return replay, predict(future, examples, errors) if future else None


def performance(rows):
    if not rows:
        return {"n": 0, "mae": None, "baseline_mae": None, "coverage": None}
    return {"n": len(rows), "mae": mean(abs(r["forecast"] - r["actual"]) for r in rows),
            "baseline_mae": mean(abs(r["baseline"] - r["actual"]) for r in rows),
            "coverage": mean(r["low"] <= r["actual"] <= r["high"] for r in rows)}
