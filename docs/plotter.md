# Plotter

`tools/plotter.py` creates publication-oriented maps from Sprtz NetCDF outputs.
It is intended for use-case figures, reports, and quick quality-control maps of
intermediate and final products.

## Basic usage

```bash
MPLBACKEND=Agg python tools/plotter.py \
  output/wildfire_case/model/concentration.nc \
  --variable concentration \
  --output output/wildfire_case/model_concentration_map.png
```

For SpritzMet products with geographic coordinates:

```bash
MPLBACKEND=Agg python tools/plotter.py \
  data/output/wrf_100m_wind.nc \
  --variable wind_speed \
  --output data/output/wrf_100m_wind.png
```

When the NetCDF contains wind components (`eastward_wind`/`northward_wind`,
`U10`/`V10`) or wind speed plus meteorological direction
(`wind_speed`/`wind_from_direction`, `WSPD10`/`WDIR10`), the plotter overlays
wind vectors automatically. Control arrow density or disable vectors with:

```bash
MPLBACKEND=Agg python tools/plotter.py \
  data/output/wrf_100m_wind.nc \
  --variable wind_speed \
  --vector-stride 5 \
  --output data/output/wrf_100m_wind_vectors.png

MPLBACKEND=Agg python tools/plotter.py \
  data/output/wrf_100m_wind.nc \
  --variable wind_speed \
  --no-vectors \
  --output data/output/wrf_100m_wind_scalar.png
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

## Coastlines

When Cartopy is installed and local Natural Earth data are available, the plotter
draws high-resolution Natural Earth `10m` coastlines, borders, land, and ocean
context over geographic plots by default. The tool does not allow Cartopy
network downloads unless explicitly requested:

```bash
MPLBACKEND=Agg python tools/plotter.py \
  output/production_2021_44/model/concentration.nc \
  --variable concentration \
  --output output/production_2021_44/concentration_map.png \
  --allow-cartopy-download
```

Use `--coastline-resolution 50m` or `110m` for faster overview figures.

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
