# Use Case 11: Backward Fire Origin

Estimate likely ignition locations from observed burned/fire points and wind direction.

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
