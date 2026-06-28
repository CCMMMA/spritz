# Use Case 08: FIRMS Satellite Ignition

Uses NASA FIRMS/VIIRS detections as ignition points. Network access is explicit and requires `FIRMS_MAP_KEY`.

NetCDF/time convention: ignition and fire NetCDF products follow strict CF
coordinate metadata. Operational meteorology used with FIRMS detections must
carry WRF/CF time metadata through SpritzWRF; filenames are not used as
scientific datetime sources.

## Data Preparation

Prepare meteorology and terrain around the FIRMS area of interest before running
an operational ignition study:

```bash
tools/meteouniparthenope-wrf-download.py 20260601Z0000 --hours 6 --domain d03 --data-root data
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_firms_area.tif
python3 tools/copernicus-lc100-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/landcover/lc100_firms_area.tif
```

The FIRMS key is separate from the OpenTopography key used by the COP30
downloader. LC100 uses GDAL `/vsicurl/` against a public source URL. Never
hard-code credentials in configuration files.

```bash
FIRMS_MAP_KEY=... sprtzfire --firms --config examples/wildfire_minimal.json --output-dir output_firms --interchange netcdf
```

## Plot the final NetCDF map

```bash
python tools/plotter.py output_firms/firefront.nc \
  --variable fire_probability \
  --output output_firms/firefront_map.png
```
