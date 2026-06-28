# Use Case 06: Wildfire Fire Spread

Runs SpritzFire on a small synthetic domain to demonstrate stochastic fire arrival probability, mean arrival time, and perimeter export.

## Data Preparation

The default configuration is synthetic, but real-area fire studies should prepare
WRF forcing and COP30 terrain first:

```bash
tools/meteouniparthenope-wrf-download.py 20260601Z0000 --hours 6 --domain d03 --data-root data
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_fire_area.tif
python3 tools/copernicus-lc100-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/landcover/lc100_fire_area.tif
```

Use the DEM and LC100 land cover as local `sprtz-terrain fetch` inputs before
coupling terrain-aware fire spread or smoke workflows.

```bash
sprtzfire --config examples/wildfire_minimal.json --output-dir output_fire --interchange json
```
