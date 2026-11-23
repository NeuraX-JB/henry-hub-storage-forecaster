"use strict";
const byId = id => document.getElementById(id);
const text = (id, value) => { byId(id).textContent = value; };
const format = (value, decimals = 0) => Number(value).toLocaleString("en-US", {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
const sign = (value, digits = 0) => (Math.abs(value) < 0.5 / 10 ** digits ? "" : value < 0 ? "−" : "+") + format(Math.abs(value), digits);
function day(iso, options = {month: "short", day: "numeric", year: "numeric"}) {
  return new Intl.DateTimeFormat("en-US", {...options, timeZone: "UTC"}).format(new Date(iso + "T12:00:00Z"));
}
function moment(iso) {
  return new Intl.DateTimeFormat("en-US", {timeZone: "America/New_York", month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"}).format(new Date(iso));
}
function el(type, value, cls) {
  const elem = document.createElement(type);
  if (value !== undefined) elem.textContent = value;
  if (cls) elem.className = cls;
  return elem;
}
function item(container, name, value) {
  const row = el("div", undefined, "components-row");
  row.append(el("span", name), el("strong", value));
  byId(container).append(row);
}
function score(id, values) {
  for (const [label, value] of [["Model MAE", values.mae], ["Baseline MAE", values.baseline_mae], ["Scored weeks", values.n]]) {
    const cell = el("div");
    cell.append(el("strong", value == null ? "—" : format(value, label === "Scored weeks" ? 0 : 1)), el("span", label));
    byId(id).append(cell);
  }
}
function forecast(s) {
  const d = s.current;
  const passed = Date.now() >= Date.parse(s.scheduled);
  text("target", day(s.target));
  text("due", moment(s.scheduled));
  text("latest", "Last EIA report · " + day(s.last_report.week) + " · " + format(s.last_report.stock) + " Bcf in storage (" + sign(s.last_report.change) + " Bcf week over week).");
  if (!d) {
    text("status", passed ? "Release time passed" : "Awaiting weather");
    text("direction", "Five-year seasonal baseline");
    text("number", s.seasonal_only == null ? "—" : sign(s.seasonal_only));
    if (s.seasonal_only != null) byId("number").append(el("small", "Bcf"));
    text("range", passed ? "The scheduled release time has passed for this snapshot. See the EIA release for the latest report." : "The model needs seven observed weather days before it can issue a forecast and interval.");
    text("issue", "Pending");
    text("exposure", "Complete weather is available through the storage week ending " + day(s.weather_through) + ".");
    return;
  }
  text("status", passed ? "Release time passed" : "Recorded before release");
  text("direction", d.forecast < 0 ? "Estimated withdrawal" : d.forecast > 0 ? "Estimated injection" : "Estimated change");
  text("number", format(Math.abs(d.forecast), 1));
  byId("number").append(el("small", "Bcf"));
  text("range", "80% range for net change · " + sign(d.low, 1) + " to " + sign(d.high, 1) + " Bcf");
  text("issue", moment(d.issued_at));
  byId("issue").title = d.issued_at;
  byId("due").title = s.scheduled;
  item("components", "Five-year seasonal baseline", sign(d.baseline, 1) + " Bcf");
  item("components", "Heating adjustment", sign(d.heating_effect, 1) + " Bcf");
  item("components", "Cooling adjustment", sign(d.cooling_effect, 1) + " Bcf");
  item("components", "Fitted intercept", sign(d.intercept, 1) + " Bcf");
  text("exposure", day(d.weather_start, {month: "short", day: "numeric"}) + "–" + day(d.weather_end) + " · " + format(d.hdd) + " heating degree days versus " + format(d.typical_hdd) + " seasonally. Cooling totaled " + format(d.cdd) + " versus " + format(d.typical_cdd) + ".");
}
function ledgerTable(s) {
  const table = byId("ledger");
  if (!s.ledger.length) {
    const r = el("tr"), td = el("td", "No estimates have been recorded.");
    td.colSpan = 5; r.append(td); table.append(r); return;
  }
  for (const row of s.ledger) {
    const tr = el("tr"), week = el("td"), anchor = el("a", day(row.week));
    anchor.href = "ledger/" + row.week + ".json"; week.append(anchor);
    const status = el("td", undefined, "ledger-status");
    if (row.publication) {
      const proof = el("a","Publication evidence");
      proof.href = "ledger/" + row.week + "-publication.json";
      status.append(proof);
    } else if (row.actual != null) status.textContent = "Awaiting publication evidence";
    else if (row.week <= s.last_report.week) status.textContent = "Release vintage unavailable";
    else status.textContent = Date.now() >= Date.parse(row.scheduled_release) ? "Awaiting report capture" : "Awaiting EIA";
    const actual = el("td", "—");
    if (row.actual != null) {
      const release = el("a", sign(row.actual) + " Bcf"); release.href = row.raw_file;
      actual.replaceChildren(release);
    }
    tr.append(week, el("td", sign(row.forecast, 1)), el("td", sign(row.baseline, 1)), actual, status);
    table.append(tr);
  }
}
function historyTable(rows) {
  const body = byId("history-body");
  body.replaceChildren();
  for (const row of [...rows].reverse()) {
    const tr = el("tr");
    const labels = [day(row.week), sign(row.actual), sign(row.forecast, 1), sign(row.baseline, 1), sign(row.low, 1) + " to " + sign(row.high, 1)];
    tr.append(...labels.map(label => el("td", label)));
    body.append(tr);
  }
}
function chart(rows) {
  const graph = byId("chart"), ns = "http://www.w3.org/2000/svg";
  const width = Math.max(276, graph.clientWidth), height = graph.clientHeight || 225;
  const left = 40, right = width-10, top = 15, bottom = height-30;
  graph.setAttribute("viewBox", "0 0 " + width + " " + height);
  graph.replaceChildren();
  function svg(name, attributes, value) {
    const node = document.createElementNS(ns, name);
    for (const [key, val] of Object.entries(attributes)) node.setAttribute(key, val);
    if (value !== undefined) node.textContent = value;
    graph.append(node);
    return node;
  }
  const vals = rows.flatMap(r => [r.forecast, r.baseline, r.actual]);
  const min = Math.min(0, ...vals), max = Math.max(0, ...vals);
  const ideal = Math.max((max - min) / 5, 1), order = 10 ** Math.floor(Math.log10(ideal));
  const step = [1, 2, 2.5, 5, 10].map(x => x * order).find(x => x >= ideal);
  const lo = Math.floor(min / step) * step, hi = Math.max(lo + step, Math.ceil(max / step) * step);
  const y = v => bottom - (v-lo) / (hi-lo) * (bottom-top);
  const x = i => left + i / Math.max(1,rows.length-1) * (right-left);
  for (let v=lo; v<=hi; v+=step) {
    svg("line",{x1:left,y1:y(v),x2:right,y2:y(v),stroke:v===0 ? "#829686" : "#e1e8df","stroke-width":v===0 ? 1.5 : 1});
    svg("text",{x:left-6,y:y(v)+4,"text-anchor":"end",fill:"#53665b","font-size":11},sign(v));
  }
  const labels = width < 460 ? 3 : 6;
  for (let j=0; j<labels; j++) {
    const i = Math.round(j*(rows.length-1)/(labels-1));
    svg("text",{x:x(i),y:bottom+19,"text-anchor":j===labels-1 ? "end" : j===0 ? "start" : "middle",fill:"#53665b","font-size":11},day(rows[i].week,{month:"short",day:"numeric"}));
  }
  for (const [key,color,dash] of [["baseline","#ad6138","6 4"],["forecast","#007968",""],["actual","#203d35",""]]) {
    svg("polyline",{points:rows.map((r,i) => x(i).toFixed(2)+","+y(r[key]).toFixed(2)).join(" "),fill:"none",stroke:color,
      "stroke-width":key==="actual" ? 2.5 : 2,"stroke-dasharray":dash,"stroke-linejoin":"round"});
  }
}
function render(s) {
  forecast(s); ledgerTable(s);
  score("live-scores", s.live_score); score("back-scores", s.backtest);
  text("live-info", s.live_score.n ? "Only forecasts with verified public delivery before the EIA release enter this score." : "No scored public releases yet. The ledger records when each estimate was frozen.");
  text("back-info", day(s.backtest.first) + " – " + day(s.backtest.last) + ". The 80% interval contained " + format(s.backtest.coverage*100,1) + "% of actual changes.");
  byId("app").hidden = false; byId("load").hidden = true;
  let selected;
  function updateHistory() {selected = s.recent.slice(-Number(byId("weeks").value)); chart(selected); historyTable(selected);}
  byId("weeks").addEventListener("change", updateHistory);
  updateHistory();
  if (typeof ResizeObserver === "function") new ResizeObserver(() => chart(selected)).observe(byId("chart"));
  else window.addEventListener("resize", () => chart(selected));
}
fetch("state.json",{cache:"no-cache"}).then(response => {
  if (!response.ok) throw new Error("Could not load forecast data");
  return response.json();
}).then(render).catch(() => {
  byId("load").textContent = "The forecast archive could not be loaded. ";
  const a=el("a","Download the historical CSV"); a.href="backtest.csv"; byId("load").append(a);
});
