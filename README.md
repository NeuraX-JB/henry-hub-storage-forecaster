# Henry Hub Storage Forecaster

**John Barreto · Independent natural gas research**

Weather-adjusted U.S. natural gas storage nowcasts, chronological backtests and a timestamped forecast ledger.

**[Open the live project](https://neurax-jb.github.io/Henry-Hub-Futures-Curve-Explorer-How-the-Natural-Gas-Market-prices-winter/lab/storage/) · [Research portfolio](https://neurax-jb.github.io/Henry-Hub-Futures-Curve-Explorer-How-the-Natural-Gas-Market-prices-winter/lab/)**

**Methods and tools:** Python, NumPy, statistical modelling, time-series validation.

## Research question
How much does observed weather improve an estimate of the weekly Lower 48 storage change relative to a five-year seasonal median?

In the 23 November 2026 historical replay, the model reduced mean absolute error from 30.50 Bcf to 20.50 Bcf across 463 common evaluation weeks. The 32.8% reduction is retrospective, based on current-vintage observations, not verified live forecasting performance. No completed live forecasts had been scored at that date.

![Historical model error by year](lab/assets/storage-replay.svg)

## Methods and evidence
- [Rolling regression and seasonal benchmark](lab/storage/model.py)
- [Historical replay](lab/storage/backtest.csv)
- [Forecast ledger](lab/storage/ledger/)
- [Research note](lab/research/storage-weather.md)
- [Shared data provenance](lab/data/README.md)

## Run locally
Serve the root with `python -m http.server 8000` and visit `http://localhost:8000/lab/storage/`. The snapshot contains the files required to display the dashboard. Run the Python model tests on Linux, macOS or WSL with Python 3.11 or later: install NumPy with `python -m pip install numpy`, then run `python -m unittest discover -s lab/storage`. The refresh pipeline uses Unix file-permission operations; use Linux, macOS or WSL when rebuilding it. Rebuilding shared data also requires `xlrd==2.0.2`. The static dashboard can be served on Windows. The official forecast publication and scoring pipeline remains in the [canonical research repository](https://github.com/NeuraX-JB/Henry-Hub-Futures-Curve-Explorer-How-the-Natural-Gas-Market-prices-winter); this project snapshot is not a separate prospective track record.

## Source and publication

This repository is a project-specific snapshot of the [canonical research lab](https://github.com/NeuraX-JB/Henry-Hub-Futures-Curve-Explorer-How-the-Natural-Gas-Market-prices-winter). The live site and automated updates remain there, so the existing website and forecast ledger are preserved. Check the [source and attribution notes](DATA_SOURCES.md) before reusing third-party data. No new license is granted. Research and educational use; not investment advice.
