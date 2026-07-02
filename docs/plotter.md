# Plotter

`tools/plotter.py` creates publication-oriented maps from Sprtz NetCDF outputs.
It is intended for use-case figures, reports, and quick quality-control maps of
intermediate and final products.

## Basic usage

```bash
MPLBACKEND=Agg python tools/plotter.py \
  output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --time-index 1 \
  --output output/wildfire_case/model_compare/particles/concentration_map.png
```

For SpritzMet products with geographic coordinates:

```bash
MPLBACKEND=Agg python tools/plotter.py \
  data/output/wrf_100m_wind.nc \
  --variable wind_speed \
  --output data/output/wrf_100m_wind.png
```

When the NetCDF contains wind components (`eastward_wind`/`northward_wind`,
`U10`/`V10`, `U10M`/`V10M`) or wind speed plus meteorological direction
(`wind_speed`/`wind_from_direction`, `WSPD10`/`WDIR10`), the plotter overlays
wind vectors automatically. Control arrow density by target vector count,
control exact stride, or disable vectors with:

```bash
MPLBACKEND=Agg python tools/plotter.py \
  data/output/wrf_100m_wind.nc \
  --variable wind_speed \
  --vector-density 20 \
  --output data/output/wrf_100m_wind_vectors.png

MPLBACKEND=Agg python tools/plotter.py \
  data/output/wrf_100m_wind.nc \
  --variable wind_speed \
  --vector-stride 5 \
  --output data/output/wrf_100m_wind_stride5.png

MPLBACKEND=Agg python tools/plotter.py \
  data/output/wrf_100m_wind.nc \
  --variable wind_speed \
  --no-vectors \
  --output data/output/wrf_100m_wind_scalar.png
```

If a NetCDF contains multiple times, select one time step by zero-based index.
For four-dimensional wind products such as `eastward_wind(time,z,y,x)` or WRF
`U(Time,bottom_top,south_north,west_east)`, select the vertical slice with
`--level-index`. Surface diagnostic products such as `U10M(time,y,x)`,
`V10M(time,y,x)`, `wind_speed_10m(time,y,x)`, and
`precipitation_rate(time,y,x)` use only `--time-index`. Sprtz NetCDF products
with a time axis must
provide a CF `time(time)` coordinate with units such as
`seconds since 2026-05-27 00:00:00 UTC`; products may also include
`time_datetime(time)` as an ISO-8601 convenience coordinate. The plot title
includes UTC time when the file provides `time_datetime`, WRF `Times`, or
CF-style absolute time units. The plotter does not infer scientific datetimes
from NetCDF filenames or `source` paths:

```bash
MPLBACKEND=Agg python tools/plotter.py \
  output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --time-index 3 \
  --output output/wildfire_case/model_compare/particles/concentration_t003.png

MPLBACKEND=Agg python tools/plotter.py \
  data/output/wrf_100m_wind.nc \
  --variable wind_speed \
  --time-index 0 \
  --level-index 0 \
  --output data/output/wrf_100m_wind_z000.png
```

For local-grid products that do not contain latitude/longitude, pass the grid
origin so the tool can transform local AEQD coordinates to WGS84:

```bash
MPLBACKEND=Agg python tools/plotter.py \
  output_fire/firefront.nc \
  --variable fire_probability \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --output output_fire/firefront_map.png
```

Use-case plotting helpers also generate `meteo_vertical_profiles.png` beside
workflow meteo maps. That figure is not a separate `tools/plotter.py` CLI mode;
it is produced by the didactic workflow helpers from SpritzMet NetCDF files
with `wind_speed(time,z,y,x)`.

## Coastlines

When Cartopy is installed and local Natural Earth data are available, the plotter
draws high-resolution Natural Earth `10m` coastlines, borders, land, and ocean
context over geographic plots by default. Select the coastline source with
`--coastline-source naturalearth` or `--coastline-source gshhs`. GSHHS is useful
for small coastal and harbor-scale domains where Natural Earth may be too
generalized. The tool does not allow Cartopy network downloads unless explicitly
requested:

```bash
MPLBACKEND=Agg python tools/plotter.py \
  output/production_2021_44/model/concentration.nc \
  --variable concentration \
  --output output/production_2021_44/concentration_map.png \
  --allow-cartopy-download
```

For harbor-scale wind maps, use GSHHS with `10m` resolution:

```bash
MPLBACKEND=Agg python tools/plotter.py \
  data/output/wrf_100m_wind_bbox.nc \
  --variable wind_speed \
  --output data/output/wrf_100m_wind_bbox.png \
  --coastline-source gshhs \
  --coastline-resolution 10m \
  --allow-cartopy-download
```

Use `--coastline-resolution 50m` or `110m` for faster overview figures. With
GSHHS, these map to Cartopy's `intermediate` and `low` GSHHS scales.
If Cartopy's NOAA GSHHS downloader fails after `--allow-cartopy-download`, the
plotter tries the maintained SOEST GSHHG shapefile archive and installs the
requested scale into Cartopy's normal data directory.

## Use cases

Use-case scripts call the plotter for every NetCDF product they create when a
map can be derived locally:

- SpritzMet intermediate meteorology, usually wind speed or eastward wind.
- Terrain/GEO NetCDF products when present.
- Firefront NetCDF products, usually fire probability.
- Concentration NetCDF products from Gaussian, particle, or puff workflows.

If optional plotting dependencies are unavailable, use-case scripts log a warning
and keep the numerical workflow result. JSON, CSV, and GeoJSON products remain
available but are not plotted by `tools/plotter.py`.
