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
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_fire_smoke_area.tif
python3 tools/copernicus-lc100-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/landcover/lc100_fire_smoke_area.tif
```

The WRF files feed SpritzWRF/SpritzMet. Pass the DEM and LC100 land cover into
the SpritzMet downscaling step with `--dem` and `--land-cover`; use the same
rasters with `sprtz-terrain fetch` and make sure they cover the coupled fire and
smoke grid.

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
