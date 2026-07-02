# Use case 02 — Arson or wildfire effects

Goal: create a reproducible screening simulation for an arson/wildfire event at a known latitude and longitude, using WRF 1 km meteorology as wind forcing.

The workflow is intentionally step-by-step:

1. **Choose the event location.** Provide the burning latitude and longitude through `--center-lat` and `--center-lon`.
2. **Acquire meteorology.** Use a local WRF file or download WRF5 d03 from meteo@uniparthenope.
3. **Downscale wind.** Reuse use case 01 logic: SpritzWRF extracts WRF wind and SpritzMet downscales it to 100 m.
4. **Build source terms.** Convert burning material, optional burning temperature, duration, source height, and area into a documented screening heat-release and PM emission estimate.
5. **Generate receptors.** Create a circular receptor set around the fire location.
6. **Run dispersion.** Execute both the particle and Gaussian backends against
   the same high-resolution SpritzMet meteorology, or select one backend for a
   shorter diagnostic run.
7. **Review outputs.** Inspect time-dependent gridded concentration fields,
   postprocessing summaries, backend-comparison metrics, horizontal maps, and
   time-varying vertical wind-profile plots.

NetCDF/time convention: WRF valid time is read only by SpritzWRF from WRF/CF
metadata (`Times`, CF `time`, or explicit global time attributes). The workflow
does not infer datetimes from WRF filenames; NetCDF meteorology and dispersion
products follow strict CF time coordinates.

Meteorology convention: Step 1 writes SpritzMet wind as
`eastward_wind(time,z,y,x)` and `northward_wind(time,z,y,x)`, with the `z`
coordinate in metres and a SpritzMet metadata attribute describing whether the
levels are height above local ground or height above mean sea level. Step 3
reuses this prepared file instead of rebuilding a one-time diagnostic
meteorology grid.

## Data preparation

Prepare WRF forcing before the run:

```bash
tools/meteouniparthenope-wrf-download.py 20240731Z1000 \
  --hours 120 \
  --domain d03 \
  --data-root data/wrf/d03
```

Prepare the optional COP30 terrain source for ground elevation and terrain/GEO
products:

```bash
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.781975 --north 40.872024 \
  --west 14.458727 --east 14.577273 \
  --output data/dem/cop30_wildfire_case.tif

python3 tools/copernicus-lc100-download.py \
  --south 40.781975 --north 40.872024 \
  --west 14.458727 --east 14.577273 \
  --output data/landcover/lc100_wildfire_case.tif
```

These bounds use a 5 km geodetic half-width around `40.827, 14.518`, matching
the edge nodes of a `101 x 101` grid with `100 m` spacing.

Use the downloaded DEM and LC100 land-cover rasters through `sprtz-terrain
fetch` with the same domain settings used by the wildfire run. The wind
downscaling step can also read the same rasters directly with `--dem` and
`--land-cover` so SpritzMet adjusts both wind and precipitation on the local
grid.

## Step 1: Prepare wind with WRF download

```bash
python usecases/02_wildfire_arson_effects/step_01_downscale_wind.py \
  --date 20240731Z1000 \
  --hours 120 \
  --download-dir data/wrf/d03 \
  --output data/output/wildfire_case/wrf_100m_wind.nc \
  --center-lat 40.827 \
  --center-lon 14.518 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100 \
  --dem data/dem/cop30_wildfire_case.tif \
  --land-cover data/landcover/lc100_wildfire_case.tif
```

## Step 1 alternative: Prepare wind with an existing WRF file

```bash
python usecases/02_wildfire_arson_effects/step_01_downscale_wind.py \
  --wrf data/wrf/wrf5_d03_20240731Z0000.nc \
  --output data/output/wildfire_case/wrf_100m_wind.nc \
  --center-lat 40.827 \
  --center-lon 14.518 \
  --dem data/dem/cop30_wildfire_case.tif \
  --land-cover data/landcover/lc100_wildfire_case.tif
```

## Step 2: Build the fire configuration

```bash
python usecases/02_wildfire_arson_effects/step_02_build_config.py \
  --output data/output/wildfire_case/wildfire_event.json \
  --center-lat 40.827 \
  --center-lon 14.518 \
  --material plastic \
  --start 20240731Z1000 \
  --end 20240803Z0000 \
  --duration-s 3600 \
  --area-m2 2500 \
  --precipitation-washout
```

## Step 3: Run the model

By default, step 3 looks for `wrf_100m_wind.nc` beside the configuration file,
copies it into each backend output directory as `meteo.nc`, derives the
concentration output interval from the NetCDF `time` axis, and enables gridded
plume output with a near-surface field level.

```bash
python usecases/02_wildfire_arson_effects/step_03_run_model.py \
  --config data/output/wildfire_case/wildfire_event.json \
  --output-dir data/output/wildfire_case/model_compare \
  --backend both \
  --interchange netcdf \
  --calpuff-binary
```

This writes separate backend products under:

- `data/output/wildfire_case/model_compare/particles/`
- `data/output/wildfire_case/model_compare/gaussian/`
- `data/output/wildfire_case/model_compare/particle_gaussian_comparison.json`

Use `--backend particles` or `--backend gaussian` to run only one backend. Use
`--meteo path/to/wrf_100m_wind.nc` when the prepared SpritzMet product is not
stored beside the configuration JSON. Use `--output-interval-s` to override the
interval inferred from the meteo file. Use `--calpuff-binary` to write a
clean-room CALPUFF-style concentration binary sidecar,
`concentration_calpuff.dat`, for each backend. NetCDF-CF remains the canonical
Sprtz interchange; the binary sidecar is for external comparison workflows.

## Step 4: Plot intermediate and final NetCDF maps

The step scripts call `tools/plotter.py` automatically for NetCDF products. To
regenerate the maps explicitly for a report, run:

```bash
python tools/plotter.py data/output/wildfire_case/wrf_100m_wind.nc \
  --variable wind_speed \
  --output data/output/wildfire_case/wrf_100m_wind_map.png

python tools/plotter.py data/output/wildfire_case/model_compare/particles/meteo.nc \
  --variable wind_speed \
  --output data/output/wildfire_case/model_compare/particles/meteo_map.png

python tools/plotter.py data/output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --time-index 1 \
  --output data/output/wildfire_case/model_compare/particles/concentration_map.png
```

The automatic plotting step also writes `meteo_vertical_profiles.png` for each
backend. The profile figure contains a center-cell time-height wind-speed panel
and sampled vertical profile curves through the WRF/SpritzMet time axis.

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

Step 2 also writes time-dependent plume defaults under `run`:

- `output_interval_s`: hourly output by default, overridden in step 3 when a
  different interval is inferred or supplied;
- `concentration_output`: `both`, so receptor values and gridded plume fields
  are written together;
- `field_z_levels`: `[1.5]`, a near-surface concentration field in metres above
  local ground.

## Multi-fire event JSON

For multiple fires, pass a JSON list to `--fire-events-json`. Each event can
set `id`, `latitude`, `longitude`, `height_agl_m`, `start_datetime`,
`end_datetime`, `material`, `area_m2`, `temperature_k`, and
`emission_factor_g_m2`. Date-time values in this script parameter use
`YYYYMMDDZhhmm`.

```bash
python usecases/02_wildfire_arson_effects/step_02_build_config.py \
  --output data/output/multi_fire/wildfire_event.json \
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
- `CALMET.DAT` — CALMET.DAT-compatible binary SpritzMet export for
  model-evaluation workflows.
- `wildfire_event.json` — the generated Spritz configuration.
- `model_compare/particles/meteo.nc` — the particle backend copy of the
  high-resolution SpritzMet forcing.
- `model_compare/particles/concentration.nc` — particle receptor and
  `concentration_field(time,field_z,field_y,field_x)` output.
- `model_compare/particles/concentration_calpuff.dat` — clean-room
  CALPUFF-style binary export of the same particle gridded concentration,
  dry-flux, and wet-flux fields when `--calpuff-binary` is used.
- `model_compare/particles/post.json` — particle postprocessed statistics.
- `model_compare/gaussian/meteo.nc` — the Gaussian backend copy of the same
  SpritzMet forcing.
- `model_compare/gaussian/concentration.nc` — Gaussian receptor and
  `concentration_field(time,field_z,field_y,field_x)` output.
- `model_compare/gaussian/concentration_calpuff.dat` — clean-room
  CALPUFF-style binary export of the same Gaussian gridded concentration,
  dry-flux, and wet-flux fields when `--calpuff-binary` is used.
- `model_compare/gaussian/post.json` — Gaussian postprocessed statistics.
- `model_compare/particle_gaussian_comparison.json` — common-grid comparison
  metrics, including min/max, mean absolute difference, RMS difference, and max
  absolute difference.
- `wrf_100m_wind_map.png` — horizontal wind map for the prepared forcing.
- `model_compare/*/meteo_map.png` — backend meteo map.
- `model_compare/*/meteo_vertical_profiles.png` — time-varying vertical wind
  profile figure.
- `model_compare/*/concentration_map.png` — gridded plume map for a nonzero
  output time.

The particle backend now advects particles through the full
`time,z,y,x` SpritzMet wind cube. The Gaussian backend samples the same
time-varying wind field along each source/receptor path and treats the active
wildfire as a continuous output-window source. The two backends are screening
models with different numerical assumptions, so compare their spatial patterns
and timing as well as the summary metrics. Step 3 checks that particle and
Gaussian `time`, `field_z`, `field_y`, and `field_x` coordinates match before
writing the comparison report, so horizontal and vertical output grids stay
consistent across both modes.

## Scientific caution

This is a screening and teaching workflow, not a certified fire-emission inventory. Operational use requires validated fuel loading, combustion phase, plume-injection height, satellite constraints, and independent model evaluation.
