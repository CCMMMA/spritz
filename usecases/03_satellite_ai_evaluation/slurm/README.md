# Use case 03 staged SLURM workflow

These launchers cover input acquisition, MPI meteorology and dispersion, and
serial plotting. Satellite acquisition/evaluation remains the separately
documented serial workflow because it uses credentials and external APIs.

| Stage | Launcher | Execution |
|---|---|---|
| WRF download | `01_download_weather.slurm` | serial network job |
| COP30 DEM download | `02_download_dem.slurm` | serial network job |
| LC100 land-use download/crop | `03_download_landuse.slurm` | serial network job with shared source cache |
| Meteorological downscaling | `04_downscale_meteorology.slurm` | 8 MPI ranks |
| Particle model | `05_run_particles.slurm` | 8 MPI ranks |
| Gaussian model | `06_run_gaussian.slurm` | 8 MPI ranks |
| Plotting | `07_plot.slurm` | serial, headless Matplotlib |

Submit from the repository root:

```bash
module load python
module load openmpi
source .venv/bin/activate
python -m pip install -e '.[netcdf,geo,viz,mpi]'
bash usecases/03_satellite_ai_evaluation/slurm/submit.sh
```

The submitter queues all jobs with non-blocking `sbatch --parsable` calls. The
three downloads run independently; meteorology waits for them; both dispersion
models wait for meteorology and may run concurrently; plotting waits for both.
The command prints the job IDs and returns immediately.

Monitor with `squeue -u "${USER}"`. Add site-specific partition, account, QoS,
memory, and module directives as needed. Set `SPRTZ_VENV` and
`SPRTZ_REPO_ROOT` for non-default shared paths. Only rank 0 writes shared
NetCDF files. Run satellite comparison stages after the MPI products exist.
