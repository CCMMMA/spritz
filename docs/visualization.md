# Publishing-quality visualization

`sprtz.models.visualization` provides figure generation for suite outputs. The production scatter plot supports local x/y or WGS84 longitude/latitude coordinates, labelled axes, colorbars, high-DPI output, CSV/JSON/NetCDF-CF concentration inputs, optional local raster basemaps, and explicit opt-in web tile basemaps.

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
