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
meteorology grid. When `U10M`/`V10M` diagnostic wind is available and the first
physical `z` level is above the surface, the Gaussian and particle samplers use
that diagnostic 10 m above-ground wind as the lower-boundary layer for
near-ground plume transport.

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

These bounds use a 10 km geodetic half-width around `40.827, 14.518`, matching
the edge nodes of a `201 x 201` grid with `100 m` spacing.

Use the downloaded DEM and LC100 land-cover rasters through `sprtz-terrain
fetch` with the same domain settings used by the wildfire run. The wind
downscaling step can also read the same rasters directly with `--dem` and
`--land-cover` so SpritzMet adjusts both wind and precipitation on the local
grid.

```bash
sprtz-terrain fetch \
  --center-lat 40.827 \
  --center-lon 14.518 \
  --nx 201 \
  --ny 201 \
  --dx 100 \
  --dy 100 \
  --dem data/dem/cop30_wildfire_case.tif \
  --landuse data/landcover/lc100_wildfire_case.tif \
  --landuse-mapping copernicus-lc100 \
  --cache-dir output/terrain-cache \
  --output data/output/wildfire_case/geo.nc
```

## Step 1: Prepare wind with WRF download

```bash
python usecases/02_wildfire_arson_effects/step_01_downscale_wind.py \
  --date 20240731Z1000 \
  --hours 120 \
  --download-dir data/wrf/d03 \
  --output data/output/wildfire_case/wrf_100m_wind.nc \
  --center-lat 40.827 \
  --center-lon 14.518 \
  --nx 201 \
  --ny 201 \
  --dx 100 \
  --dy 100 \
  --dem data/dem/cop30_wildfire_case.tif \
  --land-cover data/landcover/lc100_wildfire_case.tif
```


## Step 2: Build the fire configuration

```bash
python usecases/02_wildfire_arson_effects/step_02_build_config.py \
  --output data/output/wildfire_case/wildfire_event.json \
  --center-lat 40.827 \
  --center-lon 14.518 \
  --nx 201 \
  --ny 201 \
  --dx 100 \
  --dy 100 \
  --material plastic \
  --start 20240731Z1000 \
  --end 20240803Z0000 \
  --duration-s 86400 \
  --area-m2 2500 \
  --field-z-levels 2.5,5,10,15,20,25,30,35,40,45,50,60,70,80,90,100,125,150,175,200,250,300,350,400,450,500,600,700,800,900,1000,1250,1500,1750,2000
```

For the default single-fire case, `--center-lat 40.827 --center-lon 14.518`
defines both the local projection origin and the fire location. With
`--nx 101 --ny 101 --dx 100 --dy 100`, the local grid is
`x=-5000..5000 m`, `y=-5000..5000 m`, and field cell `G50_50` is the center at
`x=0, y=0`, mapping back to `40.827 N, 14.518 E`. The particle and Gaussian
gridded concentration outputs both use this same center and coordinate contract.
Use `--field-z-levels` to write one or more concentration-field altitudes in
metres above mean sea level; multiple levels enable vertical concentration
profile plots for both Gaussian and particle outputs. Source and receptor
release heights remain heights above local ground.

## Step 3: Run the model

By default, step 3 looks for `wrf_100m_wind.nc` beside the configuration file,
copies it into each backend output directory as `meteo.nc`, derives the
concentration output interval from the NetCDF `time` axis, and enables gridded
plume output with plume-aware vertical field levels.

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
  --center-lat 40.825 \
  --center-lon 14.52 \
  --output data/output/wildfire_case/wrf_100m_wind_map.png

python tools/plotter.py data/output/wildfire_case/model_compare/particles/meteo.nc \
  --variable wind_speed_10m \
  --center-lat 40.825 \
  --center-lon 14.52 \
  --output data/output/wildfire_case/model_compare/particles/particles_meteo_map.png

python tools/plotter.py data/output/wildfire_case/model_compare/gaussian/meteo.nc \
  --variable wind_speed_10m \
  --center-lat 40.825 \
  --center-lon 14.52 \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_meteo_map.png

python tools/plotter.py data/output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --center-lat 40.825 \
  --center-lon 14.52 \
  --time-index 0 \
  --output data/output/wildfire_case/model_compare/particles/particles_concentration_map.png
  
python tools/plotter.py data/output/wildfire_case/model_compare/gaussian/concentration.nc \
  --variable concentration_field \
  --center-lat 40.825 \
  --center-lon 14.52 \
  --time-index 0 \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_concentration_map.png
```

To create animated GIFs with all plume simulation time frames, add
`--animate`. For example:

```bash
python tools/plotter.py data/output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --center-lat 40.825 \
  --center-lon 14.52 \
  --level-index 0 \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --output data/output/wildfire_case/model_compare/particles/particles_concentration_animation.gif

python tools/plotter.py data/output/wildfire_case/model_compare/gaussian/concentration.nc \
  --variable concentration_field \
  --center-lat 40.825 \
  --center-lon 14.52 \
  --level-index 0 \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_concentration_animation.gif
```

Step 3 writes backend-named plume profile and 3-D plume figures for each
backend. To regenerate vertical profile figures explicitly, run:

```bash
python tools/profiler.py data/output/wildfire_case/model_compare/particles/meteo.nc \
  --variable wind_speed \
  --output data/output/wildfire_case/model_compare/particles/particles_meteo_vertical_profiles.png

python tools/profiler.py data/output/wildfire_case/model_compare/gaussian/meteo.nc \
  --variable wind_speed \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_meteo_vertical_profiles.png

python tools/profiler.py data/output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --output data/output/wildfire_case/model_compare/particles/particles_concentration_vertical_profiles.png

python tools/profiler.py data/output/wildfire_case/model_compare/gaussian/concentration.nc \
  --variable concentration_field \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_concentration_vertical_profiles.png
```

To animate the simulation-long plume vertical profile evolution, add
`--animate`:

```bash
python tools/profiler.py data/output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --output data/output/wildfire_case/model_compare/particles/particles_concentration_profiles_animation.gif

python tools/profiler.py data/output/wildfire_case/model_compare/gaussian/concentration.nc \
  --variable concentration_field \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_concentration_profiles_animation.gif
```

The meteo profile figure contains a center-cell time-height wind-speed panel
and sampled vertical profile curves through the WRF/SpritzMet time axis. When
the prepared meteo file contains diagnostic `U10M`/`V10M`, the plotted profile
prepends the diagnostic 10 m above-ground layer before the aloft model levels.
The plume profile figure shows the time-varying vertical
`concentration_field` at the selected center grid column for both the particle
and Gaussian backends.

To regenerate the 3-D plume-over-ground renders explicitly, pass a terrain/GEO
NetCDF built from the same DEM and land-cover rasters. `tools/render3d.py`
draws the DEM as the ground surface, colors it by terrain elevation or
land-cover class, and renders the concentration plume above that ground
surface. Concentration `field_z` levels remain altitudes above mean sea level,
consistent with the WRF/SpritzMet forcing. The dispersion backends convert
source `height_agl_m` to ASL with the DEM at the source, and gridded
concentration cells whose ASL level is below the local DEM are written as zero.
The renderer then uses the configured `field_z` values as z-axis ticks and
draws DEM blue only where `surface_altitude <= 0`.

```bash
python tools/render3d.py data/output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --terrain data/output/wildfire_case/geo.nc \
  --mode voxel \
  --ground-color terrain \
  --vertical-exaggeration 3 \
  --output data/output/wildfire_case/model_compare/particles/particles_concentration_3d_animation.gif

python tools/render3d.py data/output/wildfire_case/model_compare/gaussian/concentration.nc \
  --variable concentration_field \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --terrain data/output/wildfire_case/geo.nc \
  --mode voxel \
  --ground-color terrain \
  --vertical-exaggeration 3 \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_concentration_3d_animation.gif
```

## Event timing, materials, and source height

Use these options to express the run timing requested in the generated JSON:

- `--weather-start` and `--weather-end`: weather simulation start/end datetimes as `YYYYMMDDZhhmm`.
- `--start` and `--end`: fire/arson event start/end datetimes as `YYYYMMDDZhhmm`.
- `--firefighters-start`, `--firefighters-end`, and
  `--firefighters-emission-factor`: suppression period and emission multiplier.
- `--height-agl-m`: release height above local ground level, useful for small
  stacks or chimney-style sources. When the suite is run with a terrain/GEO
  input, this value is added to the DEM elevation at the source before Gaussian
  or particle dispersion is evaluated on ASL SpritzMet levels.
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
- `field_z_levels`: plume-field altitudes above mean sea level from 1.5 m
  through 2000 m by default, or explicit levels from `--field-z-levels`;
- particle defaults: `particles=10000`, `particle_sigma_h=175 m`,
  `particle_sigma_z=150 m`, and `particle_advection_steps=12`.
- Gaussian puff initialization reuses the configured horizontal and vertical
  spread values when `gaussian_initial_sigma_h`/`gaussian_initial_sigma_z` are
  not supplied, keeping side-by-side backend screening on comparable initial
  plume widths.

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
  `concentration_field(time,field_z,field_y,field_x)` output. The center field
  receptor `G50_50` is `x=0, y=0` and carries latitude/longitude
  `40.827, 14.518` for the default case.
- `model_compare/particles/concentration_calpuff.dat` — clean-room
  CALPUFF-style binary export of the same particle gridded concentration,
  dry-flux, and wet-flux fields when `--calpuff-binary` is used.
- `model_compare/particles/post.json` — particle postprocessed statistics.
- `model_compare/gaussian/meteo.nc` — the Gaussian backend copy of the same
  SpritzMet forcing.
- `model_compare/gaussian/concentration.nc` — Gaussian receptor and
  `concentration_field(time,field_z,field_y,field_x)` output on the same
  centered grid and geographic field-receptor coordinates as the particle
  backend.
- `model_compare/gaussian/concentration_calpuff.dat` — clean-room
  CALPUFF-style binary export of the same Gaussian gridded concentration,
  dry-flux, and wet-flux fields when `--calpuff-binary` is used.
- `model_compare/gaussian/post.json` — Gaussian postprocessed statistics.
- `model_compare/particle_gaussian_comparison.json` — common-grid comparison
  metrics, including min/max, mean absolute difference, RMS difference, and max
  absolute difference.
- `wrf_100m_wind_map.png` — horizontal wind map for the prepared forcing.
- `model_compare/*/*_concentration_vertical_profiles.png` — explicit
  backend-named time-varying plume concentration profile figure, written for
  both particles and Gaussian outputs.
- `model_compare/*/*_concentration_profiles_animation.gif` — animated vertical
  plume concentration profile across every concentration output time frame.

The particle backend now advects particles through the full
`time,z,y,x` SpritzMet wind cube. The Gaussian backend samples the same
time-varying wind field along each source/receptor path and treats the active
wildfire as a continuous output-window source. Both backends keep gridded
`field_z` levels in the SpritzMet vertical reference, normally ASL for this WRF
workflow, while applying terrain-aware ASL source release heights from
`height_agl_m`. The two backends are screening
models with different numerical assumptions, so compare their spatial patterns
and timing as well as the summary metrics. Step 3 checks that particle and
Gaussian `time`, `field_z`, `field_y`, and `field_x` coordinates match before
writing the comparison report, so horizontal and vertical output grids stay
consistent across both modes.

## Scientific caution

This is a screening and teaching workflow, not a certified fire-emission inventory. Operational use requires validated fuel loading, combustion phase, plume-injection height, satellite constraints, and independent model evaluation.
