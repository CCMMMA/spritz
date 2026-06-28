# Spritz didactic use cases

This folder contains executable, step-by-step tutorials. They are intentionally **outside** the `src/sprtz` package and are not installed as suite modules. Each use case imports the production Spritz APIs, but the scenario logic remains here so users can read, copy, adapt, and teach from it without changing the core suite.

## Prerequisites

From the repository root:

```bash
python -m pip install -e .[netcdf,viz]
sprtz doctor --require-netcdf
```

For lightweight tests or classroom demonstrations without WRF data, each relevant script provides a synthetic-data option. For real runs, use the meteo@uniparthenope WRF5 d03 archive URL pattern documented in the use-case folders.

Script-facing date-time values use compact UTC `YYYYMMDDZhhmm` format, for
example `20260601Z0000`. Internal JSON configuration files may still contain
ISO-8601 fields where the Sprtz schema requires them.

All use-case NetCDF products follow the repository's strict NetCDF-CF
convention. Time-dependent NetCDF products must carry a CF `time(time)`
coordinate with absolute UTC units when physical time is known. WRF valid time
comes only from SpritzWRF reading WRF/CF metadata (`Times`, CF `time`, or
explicit global time attributes); use cases must not infer scientific datetimes
from filenames or download paths.

## Data preparation

Use the repository download helpers to prepare shared inputs under `data/`
before running real-area use cases:

```bash
tools/meteouniparthenope-wrf-download.py 20260601Z0000 \
  --hours 24 \
  --domain d03 \
  --data-root data

python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_naples.tif

python3 tools/copernicus-lc100-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/landcover/lc100_naples.tif
```

The WRF downloader prepares NetCDF files for SpritzWRF and SpritzMet. The COP30
downloader prepares a GeoTIFF DEM for `sprtz-terrain fetch`; the LC100
downloader prepares the matching categorical land-cover GeoTIFF. Install
`sprtz[geo]` when using GeoTIFF inputs.

Use-case scripts plot NetCDF intermediate and final products with
`tools/plotter.py` whenever a plottable NetCDF is produced. Generated maps are
written beside the corresponding use-case outputs. See `docs/plotter.md` for
direct plotter commands, Cartopy coastline behavior, and optional dependency
notes.

## Use-case sequence

1. `01_high_resolution_wind_field` — download or read WRF 1 km data, extract near-surface wind with SpritzWRF, and downscale it to a 100 m SpritzMet grid using either center/node-count inputs or a conservatively covered bounding box.
2. `02_wildfire_arson_effects` — build single- or multi-fire arson/wildfire source scenarios using WRF/SpritzMet wind, material presets, source heights, time windows, firefighter actions, and Spritz dispersion.
3. `03_satellite_ai_evaluation` — compare model output with a satellite-derived mask and compute deterministic skill metrics plus a lightweight AI calibration diagnostic.
4. `04_production_incidents` — build catalog-driven production-style incident cases with receptor latitude/longitude and geographic maps.
5. `05_sailing_wind_forecast` — build a high-resolution space-height-time wind forecast product for professional sailing race planning.
6. `06_acerra_waste_to_energy` — run a 12-hour Acerra waste-to-energy chimney screening case starting on 2026-06-01 with a 110 m release height.

Run the step scripts directly:

```bash
python usecases/01_high_resolution_wind_field/step_01_downscale_wind.py --help
python usecases/02_wildfire_arson_effects/step_01_downscale_wind.py --help
python usecases/02_wildfire_arson_effects/step_02_build_config.py --help
python usecases/02_wildfire_arson_effects/step_03_run_model.py --help
python usecases/03_satellite_ai_evaluation/step_02_evaluate.py --help
python usecases/04_production_incidents/step_01_build_config.py --help
python usecases/04_production_incidents/step_02_run_model.py --help
python usecases/05_sailing_wind_forecast/step_01_build_forecast.py --help
python usecases/06_acerra_waste_to_energy/step_01_build_config.py --help
python usecases/06_acerra_waste_to_energy/step_02_run_model.py --help
```

## Repository boundary

Do not import use cases from `sprtz.usecases`; that namespace does not exist. New didactic cases should be added here as folders with a `README.md`, explicit `step_*.py` scripts, and any tiny synthetic helpers needed for automated tests. Large meteorological, satellite, or NetCDF products must not be committed.
