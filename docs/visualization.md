# Publishing-quality visualization

## Scientific Scope

This document describes visualization practices for Sprtz outputs. It emphasizes units, coordinates, temporal metadata, and reproducible figure generation suitable for scientific review.

`sprtz.models.visualization` provides figure generation for suite outputs. The production scatter plot supports local x/y or WGS84 longitude/latitude coordinates, labelled axes, colorbars, high-DPI output, CSV/JSON/NetCDF-CF concentration inputs, optional local raster basemaps, and explicit opt-in web tile basemaps. For NetCDF concentration files that contain `concentration_field(time, field_z, field_y, field_x)`, `tools/plotter.py` can render the gridded field directly with `--variable concentration_field`.

Install visualization dependencies:

```bash
python -m pip install -e .[viz]
```

For optional web tile basemaps:

```bash
python -m pip install -e .[viz,maps]
```

Create a figure:

```bash
sprtz-plot --input output/concentration.nc --output output/concentration.png --title "Scenario A" --dpi 600
```

Create a geographic figure from local coordinates by supplying the local grid center:

```bash
sprtz-plot \
  --input output/concentration.nc \
  --output output/concentration_map.png \
  --coordinates geographic \
  --center-lat 40.926506 \
  --center-lon 14.380875 \
  --dpi 600
```

Use an offline high-resolution basemap image:

```bash
sprtz-plot \
  --input output/concentration.nc \
  --output output/concentration_map.png \
  --coordinates geographic \
  --basemap data/basemaps/acerra.png \
  --basemap-extent 14.30,40.87,14.46,40.98
```

Network map tiles are never fetched implicitly. To use a `contextily` provider,
pass both `--tile-provider` and `--allow-network-basemap`.

The module imports Matplotlib lazily, so compute-only deployments do not need plotting dependencies.

Concentration plots treat zero or negative mass concentration as transparent
background. When NetCDF products provide both local projected `x/y` and WGS84
longitude/latitude coordinates, `tools/plotter.py` labels both coordinate
systems on horizontal and vertical map axes. The local-metre overlays are
computed from the displayed geographic centerlines so centered domains keep
`x=0` and `y=0` visually aligned with the true model-grid center.

Use-case workflow plotting also writes `meteo_vertical_profiles.png` for
SpritzMet NetCDF products. The profile figure combines a time-height wind-speed
section and sampled center-cell vertical profiles, using the same `time,z,y,x`
wind cube consumed by the Gaussian and particle dispersion backends. When
diagnostic `U10M/V10M` is available and the first physical model level is
aloft, the plot prepends the diagnostic 10 m above-ground layer so the
near-surface profile matches dispersion sampling.

Use `tools/plotter.py profile` to create the same style of vertical profile figure from
any compatible Sprtz NetCDF product. It supports meteo wind profiles and plume
concentration profiles, uses `--x`/`--y` to select the sampled local grid
column, and supports `--animate` plus `--gif-loop` for simulation-long profile
GIFs. When latitude/longitude variables are available, the profile figure shows
the WGS84 coordinate of the local `x=0, y=0` point. Use `tools/plotter.py render3d` for
reproducible three-dimensional surface or voxel views of `z,y,x` and
`time,z,y,x` fields, including animated GIFs. It renders all vertical levels by
default. When passed `--terrain geo.nc`, it renders DEM-shaped ground from
`surface_altitude`, colors that surface with a terrain elevation scale by
default, and can switch to land-cover coloring with
`--ground-color land-cover`. Height-above-ground plume coordinates are offset by
the local DEM, height-above-sea-level plume coordinates below the DEM are
masked, ASL vertical ticks are the configured model levels, and DEM sea-blue
coloring is used only where `surface_altitude <= 0`. 3-D horizontal tick labels
show WGS84 longitude and latitude when those axes are present. Use
`--vertical-exaggeration N` with `N >= 1` to
exaggerate vertical relief in the display. Use
`tools/plotter.py --animate --frame-duration-ms ... --gif-loop 0` for
simulation-long map GIFs; this animation interface mirrors `tools/plotter.py render3d`.

## References

- Hunter, J. D. (2007). Matplotlib: A 2D graphics environment. Computing in Science & Engineering, 9(3), 90-95. https://doi.org/10.1109/MCSE.2007.55
- Waskom, M. L. (2021). seaborn: statistical data visualization. Journal of Open Source Software, 6(60), 3021. https://doi.org/10.21105/joss.03021
- Rew, R., and Davis, G. (1990). NetCDF: an interface for scientific data access. IEEE Computer Graphics and Applications, 10(4), 76-82. https://doi.org/10.1109/38.56302
- Balaji, V., Taylor, K. E., Juckes, M., Lawrence, B. N., Durack, P. J., Lautenschlager, M., Blanton, C., Cinquini, L., Denvil, S., Elkington, M., Guglielmo, F., Guilyardi, E., Hassell, D., Kharin, S., Kindermann, S., Nikonov, S., Radhakrishnan, A., Stockhause, M., and Weigel, T. (2018). Requirements for a global data infrastructure in support of CMIP6. Geoscientific Model Development, 11, 3659-3680. https://doi.org/10.5194/gmd-11-3659-2018
