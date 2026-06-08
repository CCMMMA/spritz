# HPC And SLURM

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
