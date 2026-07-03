# SpritzFire MPI

## Scientific Scope

This document describes optional MPI decomposition for SpritzFire. It emphasizes deterministic domain or realization partitioning, rank-local work, and rank-0 responsibility for shared outputs.

SpritzFire MPI splits stochastic realizations across ranks. Each rank runs independent realizations with a rank-offset seed and rank 0 reduces ensemble probability and arrival time.

```bash
mpiexec -n 4 sprtzfire --config examples/wildfire_mpi.json --output-dir output_fire_mpi --parallel mpi
```

MPI remains optional and requires `mpi4py`.

Use `--gpu-backend auto` or `--gpu-backend cupy` to select one optional CUDA backend per rank. Realization splitting is retained because it minimizes communication and composes cleanly with one GPU per MPI process.

## References

- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 1: Physical and quasi-physical models. International Journal of Wildland Fire, 18(4), 349-368.
- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 2: Empirical and quasi-empirical models. International Journal of Wildland Fire, 18(4), 369-386.
- Mandel, J., Beezley, J. D., and Kochanski, A. K. (2011). Coupled atmosphere-wildland fire modeling with WRF-Fire. Geoscientific Model Development, 4, 591-610. https://doi.org/10.5194/gmd-4-591-2011
- Courant, R., Friedrichs, K., and Lewy, H. (1928). Uber die partiellen Differenzengleichungen der mathematischen Physik. Mathematische Annalen, 100, 32-74.
- LeVeque, R. J. (1997). Wave propagation algorithms for multidimensional hyperbolic systems. Journal of Computational Physics, 131(2), 327-353.
- Message Passing Interface Forum. (1994). MPI: A message-passing interface standard. International Journal of Supercomputer Applications, 8(3-4), 159-416.
