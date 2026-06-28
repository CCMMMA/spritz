# Use Case 10: Backward Plume Origin

Estimate possible upwind source locations from one or more odor, smoke, or pollutant detections.

## Data Preparation

Prepare the forward meteorology and terrain evidence used to interpret backward
likelihood maps:

```bash
tools/meteouniparthenope-wrf-download.py 20260601Z0000 --hours 6 --domain d03 --data-root data
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_backward_plume_area.tif
python3 tools/copernicus-lc100-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/landcover/lc100_backward_plume_area.tif
```

Backward outputs should be reviewed against the archived WRF cycle, the derived
SpritzMet field, COP30 terrain, LC100 land cover, and independent observations.

```bash
spritzmet --config examples/backward_plume.json --output output_backward/meteo.json --format json
sprtz-backward --config examples/backward_plume.json --meteo output_backward/meteo.json --model gaussian --output output_backward/source_likelihood.json
sprtz-backward --config examples/backward_plume.json --meteo output_backward/meteo.json --model particles --output output_backward/source_likelihood_particles.csv --format csv
```

SLURM sketch:

```bash
#!/bin/bash
#SBATCH --job-name=sprtz_backward_plume
#SBATCH --ntasks=4
#SBATCH --time=00:10:00
module load python/3.11 openmpi
source .venv/bin/activate
spritzmet --config examples/backward_plume.json --output output_backward/meteo.json --format json
mpiexec -n $SLURM_NTASKS sprtz-backward --config examples/backward_plume.json --meteo output_backward/meteo.json --model gaussian --output output_backward/source_likelihood.json
```
