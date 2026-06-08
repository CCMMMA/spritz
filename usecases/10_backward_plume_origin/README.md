# Use Case 10: Backward Plume Origin

Estimate possible upwind source locations from one or more odor, smoke, or pollutant detections.

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
