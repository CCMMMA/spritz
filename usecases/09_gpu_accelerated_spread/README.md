# Use Case 09: GPU Accelerated Spread

Documents the optional GPU backend. CPU remains the default fallback when CuPy or Numba CUDA are unavailable.

## Data Preparation

GPU acceleration changes execution, not input provenance. Prepare the same WRF
and COP30 terrain products before large real-area runs:

```bash
tools/meteouniparthenope-wrf-download.py 20260601Z0000 --hours 6 --domain d03 --data-root data
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_gpu_fire_area.tif
python3 tools/copernicus-lc100-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/landcover/lc100_gpu_fire_area.tif
```

Use the DEM and LC100 land cover through `sprtz-terrain fetch`; GPU backend
detection remains lazy and falls back to CPU if optional libraries are
unavailable.

```bash
sprtzfire --config examples/wildfire_minimal.json --output-dir output_fire_gpu --interchange json
```
