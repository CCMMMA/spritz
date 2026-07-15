# Use case 02 staged SLURM workflow

The staged workflow uses non-blocking `sbatch` submission and explicit
dependencies.

| Stage | Launcher | Execution |
|---|---|---|
| WRF download | `01_download_weather.slurm` | serial network job |
| COP30 DEM download | `02_download_dem.slurm` | serial network job |
| LC100 land-use download/crop | `03_download_landuse.slurm` | serial network job with shared source cache |
| Meteorological downscaling | `04_downscale_meteorology.slurm` | 8 MPI ranks |
| Particle model | `05_run_particles.slurm` | 8 MPI ranks |
| Gaussian model | `06_run_gaussian.slurm` | 8 MPI ranks |
| Plotting | `07_plot.slurm` | serial, headless Matplotlib |

Build the event configuration with demo Step 2 before submission. `submit.sh`
refuses to queue jobs when `data/output/wildfire_case/wildfire_event.json` is
absent. Then run:

```bash
module load python
module load openmpi
source .venv/bin/activate
python -m pip install -e '.[netcdf,geo,viz,mpi]'
bash usecases/02_wildfire_arson_effects/slurm/submit.sh
```

The three data jobs run independently. MPI downscaling waits for all of them;
particle and Gaussian jobs then run concurrently after meteorology; plotting
waits for both models. Submission is non-blocking and prints every job ID.

Use `squeue -u "${USER}"` to monitor the graph. Add site-specific partition,
account, QoS, memory, and module directives as needed. Set `SPRTZ_VENV` and
`SPRTZ_REPO_ROOT` when the virtual environment or checkout is not inherited
from the submission shell. Only rank 0 writes shared NetCDF outputs.
