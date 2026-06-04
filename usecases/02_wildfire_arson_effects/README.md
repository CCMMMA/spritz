# Use case 02 — Arson or wildfire effects

Goal: create a reproducible screening simulation for an arson/wildfire event at a known latitude and longitude, using WRF 1 km meteorology as wind forcing.

The workflow is intentionally step-by-step:

1. **Choose the event location.** Provide the burning latitude and longitude through `--center-lat` and `--center-lon`.
2. **Acquire meteorology.** Use a local WRF file or download WRF5 d03 from meteo@uniparthenope.
3. **Downscale wind.** Reuse use case 01 logic: SpritzWRF extracts WRF wind and SpritzMet interpolates it to 100 m.
4. **Build source terms.** Convert burning material, optional burning temperature, duration, source height, and area into a documented screening heat-release and PM emission estimate.
5. **Generate receptors.** Create a circular receptor set around the fire location.
6. **Run dispersion.** Execute Spritz with the configured Gaussian or particle backend.
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
  --material plastic \
  --start 2026-05-27T00:00:00+00:00 \
  --end 2026-05-27T01:00:00+00:00 \
  --duration-s 3600 \
  --area-m2 2500 \
  --precipitation-washout \
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
  --material paper \
  --height-agl-m 3
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
  --material generic \
  --duration-s 600 \
  --area-m2 500
```

## Event timing, materials, and source height

Use these options to express the run timing requested in the generated JSON:

- `--weather-start` and `--weather-end`: weather simulation start/end datetimes.
- `--start` and `--end`: fire/arson event start/end datetimes.
- `--firefighters-start`, `--firefighters-end`, and
  `--firefighters-emission-factor`: suppression period and emission multiplier.
- `--height-agl-m`: release height above local ground level, useful for small
  stacks or chimney-style sources.
- `--material`: one of `generic`, `paper`, or `plastic`.
- `--temperature-k`: optional override for the selected material preset.
- `--precipitation-washout`: use WRF/SpritzMet `precipitation_rate` as an
  additional wet-removal term.

The generated source records include `material`, `height_agl_m`,
`start_datetime`, and `end_datetime`. Run-level weather, event, firefighter, and
washout settings are written under `run`. The WRF-derived center-cell
`precipitation_rate` is preserved in the generated station record and in
`run.default_precipitation_rate` so the suite run can apply washout without
requiring a separate meteorology file.

## Multi-fire event JSON

For multiple fires, pass a JSON list to `--fire-events-json`. Each event can
set `id`, `latitude`, `longitude`, `height_agl_m`, `start_datetime`,
`end_datetime`, `material`, `area_m2`, `temperature_k`, and
`emission_factor_g_m2`.

```bash
python usecases/02_wildfire_arson_effects/run.py \
  --allow-synthetic-wrf \
  --interchange json \
  --output-dir output/multi_fire \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --weather-start 2026-06-01T00:00:00+00:00 \
  --weather-end 2026-06-01T04:00:00+00:00 \
  --firefighters-start 2026-06-01T02:00:00+00:00 \
  --firefighters-end 2026-06-01T03:00:00+00:00 \
  --firefighters-emission-factor 0.4 \
  --fire-events-json '[{"id":"F1","latitude":40.8500,"longitude":14.2700,"material":"paper","start_datetime":"2026-06-01T00:00:00+00:00","end_datetime":"2026-06-01T03:00:00+00:00"},{"id":"F2","latitude":40.8550,"longitude":14.2750,"height_agl_m":2.0,"material":"plastic","start_datetime":"2026-06-01T01:00:00+00:00","end_datetime":"2026-06-01T04:00:00+00:00"}]'
```

## Expected products

- `wrf_100m_wind.nc` or `.json` — the local meteorological forcing product.
- `wildfire_event.json` — the generated Spritz configuration.
- `model/meteo.*` — suite meteorology exchange file.
- `model/concentration.*` — dispersion output.
- `model/post.json` — postprocessed statistics.

The `--backend` choice is stored in `wildfire_event.json` under `run.backend`.
Change that JSON key, or pass `--backend` when rerunning `sprtz run`, to compare
Gaussian and particle behavior. For gridded 3D output, add
`"concentration_output": "grid"` and `"field_z_levels": [...]` to the same
`run` block.

## Scientific caution

This is a screening and teaching workflow, not a certified fire-emission inventory. Operational use requires validated fuel loading, combustion phase, plume-injection height, satellite constraints, and independent model evaluation.
