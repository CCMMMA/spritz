# Hierarchical Heterogeneous Parallelism

## Scientific Scope

Sprtz supports a conservative hierarchical execution model for atmospheric dispersion, meteorology, and fire-spread workflows. Serial execution remains the reference path. MPI, shared-memory workers, and CUDA/CuPy are optional acceleration layers that must preserve deterministic scientific semantics.

The hierarchy is:

```text
distributed memory: MPI ranks across nodes
shared memory: rank-local threads or processes
accelerator: NumPy or CuPy arrays inside each rank
```

## Public Controls

Workflow and model commands accept these execution controls where applicable:

```text
--parallel serial|auto|mpi
--thread-backend serial|threads|processes|auto
--threads-per-rank N
--gpu-backend numpy|auto|cupy|cuda
--decomposition auto|rows|tiles|receptors|sources|particles|realizations|source-particle-auto|source-receptor-2d
```

`serial`, `numpy`, and rank-local `serial` workers are the compatibility defaults. `SPRITZ_THREADS` can provide the default worker count when `--thread-backend auto` is selected. BLAS thread counts such as `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, and `MKL_NUM_THREADS` should be set deliberately in HPC runs to avoid oversubscription.

## Implementation Layer

The shared abstraction lives in `src/sprtz/parallel/`:

- `mpi.py` isolates optional `mpi4py` imports and rank-safe collectives.
- `threads.py` provides `ThreadContext` for serial, thread, and process maps.
- `gpu.py` provides `GPUContext` for NumPy/CuPy array polymorphism.
- `partition.py` provides deterministic 1-D chunks and 2-D tiles.
- `scheduler.py` combines these as `ParallelContext`.

Model code should request `get_parallel_context(...)` at orchestration boundaries, then pass only the narrow context or backend object needed by numerical kernels.

## Component Strategy

| Module | MPI unit | Shared-memory unit | CUDA unit | Communication |
|---|---|---|---|---|
| SpritzMet | 2-D grid tiles with halo; row mode retained | tile rows/subtiles, time slices | WRF interpolation, DEM/LC corrections, diagnostic grid arrays | halo exchange for local operators; gather/write or optional parallel NetCDF. |
| SpritzGaussian | receptor blocks; optional source-receptor 2-D decomposition | local receptor sub-blocks | source/receptor geometry and batched plume arrays | final gather over receptor rows; optional source-dimension reduction. |
| SpritzParticles | source blocks; particle blocks for dominant sources | particle batches and local reductions | particle advection, stochastic offsets, deposition, hit tests | deterministic reduction of receptor/grid totals. |
| SpritzFirefront | stochastic realizations | realization batches or spatial tiles | cellular automaton state arrays | ensemble reduction; optional tile halo exchange. |

SpritzMet uses spatial rows today and can move WRF-to-local-grid downscaling to 2-D tiles when halo-aware operations are needed. Dense interpolation, terrain correction, 10 m diagnostic wind preservation, precipitation interpolation, 2 m temperature, and 2 m relative humidity should be vectorized over tile arrays.

SpritzGaussian keeps receptor decomposition as the default. Shared-memory receptor sub-blocks and optional GPU source/receptor geometry arrays can be added without changing output row order.

SpritzParticles keeps source decomposition for balanced source catalogs. Dominant single-source cases should use deterministic particle blocks with a seed that includes source and block identity.

SpritzFirefront keeps realization splitting as the default because ensemble members are independent. Very large single realizations can later use tile decomposition with halo exchange and GPU-resident cellular automaton state.

## Determinism Contract

Parallel implementations must gather or reduce partial products in stable order. Random streams must depend on scientific work identity, such as source index, particle block index, or realization index, rather than MPI rank. Rank 0 remains responsible for shared output files unless a separately validated parallel-I/O feature is explicitly enabled.

For particle blocks, the deterministic seed convention is:

```text
particle_seed = base_seed
              + source_index * 1000003
              + particle_block_index * 9176
```

## Performance Model

Let `R` be receptors, `S` sources, `P` particles, `G` grid cells, `E` Firefront ensemble realizations, `T` time steps, `M` MPI ranks, `C` CPU workers per rank, and `A` the accelerator throughput factor.

```text
SpritzMet:        O(G × T) / (M × C × A)
SpritzGaussian:   O(R × S × T) / (M × C × A)
SpritzParticles:  O(S × P × R × T) / (M × C × A)
SpritzFirefront:  O(E × G × T) / (M × C × A)
```

Communication is dominated by halo exchange plus final gather/write for SpritzMet, receptor gather or source-dimension reduction for SpritzGaussian, receptor/grid total reductions for SpritzParticles, and ensemble-statistic reductions for SpritzFirefront.

## Validation Protocol

New mature execution paths should add serial baseline, MPI equivalence, shared-memory equivalence, GPU tolerance, mixed MPI plus shared-memory, mixed MPI plus GPU, deterministic ordering, and small end-to-end workflow tests. The portable smoke group is:

```bash
PYTHONPATH=src python -m compileall -q src tests usecases
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m sprtz doctor
PYTHONPATH=src python -m sprtz run examples/minimal.json --output-dir /tmp/spritz_serial --parallel serial --gpu-backend numpy
```

When MPI is available, also run:

```bash
mpiexec -n 2 sprtz run examples/minimal.json --output-dir /tmp/spritz_mpi --parallel mpi --gpu-backend numpy
mpiexec -n 2 sprtz run examples/minimal.json --output-dir /tmp/spritz_hybrid --parallel mpi --thread-backend auto --threads-per-rank 2 --gpu-backend auto
```

## References

- Message Passing Interface Forum. (1994). MPI: A message-passing interface standard. International Journal of Supercomputer Applications, 8(3-4), 159-416.
- Gropp, W., Lusk, E., Doss, N., and Skjellum, A. (1996). A high-performance, portable implementation of the MPI message passing interface standard. Parallel Computing, 22(6), 789-828.
- Dagum, L., and Menon, R. (1998). OpenMP: an industry-standard API for shared-memory programming. IEEE Computational Science and Engineering, 5(1), 46-55.
- Nickolls, J., Buck, I., Garland, M., and Skadron, K. (2008). Scalable parallel programming with CUDA. Queue, 6(2), 40-53.
- Owens, J. D., Houston, M., Luebke, D., Green, S., Stone, J. E., and Phillips, J. C. (2008). GPU computing. Proceedings of the IEEE, 96(5), 879-899. https://doi.org/10.1109/JPROC.2008.917757
- Li, J., Liao, W.-k., Choudhary, A., Ross, R., Thakur, R., Gropp, W., Latham, R., Siegel, A., Gallagher, B., and Zingale, M. (2003). Parallel netCDF: A high-performance scientific I/O interface. Proceedings of the ACM/IEEE Supercomputing Conference.
- Liao, W.-k., Choudhary, A., Coloma, K., Ward, L., Russell, E., Pundit, M., and Tideman, N. (2021). Supporting data compression in PnetCDF. Proceedings of the IEEE/ACM International Symposium on Cluster, Cloud and Internet Computing.
- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 1: Physical and quasi-physical models. International Journal of Wildland Fire, 18(4), 349-368.
- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 2: Empirical and quasi-empirical models. International Journal of Wildland Fire, 18(4), 369-386.
- Mandel, J., Beezley, J. D., and Kochanski, A. K. (2011). Coupled atmosphere-wildland fire modeling with WRF-Fire. Geoscientific Model Development, 4, 591-610.
- LeVeque, R. J. (1997). Wave propagation algorithms for multidimensional hyperbolic systems. Journal of Computational Physics, 131(2), 327-353.
- Wilson, G., Aruliah, D. A., Brown, C. T., Hong, N. P. C., Davis, M., Guy, R. T., Haddock, S. H. D., Huff, K. D., Mitchell, I. M., Plumbley, M. D., Waugh, B., White, E. P., and Wilson, P. (2014). Best practices for scientific computing. PLOS Biology, 12(1), e1001745.
- Sandve, G. K., Nekrutenko, A., Taylor, J., and Hovig, E. (2013). Ten simple rules for reproducible computational research. PLOS Computational Biology, 9(10), e1003285.
