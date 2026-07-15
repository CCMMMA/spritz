# Use Case 06: Wildfire Fire Spread

Runs SpritzFire on a small synthetic domain to demonstrate stochastic fire arrival probability, mean arrival time, and perimeter export.

NetCDF/time convention: SpritzFire NetCDF products follow strict CF coordinate
metadata. For production meteorology inputs, WRF valid time must come through
SpritzWRF WRF/CF metadata and must not be inferred from filenames.

## Data Preparation

The default configuration is synthetic, but real-area fire studies should prepare
WRF forcing and COP30 terrain first:

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
  --output data/dem/cop30_fire_area.tif
python3 tools/copernicus-lc100-download.py \
  --center-lat 40.75 \
  --center-lon 14.30 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100 \
  --buffer-m 1000 \
  --output data/landcover/lc100_fire_area.tif
```

On shared-IP HPC systems, follow the reusable LC100 source-cache procedure in
[`docs/copernicus-lc100-download.md`](../../../docs/copernicus-lc100-download.md)
and pass the cached TIFF through `--source-url`; direct GDAL range reads can
exhaust Zenodo's per-IP request limit.

Use the DEM and LC100 land cover as SpritzMet `--dem`/`--land-cover` inputs
when preparing WRF-derived wind and precipitation, and as local
`sprtz-terrain fetch` inputs before coupling terrain-aware fire spread or smoke
workflows.

Create the fire-domain GEO product before 3-D fire-surface rendering:

```bash
sprtz-terrain fetch \
  --center-lat 40.75 \
  --center-lon 14.30 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100 \
  --dem data/dem/cop30_fire_area.tif \
  --landuse data/landcover/lc100_fire_area.tif \
  --landuse-mapping copernicus-lc100 \
  --cache-dir output/terrain-cache \
  --output output_fire/geo.nc
```

```bash
sprtzfire --config examples/wildfire_minimal.json --output-dir output_fire --interchange netcdf
```

## Plot the final NetCDF map

```bash
python tools/plotter.py output_fire/firefront.nc \
  --variable fire_probability \
  --output output_fire/firefront_map.png
```

When a matching terrain/GEO NetCDF is available, render the probability surface
over DEM-shaped, terrain-colored ground:

```bash
python tools/plotter.py render3d output_fire/firefront.nc \
  --variable fire_probability \
  --terrain output_fire/geo.nc \
  --mode surface \
  --ground-color terrain \
  --output output_fire/firefront_3d.png
```
