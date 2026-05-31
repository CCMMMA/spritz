# Use case 02 — Arson or wildfire effects

Goal: create a reproducible screening simulation for an arson/wildfire event at a known latitude and longitude, using WRF 1 km meteorology as wind forcing.

The workflow is intentionally step-by-step:

1. **Choose the event location.** Provide the burning latitude and longitude through `--center-lat` and `--center-lon`.
2. **Acquire meteorology.** Use a local WRF file or download WRF5 d03 from meteo@uniparthenope.
3. **Downscale wind.** Reuse use case 01 logic: SpritzWRF extracts WRF wind and SpritzMet interpolates it to 100 m.
4. **Build source terms.** Convert burning temperature, duration, and area into a documented screening heat-release and PM emission estimate.
5. **Generate receptors.** Create a circular receptor set around the fire location.
6. **Run dispersion.** Execute Sprtz with the Gaussian or particle backend.
7. **Review outputs.** Inspect the generated configuration, concentration product, and postprocessing summary.

## Run with WRF download

```bash
python usecases/02_wildfire_arson_effects/run.py \
  --download-date 2026-05-27 \
  --download-cycle-hour 0 \
  --download-dir data/wrf \
  --output-dir output/wildfire_case \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --temperature-k 1100 \
  --duration-s 3600 \
  --area-m2 2500 \
  --backend particles \
  --interchange netcdf
```

## Run with an existing WRF file

```bash
python usecases/02_wildfire_arson_effects/run.py \
  --wrf data/wrf/wrf5_d03_20260527Z0000.nc \
  --output-dir output/wildfire_case \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --temperature-k 1100
```

## Classroom/demo run

```bash
python usecases/02_wildfire_arson_effects/run.py \
  --allow-synthetic-wrf \
  --interchange json \
  --backend gaussian \
  --output-dir output/demo_wildfire \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --temperature-k 1000 \
  --duration-s 600 \
  --area-m2 500
```

## Expected products

- `wrf_100m_wind.nc` or `.json` — the local meteorological forcing product.
- `wildfire_event.json` — the generated Sprtz configuration.
- `model/meteo.*` — suite meteorology exchange file.
- `model/concentration.*` — dispersion output.
- `model/post.json` — postprocessed statistics.

## Scientific caution

This is a screening and teaching workflow, not a certified fire-emission inventory. Operational use requires validated fuel loading, combustion phase, plume-injection height, satellite constraints, and independent model evaluation.
