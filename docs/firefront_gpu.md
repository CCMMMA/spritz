# SpritzFire GPU Acceleration Guide

## Backends

Backend detection tries CuPy, then Numba CUDA, then NumPy. `_detect_gpu_backend()` never raises.

## Installation

Install the CuPy package matching your CUDA version, such as `cupy-cuda11x` or `cupy-cuda12x`. CPU execution needs no GPU package.

## MPI

GPU and MPI can be combined by assigning one GPU-capable process per rank. State should remain on device between output intervals in accelerated implementations.
