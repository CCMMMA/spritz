# SpritzMet MPI Domain Decomposition Guide

## Overview

SpritzMet MPI uses 2-D Cartesian domain decomposition, unlike SpritzFire realization splitting.

## Halo Exchange

Each rank owns a rectangular grid slice with a one-cell halo for gradient-style operations.

## Parallel NetCDF

Parallel NetCDF IO requires MPI-enabled HDF5. Standard pip wheels usually do not provide this, so Sprtz falls back to gather/write when needed.

```bash
#!/bin/bash
#SBATCH --job-name=spritzmet_mpi
#SBATCH --ntasks=16
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=4G
#SBATCH --time=00:30:00

module load python/3.11 openmpi/4.1 hdf5-parallel/1.14 netcdf4-parallel/4.9
source .venv/bin/activate
mpiexec -n $SLURM_NTASKS spritzmet --config examples/wildfire_minimal.json --output output_mpi/meteo.nc --parallel mpi
mpiexec -n $SLURM_NTASKS sprtzfire --config examples/wildfire_minimal.json --output-dir output_mpi --parallel mpi
```
