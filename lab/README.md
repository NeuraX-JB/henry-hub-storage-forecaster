# Reproduce the storage scorecard

The archived dashboard and the research note use the same weekly comparisons. Each row of [backtest.csv](storage/backtest.csv) contains a Friday date, an observed stock change (`actual`), two estimates (`forecast` and `baseline`) and the weather model’s interval (`low`, `high`). These five numeric fields are in billion cubic feet.

## Recalculate the scorecard

From the repository root, run this in a Python session. It reads the frozen CSV using only the standard library.

```python
import csv
from statistics import mean

with open("lab/storage/backtest.csv", newline="") as replay:
    weeks = list(csv.DictReader(replay))

def errors(column):
    return [abs(float(row[column]) - float(row["actual"])) for row in weeks]

model = errors("forecast")
seasonal = errors("baseline")
closer = sum(m < s for m, s in zip(model, seasonal))
covered = sum(float(r["low"]) <= float(r["actual"]) <= float(r["high"]) for r in weeks)
print(f"{len(weeks)} weeks, {weeks[0]['week']} through {weeks[-1]['week']}")
print(f"Mean absolute miss: model {mean(model):.2f} Bcf, seasonal {mean(seasonal):.2f} Bcf")
print(f"Model closer: {closer}/{len(weeks)}. Interval coverage: {covered / len(weeks):.1%}")
```

For the 23 November 2026 snapshot, this returns **463 weeks**, average misses of **20.50 and 30.50 Bcf**, **266** closer weather estimates and **78.2%** interval coverage. The [forecast ledger](storage/ledger/) holds estimates recorded before a scheduled report. The [snapshot state](storage/state.json) gives their scoring status separately.

[Research note](research/storage-weather.md) · [Run the repository checks](../VALIDATION.md) · [Original full-lab rebuild instructions](https://github.com/NeuraX-JB/Henry-Hub-Futures-Curve-Explorer-How-the-Natural-Gas-Market-prices-winter/blob/80c2e5321dadc95aadd4c7f65792fb15f0e2f156/lab/README.md) · [Project overview](../README.md)
