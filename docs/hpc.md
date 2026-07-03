# HPC And SLURM

## Scientific Scope

This document describes batch and SLURM execution of Sprtz workflows. It emphasizes reproducibility, optional parallelism, deterministic serial fallback, and audit-friendly logs for scientific computing environments.

This guide shows how to submit Spritz modules on an HPC system with SLURM. The commands assume the package is installed in `.venv` and optional MPI dependencies are available.

## Environment

```bash
module load python/3.11 openmpi/4.1
source .venv/bin/activate
```

For NetCDF-CF collective IO or GPU jobs, load site-specific modules:

```bash
module load hdf5-parallel netcdf4-parallel cuda
```

## SpritzMet

Use spatial MPI decomposition and optional CUDA:

```bash
#!/bin/bash
#SBATCH --job-name=spritzmet
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --time=00:20:00
#SBATCH --mem-per-cpu=2G

module load python/3.11 openmpi/4.1
source .venv/bin/activate
mpiexec -n $SLURM_NTASKS spritzmet --config examples/minimal.json --output output_hpc/meteo.nc --format netcdf --parallel mpi --gpu-backend auto
```

## Gaussian Or Particle Dispersion

Gaussian uses receptor decomposition. Particles use source decomposition.

```bash
#!/bin/bash
#SBATCH --job-name=spritz_dispersion
#SBATCH --ntasks=8
#SBATCH --time=00:20:00

module load python/3.11 openmpi/4.1
source .venv/bin/activate
mpiexec -n $SLURM_NTASKS spritz --config examples/minimal.json --meteo output_hpc/meteo.nc --output output_hpc/concentration.nc --format netcdf --backend gaussian --parallel mpi --gpu-backend auto
mpiexec -n $SLURM_NTASKS spritz --config examples/minimal.json --meteo output_hpc/meteo.nc --output output_hpc/particles.nc --format netcdf --backend particles --parallel mpi --gpu-backend auto
```

## SpritzFire

SpritzFire uses realization splitting. One GPU per rank is recommended on GPU nodes.

```bash
#!/bin/bash
#SBATCH --job-name=spritzfire
#SBATCH --ntasks=4
#SBATCH --gres=gpu:4
#SBATCH --time=00:30:00

module load python/3.11 openmpi/4.1 cuda
source .venv/bin/activate
mpiexec -n $SLURM_NTASKS sprtzfire --config examples/wildfire_mpi.json --output-dir output_fire_hpc --parallel mpi --gpu-backend auto --interchange netcdf
```

## Backward Attribution

```bash
#!/bin/bash
#SBATCH --job-name=sprtz_backward
#SBATCH --ntasks=4
#SBATCH --time=00:10:00

module load python/3.11 openmpi/4.1
source .venv/bin/activate
spritzmet --config examples/backward_plume.json --output output_backward/meteo.json --format json
mpiexec -n $SLURM_NTASKS sprtz-backward --config examples/backward_plume.json --meteo output_backward/meteo.json --model gaussian --output output_backward/source_likelihood.json
```

## Practical Notes

- Use `--parallel mpi` when SLURM allocated multiple ranks.
- Use `--gpu-backend cupy` only when CUDA/CuPy is guaranteed; otherwise use `auto`.
- Keep output directories per job to avoid concurrent writes.
- Run `sprtz doctor --require-mpi` on the target node before production jobs.
- Prefer NetCDF-CF for chained HPC workflows.

## References

- Message Passing Interface Forum. (1994). MPI: A message-passing interface standard. International Journal of Supercomputer Applications, 8(3-4), 159-416.
- Gropp, W., Lusk, E., Doss, N., and Skjellum, A. (1996). A high-performance, portable implementation of the MPI message passing interface standard. Parallel Computing, 22(6), 789-828.
- Owens, J. D., Houston, M., Luebke, D., Green, S., Stone, J. E., and Phillips, J. C. (2008). GPU computing. Proceedings of the IEEE, 96(5), 879-899. https://doi.org/10.1109/JPROC.2008.917757
- Wilson, G., Aruliah, D. A., Brown, C. T., Hong, N. P. C., Davis, M., Guy, R. T., Haddock, S. H. D., Huff, K. D., Mitchell, I. M., Plumbley, M. D., Waugh, B., White, E. P., and Wilson, P. (2014). Best practices for scientific computing. PLOS Biology, 12(1), e1001745. https://doi.org/10.1371/journal.pbio.1001745
- Sandve, G. K., Nekrutenko, A., Taylor, J., and Hovig, E. (2013). Ten simple rules for reproducible computational research. PLOS Computational Biology, 9(10), e1003285. https://doi.org/10.1371/journal.pcbi.1003285
