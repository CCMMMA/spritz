# SpritzFire GPU Acceleration Guide

## Scientific Scope

This document describes optional GPU execution for SpritzFire. It treats acceleration as an implementation detail that must preserve serial numerical semantics, reproducibility, and graceful fallback on CPU-only systems.

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

## References

- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 1: Physical and quasi-physical models. International Journal of Wildland Fire, 18(4), 349-368.
- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 2: Empirical and quasi-empirical models. International Journal of Wildland Fire, 18(4), 369-386.
- Mandel, J., Beezley, J. D., and Kochanski, A. K. (2011). Coupled atmosphere-wildland fire modeling with WRF-Fire. Geoscientific Model Development, 4, 591-610. https://doi.org/10.5194/gmd-4-591-2011
- Courant, R., Friedrichs, K., and Lewy, H. (1928). Uber die partiellen Differenzengleichungen der mathematischen Physik. Mathematische Annalen, 100, 32-74.
- LeVeque, R. J. (1997). Wave propagation algorithms for multidimensional hyperbolic systems. Journal of Computational Physics, 131(2), 327-353.
- Message Passing Interface Forum. (1994). MPI: A message-passing interface standard. International Journal of Supercomputer Applications, 8(3-4), 159-416.
