# Use case 01 - High-resolution wind-field downscaling

Goal: obtain a local 100 m wind, precipitation-rate, 2 m temperature, and 2 m relative-humidity field centered on a user-supplied latitude and longitude, starting from a 1 km WRF5 d03 file.

This didactic workflow is deliberately explicit, and
`step_01_downscale_wind.py` invokes the production modules in this order:

1. **Input step.** Use a local WRF NetCDF file or call `spritzwrf.download_meteo_uniparthenope_wrf` for the meteo@uniparthenope archive.
2. **SpritzWRF extraction step.** Call `spritzwrf.load_near_surface_wind` to extract latitude, longitude, near-surface wind components, precipitation, 2 m temperature, and 2 m relative humidity when available.
3. **SpritzMet downscaling step.** Call `spritzmet.downscale_wrf_to_local_grid` to build the local azimuthal-equidistant grid and downscale SpritzWRF fields onto the 100 m grid.
4. **Output step.** Call `spritzmet.write_local_meteorology` to write NetCDF-CF by default, or JSON for lightweight runs. Pass `--calmet-dat data/output/CALMET.DAT` when a binary CALMET.DAT-compatible artifact is needed for model evaluation.

SpritzWRF reads WRF valid time strictly from WRF/CF metadata (`Times`, CF
`time`, or explicit global time attributes). It does not infer datetimes from
the WRF filename. Four-dimensional WRF wind variables are managed as
`time, level, y, x`. By default, when `--time-index` and `--level-index` are
omitted, the workflow downscales all WRF times and all wind levels. Pass
either option only when you need a single slice. The NetCDF-CF output includes a
CF `time(time)` coordinate with absolute UTC units when the WRF file provides
valid-time metadata.

Use `--field-z-levels` to set the physical `z` coordinate written by
SpritzMet, or use `--config usecases/01_high_resolution_wind_field/demo/config.json`
for the documented use-case heights above mean sea level:
`10, 15, 25, 50, 75, 100, 150, 250, 500, 750, 1000, 1250` m. Four-dimensional
WRF wind is treated as `time, level, y, x` with levels in metres above sea
level; diagnostic three-dimensional WRF wind such as `U10/V10` is treated as
`time, y, x` at 10 m above local ground. Precipitation remains
`time, y, x`.

The default use-case bounding box is:

```json
[
  [14.18, 40.78],
  [14.18, 40.85],
  [14.33, 40.85],
  [14.33, 40.78],
  [14.18, 40.78]
]
```

The grid can be requested in either of two ways:

- `--center-lat --center-lon --nx --ny` creates an exact node-count grid centered on one coordinate.
- `--south --north --west --east` creates a conservative grid covering the requested bounding box. The script keeps `--dx` and `--dy` as hard constraints and expands the actual covered area outward to the nearest exact spacing multiple.

The WRF5 history-file pattern is:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

## Data preparation

Prepare WRF input with the repository downloader:

```bash
tools/meteouniparthenope-wrf-download.py 20260621Z0000 \
  --hours 24 \
  --domain d03 \
  --data-root data/wrf/d03
```

Prepare terrain for workflows that also need surface elevation:

```bash
python3 tools/copernicus-cop30-dem-download.py \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100 \
  --buffer-m 5000 \
  --output data/dem/cop30_naples.tif

python3 tools/copernicus-lc100-download.py \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100 \
  --buffer-m 5000 \
  --output data/landcover/lc100_naples.tif
```

The WRF file feeds SpritzWRF/SpritzMet directly. Pass the COP30 GeoTIFF as
`--dem` and the LC100 GeoTIFF as `--land-cover` so SpritzMet uses both rasters
for wind and precipitation downscaling. DEM elevation is also used for the 2 m
temperature lapse-rate correction and the corresponding relative-humidity
update when WRF thermodynamic fields are available. The same files can feed
`sprtz-terrain fetch` when standalone terrain/GEO output is needed; install
`sprtz[geo]` for GeoTIFF support. See
`docs/copernicus-cop30-dem-download.md` and
`docs/copernicus-lc100-download.md`.
The download helpers compute the WGS84 source-raster bounds from the same grid
center, node count, spacing, and projection used for `sprtz-terrain fetch`, then
add `--buffer-m` so the resampler never has to use source edge pixels to fill
the model domain.

SpritzMet vertical levels in this WRF-downscaled workflow are altitudes above
mean sea level. Terrain is used to mask or constrain fields below local DEM and
to anchor diagnostic near-surface quantities such as U10M/V10M at 10 m above
ground, but it does not turn the model `z` coordinate into height above ground.
Downstream dispersion use cases should therefore keep gridded `field_z` levels
as ASL values and convert source release heights from ground-relative values
with the DEM at the source.

Build the standalone GEO product before running 3-D visualization:

```bash
sprtz-terrain fetch \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100 \
  --dem data/dem/cop30_naples.tif \
  --landuse data/landcover/lc100_naples.tif \
  --landuse-mapping copernicus-lc100 \
  --cache-dir data/output/high_resolution_wind_field/terrain-cache \
  --output data/output/high_resolution_wind_field/geo.nc
```

## Run with automatic download

```bash
python usecases/01_high_resolution_wind_field/demo/step_01_downscale_wind.py \
  --date 20260621Z0000 \
  --hours 24 \
  --download-dir data/wrf/d03/ \
  --output data/output/high_resolution_wind_field/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 --ny 101 \
  --dx 100 --dy 100 \
  --config usecases/01_high_resolution_wind_field/demo/config.json \
  --dem data/dem/cop30_naples.tif \
  --land-cover data/landcover/lc100_naples.tif \
  --station-measurements data/stations/weather_observations.csv \
  --calmet-dat data/output/CALMET.DAT \
  --parallel auto
```

This mode uses hourly WRF files from `data/wrf` for the interval
`20260527Z0000` through `20260527Z2300`. Existing files named
`wrf5_d03_YYYYMMDDZhh00.nc` may be directly under `data/wrf` or under
`data/wrf/d03`; missing files are downloaded to `data/wrf`. The result is one
NetCDF file with 24 time slices on the requested 101 by 101 grid at 100 m by
100 m spacing.

Station measurements are optional residual observations applied after the
selected SpritzMet downscaling mode. The CSV header may use local projected
`x,y` coordinates in meters, or geographic `latitude,longitude` coordinates.
Provide `wind_speed` and `wind_dir` together for wind correction and/or
`precipitation_rate` for precipitation correction.

`--parallel auto` enables the generic SpritzMet MPI path when the script is
launched with `mpiexec` and `mpi4py` is installed; otherwise it falls back to
serial execution. Use `--parallel mpi` in batch jobs that should fail fast when
MPI is unavailable.

## Run with a bounding box "The Bay of Naples"

```bash
python usecases/01_high_resolution_wind_field/demo/step_01_downscale_wind.py \
  --date 20260621Z0000 \
  --hours 24 \
  --download-dir data/wrf/d03/ \
  --output data/output/high_resolution_wind_field/wrf_100m_wind_bbox.nc \
  --south 40.78 --north 40.85 --west 14.18 --east 14.33 \
  --dx 100 --dy 100 \
  --config usecases/01_high_resolution_wind_field/demo/config.json \
  --dem data/dem/cop30_naples.tif \
  --land-cover data/landcover/lc100_naples.tif \
  --parallel auto
```

In bounding-box mode, `--dx` and `--dy` are never changed. The workflow derives
the local grid center from the box midpoint, projects the four requested corners
to the local SpritzMet grid, and increases `nx` and `ny` just enough to cover
the box with exact grid spacing.

## Print the URL without downloading

```bash
python usecases/01_high_resolution_wind_field/demo/step_01_downscale_wind.py \
  --download-time 20260527Z0000 \
  --output ignored.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --print-download-url
```

## Run with an existing WRF file

```bash
python usecases/01_high_resolution_wind_field/demo/step_01_downscale_wind.py \
  --wrf data/wrf/wrf5_d03_20260527Z0000.nc \
  --output data/output/high_resolution_wind_field/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --dem data/dem/cop30_naples.tif \
  --land-cover data/landcover/lc100_naples.tif
```

This downscales all WRF times and all wind levels into
`eastward_wind(time,z,y,x)`, `northward_wind(time,z,y,x)`, and
`precipitation_rate(time,y,x)`, plus `temperature_2m_c(time,y,x)` and
`relative_humidity_2m(time,y,x)` when the WRF file provides the required
thermodynamic variables. To extract only one WRF slice, pass explicit indices:

```bash
python usecases/01_high_resolution_wind_field/demo/step_01_downscale_wind.py \
  --wrf data/wrf/wrf5_d03_20260527Z0000.nc \
  --output data/output/high_resolution_wind_field/wrf_100m_wind_t000_z000.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --time-index 0 \
  --level-index 0 \
  --dem data/dem/cop30_naples.tif \
  --land-cover data/landcover/lc100_naples.tif
```

## Plot the intermediate/final NetCDF map

`step_01_downscale_wind.py` writes the downscaled meteorology product without
drawing maps by default. Add `--plot` to that command only when you want a
convenience wind-speed PNG beside the NetCDF. To generate or regenerate the
publication map explicitly after a compute-only run, use `tools/plotter.py`:

```bash
python tools/plotter.py data/output/high_resolution_wind_field/wrf_100m_wind.nc \
  --variable wind_speed \
  --time-index 12 \
  --level-index 0 \
  --output data/output/high_resolution_wind_field/wrf_100m_wind.png
```

To plot the diagnostic 10 m wind as a vector field, shade `wind_speed_10m`.
The plotter converts the shaded speed to knots and overlays vectors from
`U10M`/`V10M` automatically:

```bash
python tools/plotter.py data/output/high_resolution_wind_field/wrf_100m_wind.nc \
  --variable wind_speed_10m \
  --time-index 12 \
  --vector-density 20 \
  --output data/output/high_resolution_wind_field/wrf_100m_wind_10m.png
```

For a bounding-box product, use the matching NetCDF path:

```bash
python tools/plotter.py data/output/high_resolution_wind_field/wrf_100m_wind_bbox.nc \
  --variable wind_speed \
  --time-index 12 \
  --level-index 0 \
  --output data/output/high_resolution_wind_field/wrf_100m_wind_bbox.png
```

For finer harbor-scale coastline detail, request GSHHS coastlines explicitly:

```bash
python tools/plotter.py data/output/high_resolution_wind_field/wrf_100m_wind_bbox.nc \
  --variable wind_speed \
  --time-index 12 \
  --level-index 0 \
  --vector-density 20 \
  --output data/output/high_resolution_wind_field/wrf_100m_wind_bbox_10m_12.png \
  --coastline-source gshhs \
  --coastline-resolution 10m \
  --allow-cartopy-download
```

To inspect the vertical wind field in 3-D over DEM-shaped terrain, render the
full wind-speed volume. When a standalone `geo.nc` has been generated by
`sprtz-terrain fetch`, pass it with `--terrain` so the ground surface uses DEM
elevation and terrain colors. The z-axis ticks are the configured ASL model
levels, with any ASL sample below the DEM hidden by the renderer:

```bash
python tools/render3d.py data/output/high_resolution_wind_field/wrf_100m_wind_bbox.nc \
  --variable wind_speed \
  --time-index 12 \
  --terrain data/output/high_resolution_wind_field/geo.nc \
  --mode surface \
  --ground-color terrain \
  --output data/output/high_resolution_wind_field/wrf_100m_wind_3d.png
```

## Classroom/demo run without WRF data

```bash
python usecases/01_high_resolution_wind_field/demo/step_01_downscale_wind.py \
  --allow-synthetic \
  --json \
  --output data/output/high_resolution_wind_field/demo_wind.json \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 21 --ny 21
```

## Expected products

- `wrf_100m_wind.nc` or `.json`
- `wrf_100m_wind.png` when NetCDF output is selected and plotting dependencies are available
- variables/fields: `latitude`, `longitude`, `z` height above mean sea level when `--field-z-levels` is supplied, `eastward_wind(time,z,y,x)`, `northward_wind(time,z,y,x)`, `wind_speed(time,z,y,x)`, `wind_from_direction(time,z,y,x)`, diagnostic `U10M(time,y,x)`, diagnostic `V10M(time,y,x)`, `wind_speed_10m(time,y,x)`, `wind_from_direction_10m(time,y,x)`, `precipitation_rate(time,y,x)`, optional `temperature_2m_c(time,y,x)`, optional `relative_humidity_2m(time,y,x)`

## Teaching notes

The script uses production modules `sprtz.models.spritzwrf` and `sprtz.models.spritzmet`, but the scenario orchestration lives only in this folder. This keeps the suite compact and keeps educational workflows easy to inspect.
