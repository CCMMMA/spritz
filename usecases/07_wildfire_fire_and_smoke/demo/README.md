# Use Case 07: Wildfire Fire And Smoke

Demonstrates the documented `fire+puff` workflow: fire spread outputs are generated first, then the standard Spritz puff workflow can be run on the same configuration.

NetCDF/time convention: fire, meteorology, and smoke NetCDF products follow
strict CF coordinate metadata. Production WRF valid time must come through
SpritzWRF WRF/CF metadata and must not be inferred from filenames.

## Data Preparation

Prepare external meteorology and terrain before replacing the bundled synthetic
configuration:

```bash
tools/meteouniparthenope-wrf-download.py 20260601Z0000 --hours 6 --domain d03 --data-root data/wrf/d03
python3 tools/copernicus-cop30-dem-download.py \
  --center-lat 40.75 \
  --center-lon 14.30 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100 \
  --buffer-m 1000 \
  --output data/dem/cop30_fire_smoke_area.tif
python3 tools/copernicus-lc100-download.py \
  --center-lat 40.75 \
  --center-lon 14.30 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100 \
  --buffer-m 1000 \
  --output data/landcover/lc100_fire_smoke_area.tif
```

The WRF files feed SpritzWRF/SpritzMet. Pass the DEM and LC100 land cover into
the SpritzMet downscaling step with `--dem` and `--land-cover`; use the same
rasters with `sprtz-terrain fetch` and make sure they cover the coupled fire and
smoke grid.

Create the coupled fire-smoke GEO product before 3-D smoke rendering:

```bash
sprtz-terrain fetch \
  --center-lat 40.75 \
  --center-lon 14.30 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100 \
  --dem data/dem/cop30_fire_smoke_area.tif \
  --landuse data/landcover/lc100_fire_smoke_area.tif \
  --landuse-mapping copernicus-lc100 \
  --cache-dir output/terrain-cache \
  --output output_fire_smoke/geo.nc
```

```bash
sprtz run examples/wildfire_minimal.json --backend fire+puff --output-dir output_fire_smoke --interchange netcdf
```

## Plot intermediate and final NetCDF maps

```bash
python tools/plotter.py output_fire_smoke/firefront.nc \
  --variable fire_probability \
  --output output_fire_smoke/firefront_map.png

python tools/plotter.py output_fire_smoke/concentration.nc \
  --variable concentration \
  --output output_fire_smoke/concentration_map.png
```

For three-dimensional smoke inspection, render the plume above the DEM/LC
terrain surface:

```bash
python tools/plotter.py render3d output_fire_smoke/concentration.nc \
  --variable concentration_field \
  --terrain output_fire_smoke/geo.nc \
  --mode surface \
  --ground-color terrain \
  --output output_fire_smoke/concentration_3d.png
```
