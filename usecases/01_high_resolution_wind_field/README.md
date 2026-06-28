# Use case 01 - High-resolution wind-field downscaling

Goal: obtain a local 100 m wind and precipitation-rate field centered on a user-supplied latitude and longitude, starting from a 1 km WRF5 d03 file.

This didactic workflow is deliberately explicit, and
`step_01_downscale_wind.py` invokes the production modules in this order:

1. **Input step.** Use a local WRF NetCDF file or call `spritzwrf.download_meteo_uniparthenope_wrf` for the meteo@uniparthenope archive.
2. **SpritzWRF extraction step.** Call `spritzwrf.load_near_surface_wind` to extract latitude, longitude, near-surface wind components, and precipitation when available.
3. **SpritzMet downscaling step.** Call `spritzmet.downscale_wrf_to_local_grid` to build the local azimuthal-equidistant grid and downscale SpritzWRF fields onto the 100 m grid.
4. **Output step.** Call `spritzmet.write_local_meteorology` to write NetCDF-CF by default, or JSON for lightweight runs.

SpritzWRF reads WRF valid time strictly from WRF/CF metadata (`Times`, CF
`time`, or explicit global time attributes). It does not infer datetimes from
the WRF filename. Four-dimensional WRF wind variables are managed as
`time, level, y, x`. By default, when `--time-index` and `--level-index` are
omitted, the workflow downscales all WRF times and all wind levels. Pass
either option only when you need a single slice. The NetCDF-CF output includes a
CF `time(time)` coordinate with absolute UTC units when the WRF file provides
valid-time metadata.

The grid can be requested in either of two ways:

- `--center-lat --center-lon --nx --ny` creates an exact node-count grid centered on one coordinate.
- `--south --north --west --east` creates a conservative grid covering the requested bounding box. The script keeps `--dx` and `--dy` as hard constraints and expands the actual covered area outward to the nearest exact spacing multiple.

The WRF archive pattern is:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

## Data preparation

Prepare WRF input with the repository downloader:

```bash
tools/meteouniparthenope-wrf-download.py 20260527Z0000 \
  --hours 1 \
  --domain d03 \
  --data-root data
```

Prepare terrain for workflows that also need surface elevation:

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

The WRF file feeds SpritzWRF/SpritzMet directly. The COP30 GeoTIFF feeds
`sprtz-terrain fetch` as a local DEM input, and LC100 feeds the matching local
land-cover input when `sprtz[geo]` is installed; see
`docs/copernicus-cop30-dem-download.md` and
`docs/copernicus-lc100-download.md`.

## Run with automatic download

```bash
python usecases/01_high_resolution_wind_field/step_01_downscale_wind.py \
  --date 20260527Z0000 \
  --hours 24 \
  --download-dir data/wrf \
  --output data/output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 --ny 101 \
  --dx 100 --dy 100
```

This mode uses hourly WRF files from `data/wrf` for the interval
`20260527Z0000` through `20260527Z2300`. Existing files named
`wrf5_d03_YYYYMMDDZhh00.nc` may be directly under `data/wrf` or under
`data/wrf/d03`; missing files are downloaded to `data/wrf`. The result is one
NetCDF file with 24 time slices on the requested 101 by 101 grid at 100 m by
100 m spacing.

## Run with a bounding box

```bash
python usecases/01_high_resolution_wind_field/step_01_downscale_wind.py \
  --download-time 20260527Z0000 \
  --download-dir data/wrf \
  --output data/output/wrf_100m_wind_bbox.nc \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --dx 100 --dy 100
```

In bounding-box mode, `--dx` and `--dy` are never changed. The workflow derives
the local grid center from the box midpoint, projects the four requested corners
to the local SpritzMet grid, and increases `nx` and `ny` just enough to cover
the box with exact grid spacing.

## Print the URL without downloading

```bash
python usecases/01_high_resolution_wind_field/step_01_downscale_wind.py \
  --download-time 20260527Z0000 \
  --output ignored.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --print-download-url
```

## Run with an existing WRF file

```bash
python usecases/01_high_resolution_wind_field/step_01_downscale_wind.py \
  --wrf data/wrf/wrf5_d03_20260527Z0000.nc \
  --output data/output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27
```

This downscales all WRF times and all wind levels into
`eastward_wind(time,z,y,x)`, `northward_wind(time,z,y,x)`, and
`precipitation_rate(time,y,x)`. To extract only one WRF slice, pass explicit
indices:

```bash
python usecases/01_high_resolution_wind_field/step_01_downscale_wind.py \
  --wrf data/wrf/wrf5_d03_20260527Z0000.nc \
  --output data/output/wrf_100m_wind_t000_z000.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --time-index 0 \
  --level-index 0
```

## Plot the intermediate/final NetCDF map

When the workflow writes NetCDF, `step_01_downscale_wind.py` also calls
`tools/plotter.py` and writes a wind-speed map beside the NetCDF product. To
regenerate the publication map explicitly, run:

```bash
python tools/plotter.py data/output/wrf_100m_wind.nc \
  --variable wind_speed \
  --time-index 12 \
  --level-index 0 \
  --output data/output/wrf_100m_wind.png
```

For a bounding-box product, use the matching NetCDF path:

```bash
python tools/plotter.py data/output/wrf_100m_wind_bbox.nc \
  --variable wind_speed \
  --output data/output/wrf_100m_wind_bbox.png
```

## Classroom/demo run without WRF data

```bash
python usecases/01_high_resolution_wind_field/step_01_downscale_wind.py \
  --allow-synthetic \
  --json \
  --output data/output/demo_wind.json \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 21 --ny 21
```

## Expected products

- `wrf_100m_wind.nc` or `.json`
- `wrf_100m_wind.png` when NetCDF output is selected and plotting dependencies are available
- variables/fields: `latitude`, `longitude`, `z`, `eastward_wind(time,z,y,x)`, `northward_wind(time,z,y,x)`, `wind_speed(time,z,y,x)`, `wind_from_direction(time,z,y,x)`, `precipitation_rate(time,y,x)`

## Teaching notes

The script uses production modules `sprtz.models.spritzwrf` and `sprtz.models.spritzmet`, but the scenario orchestration lives only in this folder. This keeps the suite compact and keeps educational workflows easy to inspect.
