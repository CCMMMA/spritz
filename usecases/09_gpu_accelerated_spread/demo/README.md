# Use Case 09: GPU Accelerated Spread

Documents the optional GPU backend. CPU remains the default fallback when CuPy or Numba CUDA are unavailable.

NetCDF/time convention: GPU acceleration does not change CF metadata
requirements. NetCDF products keep strict CF coordinates, and any production WRF
valid time must come from SpritzWRF WRF/CF metadata rather than filenames.

## Data Preparation

GPU acceleration changes execution, not input provenance. Prepare the same WRF
and COP30 terrain products before large real-area runs:

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
  --output data/dem/cop30_gpu_fire_area.tif
python3 tools/copernicus-lc100-download.py \
  --center-lat 40.75 \
  --center-lon 14.30 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100 \
  --buffer-m 1000 \
  --output data/landcover/lc100_gpu_fire_area.tif
```

On shared-IP HPC systems, follow the reusable LC100 source-cache procedure in
[`docs/copernicus-lc100-download.md`](../../../docs/copernicus-lc100-download.md)
and pass the cached TIFF through `--source-url`; direct GDAL range reads can
exhaust Zenodo's per-IP request limit.

Use the DEM and LC100 land cover as SpritzMet `--dem`/`--land-cover` inputs
when preparing WRF-derived wind and precipitation, and through
`sprtz-terrain fetch` for fire-spread terrain products. GPU backend detection
remains lazy and falls back to CPU if optional libraries are unavailable.

Create the GPU fire-domain GEO product before 3-D fire-surface rendering:

```bash
sprtz-terrain fetch \
  --center-lat 40.75 \
  --center-lon 14.30 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100 \
  --dem data/dem/cop30_gpu_fire_area.tif \
  --landuse data/landcover/lc100_gpu_fire_area.tif \
  --landuse-mapping copernicus-lc100 \
  --cache-dir output/terrain-cache \
  --output output_fire_gpu/geo.nc
```

```bash
sprtzfire --config examples/wildfire_minimal.json --output-dir output_fire_gpu --interchange netcdf
```

## Plot the final NetCDF map

```bash
python tools/plotter.py output_fire_gpu/firefront.nc \
  --variable fire_probability \
  --output output_fire_gpu/firefront_map.png
```

Use the 3-D renderer to inspect the accelerated fire surface against DEM shape
and terrain colors:

```bash
python tools/plotter.py render3d output_fire_gpu/firefront.nc \
  --variable fire_probability \
  --terrain output_fire_gpu/geo.nc \
  --mode surface \
  --ground-color terrain \
  --output output_fire_gpu/firefront_3d.png
```
