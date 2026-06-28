# Use Case 11: Backward Fire Origin

Estimate likely ignition locations from observed burned/fire points and wind direction.

## Data Preparation

Prepare meteorology and terrain for the fire-origin analysis area:

```bash
tools/meteouniparthenope-wrf-download.py 20260601Z0000 --hours 6 --domain d03 --data-root data
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_backward_fire_area.tif
python3 tools/copernicus-lc100-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/landcover/lc100_backward_fire_area.tif
```

Use the COP30 and LC100 GeoTIFFs through `sprtz-terrain fetch` with matching
domain settings when terrain or land cover affects ignition plausibility or
spread interpretation.

```bash
sprtz-backward --config examples/backward_firefront.json --model firefront --output output_backward_fire/ignition_likelihood.json
```

SLURM sketch:

```bash
#!/bin/bash
#SBATCH --job-name=sprtz_backward_fire
#SBATCH --ntasks=1
#SBATCH --time=00:05:00
module load python/3.11
source .venv/bin/activate
sprtz-backward --config examples/backward_firefront.json --model firefront --output output_backward_fire/ignition_likelihood.json
```
