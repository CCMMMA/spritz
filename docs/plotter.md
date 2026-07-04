# Plotter

## Scientific Scope

This document describes publication-oriented plotting utilities for Sprtz outputs. It emphasizes scientifically meaningful coordinates, units, time labels, and reproducible rendering from NetCDF products.

`tools/plotter.py` creates publication-oriented maps from Sprtz NetCDF outputs.
`tools/profiler.py` creates centralized time-varying vertical profile figures
from the same NetCDF products. `tools/render3d.py` creates high-quality
three-dimensional volume views from compatible `z,y,x` or `time,z,y,x` fields.
They are intended for use-case figures, reports, and quick quality-control
plots of intermediate and final products.

For concentration and gridded mass fields, zero or negative mass concentration
is rendered transparent in maps, vertical profile heatmaps, and 3-D plume
views. This keeps no-mass cells from painting artificial background color into
the figure.

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
`precipitation_rate(time,y,x)` use only `--time-index`. Use-case vertical
profile plots prepend the diagnostic 10 m above-ground layer when it is present
and the first physical `z` level is aloft, matching Gaussian and particle wind
sampling. Sprtz NetCDF products
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

When both local `x/y` and WGS84 longitude/latitude are available, map figures
show longitude/latitude on the primary axes and local metres on secondary axes.

Use-case plotting helpers also generate `meteo_vertical_profiles.png` beside
workflow meteo maps and plume concentration profile figures beside concentration
maps. The centralized CLI for those figures is `tools/profiler.py`:

```bash
MPLBACKEND=Agg python tools/profiler.py \
  output/wildfire_case/model_compare/particles/meteo.nc \
  --variable wind_speed \
  --output output/wildfire_case/model_compare/particles/meteo_vertical_profiles.png

MPLBACKEND=Agg python tools/profiler.py \
  output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --output output/wildfire_case/model_compare/particles/concentration_vertical_profiles.png
```

`tools/profiler.py` accepts the same broad CLI style as `tools/plotter.py`:
input path first, `--variable`, `--output`, `--time-index`, `--dpi`, and
`--animate`. Use `--x` and `--y` to select the local grid column. Without
`--time-index`, static figures show a time-height section plus sampled vertical
profiles through the simulation.
When the NetCDF also contains latitude/longitude fields, profiler titles include
the WGS84 coordinate of the local `x=0, y=0` origin point for geographic context.

`tools/render3d.py` follows the same CLI family for three-dimensional fields:
input path first, `--variable`, `--output`, `--time-index`, `--dpi`, `--cmap`,
`--log-scale`, and `--animate`. Pass `--terrain path/to/geo.nc` to render a
DEM-shaped ground surface from `surface_altitude`/`elevation_m` and color that
surface with `land_cover` or `landuse_class`. Plume and other volume fields are
rendered above that ground surface, so `field_z` heights are interpreted as
height above local DEM where terrain is available. Static renders use all
vertical levels and extract either a threshold surface or a sparse voxel view:
when longitude/latitude axes are available, the 3-D horizontal tick labels show
both local metres and WGS84 coordinates.

```bash
MPLBACKEND=Agg python tools/render3d.py \
  output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --time-index 3 \
  --terrain output/wildfire_case/geo.nc \
  --mode surface \
  --threshold-quantile 0.85 \
  --output output/wildfire_case/model_compare/particles/concentration_3d.png

MPLBACKEND=Agg python tools/render3d.py \
  output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --time-index 3 \
  --terrain output/wildfire_case/geo.nc \
  --mode voxel \
  --threshold-quantile 0.90 \
  --output output/wildfire_case/model_compare/particles/concentration_voxels.png
```

Use `--max-points` to limit per-axis sampling for large NetCDF products and
`--elevation` / `--azimuth` to make camera angles reproducible in manuscripts.

## Animations

`tools/plotter.py` can render a simulation-long animated GIF from every time
frame of a gridded map variable:

```bash
MPLBACKEND=Agg python tools/plotter.py \
  output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --level-index 0 \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --output output/wildfire_case/model_compare/particles/concentration_animation.gif
```

For map animations, the plotter evaluates the selected variable over all
animation frames before rendering and fixes one color scale for the whole GIF.
For nonnegative linear fields, the lower bound is pinned at zero and the upper
bound is the simulation-wide maximum. With `--log-scale`, the bounds come from
the simulation-wide positive minimum and maximum. Use `--gif-loop 0` to loop
forever, or a positive integer for a finite loop count.

`tools/profiler.py` can render a simulation-long animated GIF from every
vertical-profile time frame:

```bash
MPLBACKEND=Agg python tools/profiler.py \
  output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --output output/wildfire_case/model_compare/particles/concentration_profiles_animation.gif
```

`tools/render3d.py` can render a simulation-long animated GIF from every time
frame of a selected volume variable. It evaluates all frames first and fixes one
color scale across the animation:

```bash
MPLBACKEND=Agg python tools/render3d.py \
  output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --terrain output/wildfire_case/geo.nc \
  --mode surface \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --output output/wildfire_case/model_compare/particles/concentration_3d_animation.gif
```

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

## References

- Hunter, J. D. (2007). Matplotlib: A 2D graphics environment. Computing in Science & Engineering, 9(3), 90-95. https://doi.org/10.1109/MCSE.2007.55
- Waskom, M. L. (2021). seaborn: statistical data visualization. Journal of Open Source Software, 6(60), 3021. https://doi.org/10.21105/joss.03021
- Rew, R., and Davis, G. (1990). NetCDF: an interface for scientific data access. IEEE Computer Graphics and Applications, 10(4), 76-82. https://doi.org/10.1109/38.56302
- Balaji, V., Taylor, K. E., Juckes, M., Lawrence, B. N., Durack, P. J., Lautenschlager, M., Blanton, C., Cinquini, L., Denvil, S., Elkington, M., Guglielmo, F., Guilyardi, E., Hassell, D., Kharin, S., Kindermann, S., Nikonov, S., Radhakrishnan, A., Stockhause, M., and Weigel, T. (2018). Requirements for a global data infrastructure in support of CMIP6. Geoscientific Model Development, 11, 3659-3680. https://doi.org/10.5194/gmd-11-3659-2018
