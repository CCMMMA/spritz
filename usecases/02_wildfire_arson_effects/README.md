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

NetCDF/time convention: WRF valid time is read only by SpritzWRF from WRF/CF
metadata (`Times`, CF `time`, or explicit global time attributes). The workflow
does not infer datetimes from WRF filenames; NetCDF meteorology and dispersion
products follow strict CF time coordinates.

## Data preparation

Prepare WRF forcing before the run:

```bash
tools/meteouniparthenope-wrf-download.py 20260527Z0000 \
  --hours 1 \
  --domain d03 \
  --data-root data
```

Prepare the optional COP30 terrain source for ground elevation and terrain/GEO
products:

```bash
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_naples.tif

python3 tools/copernicus-lc100-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/landcover/lc100_naples.tif
```

Use the downloaded DEM and LC100 land-cover rasters through `sprtz-terrain
fetch` with the same domain settings used by the wildfire run.

## Step 1: Prepare wind with WRF download

```bash
python usecases/02_wildfire_arson_effects/step_01_interpolate_wind.py \
  --download-time 20260527Z0000 \
  --download-dir data/wrf \
  --output output/wildfire_case/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 --ny 101
```

## Step 1 alternative: Prepare wind with an existing WRF file

```bash
python usecases/02_wildfire_arson_effects/step_01_interpolate_wind.py \
  --wrf data/wrf/wrf5_d03_20260527Z0000.nc \
  --output output/wildfire_case/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27
```

## Step 2: Build the fire configuration

```bash
python usecases/02_wildfire_arson_effects/step_02_build_config.py \
  --output output/wildfire_case/wildfire_event.json \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --material plastic \
  --start 20260527Z0000 \
  --end 20260527Z0100 \
  --duration-s 3600 \
  --area-m2 2500 \
  --precipitation-washout
```

## Step 3: Run the model

```bash
python usecases/02_wildfire_arson_effects/step_03_run_model.py \
  --config output/wildfire_case/wildfire_event.json \
  --output-dir output/wildfire_case/model \
  --backend particles \
  --interchange netcdf
```

## Step 4: Plot intermediate and final NetCDF maps

The step scripts call `tools/plotter.py` automatically for NetCDF products. To
regenerate the maps explicitly for a report, run:

```bash
python tools/plotter.py output/wildfire_case/wrf_100m_wind.nc \
  --variable wind_speed \
  --output output/wildfire_case/wrf_100m_wind_map.png

python tools/plotter.py output/wildfire_case/model/meteo.nc \
  --variable wind_speed \
  --output output/wildfire_case/model/meteo_map.png

python tools/plotter.py output/wildfire_case/model/concentration.nc \
  --variable concentration \
  --output output/wildfire_case/model/concentration_map.png
```

## Event timing, materials, and source height

Use these options to express the run timing requested in the generated JSON:

- `--weather-start` and `--weather-end`: weather simulation start/end datetimes as `YYYYMMDDZhhmm`.
- `--start` and `--end`: fire/arson event start/end datetimes as `YYYYMMDDZhhmm`.
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
`emission_factor_g_m2`. Date-time values in this script parameter use
`YYYYMMDDZhhmm`.

```bash
python usecases/02_wildfire_arson_effects/step_02_build_config.py \
  --output output/multi_fire/wildfire_event.json \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --weather-start 20260601Z0000 \
  --weather-end 20260601Z0400 \
  --firefighters-start 20260601Z0200 \
  --firefighters-end 20260601Z0300 \
  --firefighters-emission-factor 0.4 \
  --fire-events-json '[{"id":"F1","latitude":40.8500,"longitude":14.2700,"material":"paper","start_datetime":"20260601Z0000","end_datetime":"20260601Z0300"},{"id":"F2","latitude":40.8550,"longitude":14.2750,"height_agl_m":2.0,"material":"plastic","start_datetime":"20260601Z0100","end_datetime":"20260601Z0400"}]'
```

## Expected products

- `wrf_100m_wind.nc` or `.json` — the local meteorological forcing product.
- `wildfire_event.json` — the generated Spritz configuration.
- `model/meteo.*` — suite meteorology exchange file.
- `model/concentration.*` — dispersion output.
- `model/post.json` — postprocessed statistics.
- `wrf_100m_wind_map.png` and `model_*_map.png` — plotter maps for NetCDF
  intermediate and final products when plotting dependencies are available.

The `--backend` choice is stored in `wildfire_event.json` under `run.backend`.
Change that JSON key, or pass `--backend` when rerunning `sprtz run`, to compare
Gaussian and particle behavior. For gridded 3D output, add
`"concentration_output": "grid"` and `"field_z_levels": [...]` to the same
`run` block.

## Scientific caution

This is a screening and teaching workflow, not a certified fire-emission inventory. Operational use requires validated fuel loading, combustion phase, plume-injection height, satellite constraints, and independent model evaluation.
