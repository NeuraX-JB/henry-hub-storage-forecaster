# Data use and attribution

This storage study includes EIA inventories, NOAA observed degree days, and the shared Henry Hub spot snapshot. Its sources are documented below.

| Source | Material | Local evidence |
| --- | --- | --- |
| [U.S. Energy Information Administration](https://www.eia.gov/naturalgas/) | Lower 48 working gas stocks and net stock changes | [Definitions](lab/data/README.md) · [Input manifest](lab/data/manifest.json) |
| [NOAA Climate Prediction Center](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/cdus/degree_days/) | Observed population-weighted CONUS heating and cooling degree days | [Weather definitions](lab/data/README.md) · [Input manifest](lab/data/manifest.json) |
| [EIA Henry Hub spot series](https://www.eia.gov/dnav/ng/hist/rngwhhdd.htm) | Shared daily spot-price observations; not a storage-model feature | [Shared source notes](lab/data/README.md) |

The manifest records retrieval timestamps and SHA-256 hashes. Those timestamps describe the downloaded data vintage, not proof of historical first-release availability. The [research note](lab/research/storage-weather.md) documents that limitation and the frozen evaluation results.

EIA attributes the underlying spot-price series to Refinitiv, an LSEG business. Public access does not automatically permit unrestricted redistribution or commercial reuse. Source terms continue to apply. No repository-wide software or data license is declared, and this document grants no additional rights.
