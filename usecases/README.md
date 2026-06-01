# Sprtz didactic use cases

This folder contains executable, step-by-step tutorials. They are intentionally **outside** the `src/sprtz` package and are not installed as suite modules. Each use case imports the production Sprtz APIs, but the scenario logic remains here so users can read, copy, adapt, and teach from it without changing the core suite.

## Prerequisites

From the repository root:

```bash
python -m pip install -e .[netcdf,viz]
sprtz doctor --require-netcdf
```

For lightweight tests or classroom demonstrations without WRF data, each relevant script provides a synthetic-data option. For real runs, use the meteo@uniparthenope WRF5 d03 archive URL pattern documented in the use-case folders.

## Use-case sequence

1. `01_high_resolution_wind_field` — download or read WRF 1 km data, extract near-surface wind with SpritzWRF, and downscale it to 100 m with SpritzMet.
2. `02_wildfire_arson_effects` — build an arson/wildfire source scenario using the WRF/SpritzMet wind field and run Sprtz dispersion.
3. `03_satellite_ai_evaluation` — compare model output with a satellite-derived mask and compute deterministic skill metrics plus a lightweight AI calibration diagnostic.
4. `04_production_incidents` — build catalog-driven production-style incident cases with receptor latitude/longitude and geographic maps.
5. `05_sailing_wind_forecast` — build a high-resolution space-height-time wind forecast product for professional sailing race planning.

Run the scripts directly:

```bash
python usecases/01_high_resolution_wind_field/run.py --help
python usecases/02_wildfire_arson_effects/run.py --help
python usecases/03_satellite_ai_evaluation/run.py --help
python usecases/04_production_incidents/run.py --help
python usecases/05_sailing_wind_forecast/run.py --help
```

## Repository boundary

Do not import use cases from `sprtz.usecases`; that namespace does not exist. New didactic cases should be added here as folders with a `README.md`, a `run.py`, and any tiny synthetic helpers needed for automated tests. Large meteorological, satellite, or NetCDF products must not be committed.
