# Use case 01 staged SLURM workflow

The launchers separate network acquisition, MPI meteorological downscaling,
and serial plotting. `submit.sh` uses non-blocking `sbatch --parsable` calls and
records dependencies without waiting for any job to finish.

| Stage | Launcher | Execution |
|---|---|---|
| WRF download | `01_download_weather.slurm` | serial network job |
| COP30 DEM download | `02_download_dem.slurm` | serial network job |
| LC100 land-use download/crop | `03_download_landuse.slurm` | serial network job with shared source cache |
| SpritzWRF/SpritzMet | `04_downscale_meteorology.slurm` | 8 MPI ranks via `srun` |
| Plotting | `05_plot.slurm` | serial, headless Matplotlib |

The first three jobs are submitted independently. Downscaling has an `afterok`
dependency on all three; plotting depends on downscaling.

Prepare the environment, then submit from the repository root:

```bash
module load python
module load openmpi
source .venv/bin/activate
python -m pip install -e '.[netcdf,geo,viz,mpi]'
bash usecases/01_high_resolution_wind_field/slurm/submit.sh
```

`sbatch` is non-blocking: the command prints all job IDs and returns. Monitor
with `squeue -u "${USER}"`. Site-specific partitions, accounts, QoS, memory,
and module setup may be added to the launcher headers. An already-active virtual
environment is exported by `sbatch`; alternatively set `SPRTZ_VENV` to its
absolute directory and `SPRTZ_REPO_ROOT` to the shared checkout.

Only rank 0 writes the shared meteorological NetCDF. Compare the MPI output
with an otherwise identical serial run before operational use.
