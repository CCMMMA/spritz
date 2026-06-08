# SpritzFire GPU Acceleration Guide

## Backends

Backend detection tries CuPy, then Numba CUDA, then NumPy. `_detect_gpu_backend()` never raises.

## Installation

Install the CuPy package matching your CUDA version, such as `cupy-cuda11x` or `cupy-cuda12x`. CPU execution needs no GPU package.

## MPI

GPU and MPI can be combined by assigning one GPU-capable process per rank:

```bash
mpiexec -n 4 sprtzfire --config examples/wildfire_mpi.json --output-dir output_fire --parallel mpi --gpu-backend auto
```

SpritzFire's best MPI decomposition is realization splitting. Each rank owns independent stochastic realizations; a CUDA backend is selected per rank and should keep CA state on device between output intervals in accelerated implementations.
