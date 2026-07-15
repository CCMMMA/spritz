# SpritzMet MPI Domain Decomposition Guide

## Scientific Scope

This document describes MPI domain decomposition for SpritzMet. It emphasizes partition-independent meteorological interpolation, rank-safe output writing, and equivalence to serial downscaling.

## Overview

SpritzMet MPI uses spatial domain decomposition, unlike SpritzFire realization splitting. The implementation partitions rows across ranks, loads each source time frame on rank 0 only, broadcasts it for processing, and gathers the completed field to rank 0 for safe shared-file output. Worker ranks do not perform input or output. The helper module also exposes 2-D Cartesian slice utilities for halo-aware extensions.

CUDA acceleration is optional:

```bash
mpiexec -n 4 spritzmet --config examples/minimal.json --output output/meteo.nc --parallel mpi --gpu-backend auto
```

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

## References

- Message Passing Interface Forum. (1994). MPI: A message-passing interface standard. International Journal of Supercomputer Applications, 8(3-4), 159-416.
- Gropp, W., Lusk, E., Doss, N., and Skjellum, A. (1996). A high-performance, portable implementation of the MPI message passing interface standard. Parallel Computing, 22(6), 789-828.
- Owens, J. D., Houston, M., Luebke, D., Green, S., Stone, J. E., and Phillips, J. C. (2008). GPU computing. Proceedings of the IEEE, 96(5), 879-899. https://doi.org/10.1109/JPROC.2008.917757
- Wilson, G., Aruliah, D. A., Brown, C. T., Hong, N. P. C., Davis, M., Guy, R. T., Haddock, S. H. D., Huff, K. D., Mitchell, I. M., Plumbley, M. D., Waugh, B., White, E. P., and Wilson, P. (2014). Best practices for scientific computing. PLOS Biology, 12(1), e1001745. https://doi.org/10.1371/journal.pbio.1001745
- Sandve, G. K., Nekrutenko, A., Taylor, J., and Hovig, E. (2013). Ten simple rules for reproducible computational research. PLOS Computational Biology, 9(10), e1003285. https://doi.org/10.1371/journal.pcbi.1003285
