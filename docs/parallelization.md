# Parallelization schema

## Scientific Scope

This document presents the parallelization schema for Spritz. It separates scientific state from execution layout so parallel acceleration does not change model interpretation.

Spritz uses an optional hierarchical parallelization layer designed for deterministic atmospheric-dispersion workflows on both laptops and HPC clusters. The same code path can run in serial mode, in automatic MPI mode, or in explicit MPI mode without changing the scenario configuration files. Backend selection can live in JSON `run.backend` or be overridden with `--backend`.

The execution hierarchy is MPI ranks across nodes, rank-local shared-memory workers, and an optional NumPy, CuPy/CUDA, or MLX/Metal array backend inside each rank. Accelerator execution is requested with `--gpu-backend auto`, `cupy`, or `mlx`; CPU NumPy remains the default.

This document describes the production execution schema, how work is partitioned, which files are read and written by each rank, and how to run and validate parallel jobs.

## Goals

Spritz parallelization follows five design goals.

1. **Serial first**: every model must run without MPI, CUDA, or optional HPC libraries.
2. **Hierarchical by construction**: MPI distributes large independent work units; CPU workers subdivide rank-local work; CUDA accelerates dense kernels.
3. **Deterministic partitioning**: static or cost-aware partitions must be reproducible from model inputs, not runtime scheduling order.
4. **Minimal communication**: communication occurs at phase boundaries, halo exchanges, or well-defined reductions.
5. **Safe I/O**: rank-0 gather/write remains the portable default; parallel NetCDF/HDF5 is optional and must be validated per HPC filesystem.

## Supported execution modes

All concentration-producing commands accept one of the following modes:

| Mode | Behavior | Recommended use |
|---|---|---|
| `serial` | Disable MPI even if the process was started by `mpiexec`. | Local debugging, tests, notebooks, small jobs. |
| `auto` | Use MPI only when `mpi4py` is installed and the communicator has more than one rank. Otherwise fall back to serial. | Portable scripts and teaching material. |
| `mpi` | Require `mpi4py`; fail if MPI cannot be initialized. | Production batch jobs where MPI is expected. |

GPU backend modes:

| Mode | Behavior | Recommended use |
|---|---|---|
| `numpy` | CPU arrays only. | Reproducibility tests, CPU-only systems. |
| `auto` | Use CuPy only when CUDA allocation succeeds. | Portable scripts that can benefit from GPU nodes. |
| `cupy` | Require CUDA/CuPy and fail fast if unavailable. | Batch jobs where GPU allocation is expected. |

Shared-memory backend modes:

| Mode | Behavior | Recommended use |
|---|---|---|
| `serial` | Disable rank-local workers. | Default behavior and reproducibility tests. |
| `threads` | Use a `ThreadPoolExecutor` inside each rank. | NumPy/CuPy kernels that release the GIL and light I/O orchestration. |
| `processes` | Use a `ProcessPoolExecutor` inside each rank. | Pure-Python CPU loops where serialization cost is acceptable. |
| `auto` | Use threads when the selected worker count is greater than one. | Workstation or SLURM jobs with `SPRITZ_THREADS` or `--threads-per-rank`. |

Example serial run:

```bash
sprtz run examples/minimal.json \
  --output-dir output-serial \
  --interchange netcdf \
  --parallel serial
```

Example automatic run:

```bash
mpiexec -n 4 sprtz run examples/minimal.json \
  --output-dir output-auto \
  --interchange netcdf \
  --parallel auto
```

Example production MPI run:

```bash
mpiexec -n 4 sprtz run examples/minimal.json \
  --output-dir output-mpi \
  --backend gaussian \
  --interchange netcdf \
  --parallel mpi \
  --gpu-backend auto
```

Particle backend, either by JSON `run.backend: "particles"` or CLI override:

```bash
mpiexec -n 4 sprtz run examples/minimal.json \
  --output-dir output-particles-mpi \
  --backend particles \
  --interchange netcdf \
  --parallel mpi
```

## Software architecture

The parallel abstraction is implemented in:

```text
src/sprtz/parallel/
├── __init__.py
├── gpu.py
├── mpi.py
├── partition.py
├── scheduler.py
└── threads.py
```

The central object is `ParallelContext`. It combines `MPIContext`, `ThreadContext`, and `GPUContext` while preserving serial fallbacks at every level:

```python
from sprtz.parallel import get_parallel_context

ctx = get_parallel_context(
    parallel="auto",
    thread_mode="auto",
    threads_per_rank=4,
    gpu_backend="auto",
)
```

`MPIContext` wraps `MPI.COMM_WORLD` when MPI is active and exposes the same small API when Spritz is running serially:

- `rank`: current rank, or `0` in serial mode.
- `size`: communicator size, or `1` in serial mode.
- `is_root`: true for rank 0.
- `partition(n_items)`: balanced contiguous ownership range for this rank.
- `allgather(value)`: gather one value from every rank.
- `gather_flat(rows)`: gather lists from all ranks and flatten them in rank order.
- `bcast(value, root=0)`: broadcast a value from one rank.
- `barrier()`: synchronize ranks.

The public factory is:

```python
from sprtz.parallel import get_mpi_context

ctx = get_mpi_context("auto")
```

No modeling module imports `mpi4py` directly. This keeps non-MPI installations importable and simplifies testing.

`ThreadContext.map()` gives model code a deterministic local map operation. It is serial unless explicitly configured for `threads`, `processes`, or `auto` with more than one worker. `GPUContext.xp` stores either NumPy or CuPy so dense kernels can be written once and validated against the CPU path.

## Work partitioning

Spritz currently uses static balanced partitioning with contiguous blocks. For `n_items` units of work, `size` MPI ranks, and one `rank`, the 1-D partition is:

```python
base, remainder = divmod(n_items, size)
start = rank * base + min(rank, remainder)
stop = start + base + (1 if rank < remainder else 0)
```

The first `remainder` ranks receive one extra item. This schema has three advantages:

1. It is deterministic and independent of runtime scheduling.
2. It minimizes communication because each rank receives a simple contiguous range.
3. It produces stable output ordering when gathered in rank order.

Example for 10 receptors and 4 ranks:

| Rank | Owned indices | Number of items |
|---:|---:|---:|
| 0 | 0, 1, 2 | 3 |
| 1 | 3, 4, 5 | 3 |
| 2 | 6, 7 | 2 |
| 3 | 8, 9 | 2 |

For gridded workflows, `balanced_tiles_2d(nx, ny, rank, size, halo=0)` provides deterministic row-major 2-D tiles. SpritzMet can keep row partitioning for compatibility and use tile partitioning for future halo-aware WRF downscaling, smoothing, or terrain-correction kernels.

## Stage-specific best models

Spritz uses different parallelization units for different numerical kernels:

| Module | MPI unit | Shared-memory unit | CUDA unit | Communication |
|---|---|---|---|---|
| SpritzMet | 2-D grid tiles with halo; row mode retained | tile rows/subtiles, time slices | WRF interpolation, DEM/LC corrections, diagnostic grid arrays | halo exchange for local operators; gather/write or optional parallel NetCDF. |
| SpritzGaussian | receptor blocks; optional source-receptor 2-D decomposition | local receptor sub-blocks | source/receptor geometry and batched plume arrays | final gather over receptor rows; optional source-dimension reduction. |
| SpritzParticles | source blocks; particle blocks for dominant sources | particle batches and local reductions | particle advection, stochastic offsets, deposition, hit tests | deterministic reduction of receptor/grid totals. |
| SpritzFirefront | stochastic realizations | realization batches or spatial tiles | cellular automaton state arrays | ensemble reduction; optional tile halo exchange. |

## Gaussian backend schema

The Gaussian/non-steady puff backend is implemented in:

```text
src/sprtz/models/spritz.py
```

Parallelization unit: **receptors**.

Optional CUDA unit: **source/receptor geometry arrays**. CuPy accelerates the vector projection from source coordinates to downwind/crosswind distances; stability, depletion, and plume/puff formulas remain scalar and deterministic.

Each rank receives a balanced subset of receptors and evaluates every source for those receptors. The current schema is:

```text
all ranks read configuration and meteorology
        │
        ▼
rank-local receptor partition
        │
        ▼
for each local receptor:
    for each source:
        compute downwind/crosswind coordinates
        compute travel time
        compute plume rise/effective release height
        compute depletion/deposition terms
        compute concentration contribution
        accumulate concentration, dry flux, wet flux
        │
        ▼
all ranks allgather local receptor rows
        │
        ▼
rank 0 writes concentration output
```

This receptor-based decomposition is appropriate because receptor rows are independent after meteorology and configuration have been loaded. It also preserves output semantics: each final row represents one receptor and one time aggregation.

### Communication pattern

The Gaussian backend uses a single collective gather at the end of the concentration calculation:

- Input files are read independently by each rank.
- Intermediate source contributions stay rank-local.
- Final rows are merged with `gather_flat`.
- Rank 0 writes CSV, legacy text, or NetCDF-CF concentration output.

### Numerical reproducibility

The Gaussian backend is deterministic because each receptor row is computed independently. Floating-point summation order is stable within each receptor, and output ordering is defined by rank partitions. The test suite verifies serial and automatic parallel equivalence for the available implementation.

## Particle backend schema

The particle backend is implemented in:

```text
src/sprtz/models/particles.py
```

Parallelization unit: **sources**.

Optional CUDA unit: **particle arrays within each local source**. Travel time, stochastic offsets, loss weights, and receptor hit tests can run on CuPy arrays. Source-level RNG seeds remain independent of MPI rank count.

Each rank receives a balanced subset of emission sources. For each local source, particles are generated and transported using a deterministic per-source random-number stream. The current schema is:

```text
all ranks read configuration and meteorology
        │
        ▼
rank-local source partition
        │
        ▼
for each local source:
    initialize RNG with base_seed + source_index * 1000003
    compute particle count proportional to emission rate
    transport particles through sampled time,z,y,x SpritzMet wind substeps
    apply stochastic horizontal and vertical spread
    apply finite source-size, flare uplift, loss/deposition terms
    accumulate local receptor hit masses
        │
        ▼
all ranks allgather local receptor totals
        │
        ▼
all ranks sum partial totals in the same order
        │
        ▼
rank 0 writes concentration output
```

### Deterministic random seeding

The particle backend uses a per-source seed:

```text
source_seed = base_seed + source_index * 1000003
```

This means each source receives the same random stream regardless of the number of MPI ranks. The final result is therefore reproducible across serial and MPI layouts, subject to ordinary floating-point behavior.

### Why sources rather than particles are partitioned

Partitioning by source has several practical benefits:

- It keeps all particles from a source on the same rank, simplifying source-specific physics.
- It avoids exchanging particle trajectories between ranks.
- It preserves deterministic seeding by source index.
- It works well for multi-source fire, industrial, and area-source cases.

For future very large single-source simulations, a particle-block decomposition could be added. That would require a second deterministic seeding layer by source and block index.

## Workflow-level schema

The high-level workflow is implemented in:

```text
src/sprtz/workflow.py
```

The workflow coordinates SpritzMet, the selected concentration backend, and SpritzPost-style post-processing. The current production workflow is:

```text
rank 0 creates output directory
all ranks synchronize
all ranks load configuration
rank 0 runs SpritzMet meteorology generation
all ranks synchronize
all ranks run Gaussian or particle concentration backend
rank 0 runs SpritzPost post-processing
rank 0 broadcasts the final workflow summary
```

This avoids concurrent writes for shared meteorology and post-processing products while still using MPI for the expensive concentration step.

For WRF-driven SpritzMet downscaling, `downscale_wrf_to_local_grid(...,
parallel="auto"|"mpi")` partitions the target local grid by row, builds each
rank's projected inverse-distance neighbour plan only for its rows, applies DEM
and land-cover corrections on the same row slice, then allgathers the completed
wind, precipitation, diagnostic 10 m wind, 2 m temperature, and 2 m relative
humidity arrays. Use case 01 exposes this as `--parallel auto` or
`--parallel mpi`; output writing remains rank-0/serial through
`write_local_meteorology`.

The academic target for large domains is 2-D tiling:

```text
Global grid G(time, y, x)
│
├── MPI rank r owns tile Tr = [y0:y1, x0:x1] plus halo h
├── CPU workers process subtiles of Tr
└── CUDA kernels evaluate dense cell-wise operations on Tr
```

Recommended dense kernels include WRF-to-local interpolation, terrain correction from DEM, land-cover correction and roughness proxies, diagnostic U10M/V10M preservation, precipitation interpolation, 2 m temperature and relative humidity derivation, and local quality masks.

## File I/O rules

The I/O contract is intentionally conservative.

| File class | Writer | Readers | Notes |
|---|---|---|---|
| Configuration JSON / `.inp` | User | All ranks | Small text inputs; read independently. |
| SpritzMet meteorology NetCDF/JSON | Rank 0 | All ranks | Rank 0 writes, all ranks read after a barrier. |
| Concentration NetCDF/CSV/legacy table | Rank 0 | User / SpritzPost | Rank 0 writes gathered results. |
| CALPUFF-style concentration binary sidecar | Rank 0 | External comparison tools | Exported from the same gathered gridded rows as NetCDF-CF output. |
| Post-processing JSON | Rank 0 | User | Produced after concentration output exists. |
| Visualization figures | Serial scripts or rank 0 | User | Visualization is not currently MPI-parallel. |

Rank 0 only writing is deliberate. It avoids multi-writer NetCDF corruption and keeps the package portable across MPI implementations and filesystems. Future versions may add parallel NetCDF/HDF5 output for very large domains, but that will require optional dependencies and filesystem-specific validation.

An optional HPC extension may collectively write large arrays through parallel NetCDF/HDF5 or PnetCDF only when the Python environment is linked against MPI-enabled HDF5/netCDF4 or PnetCDF and the target filesystem supports collective I/O efficiently. This feature must remain disabled unless detected and explicitly validated.

## NetCDF-CF interoperability

Spritz prefers NetCDF-CF for module interoperability. In a parallel workflow, NetCDF-CF is used as a shared exchange format rather than a parallel write target:

1. SpritzWRF converts/extracts WRF-derived meteorology.
2. SpritzMet downscales or regularizes meteorology onto the modeling grid.
3. Terrain provides terrain fields where required.
4. Spritz Gaussian or particle backend reads the meteorology product on all ranks.
5. Rank 0 writes the concentration NetCDF-CF product.
6. SpritzPost and visualization modules read the final product.

This schema is robust on local disks, shared POSIX filesystems, and typical HPC scratch filesystems.

## MPI environment setup

Install the optional MPI dependency only in environments where MPI is available:

```bash
python -m pip install -e .[mpi]
```

For a full scientific/visual workflow:

```bash
python -m pip install -e .[netcdf,viz,mpi]
```

A working MPI launcher is also required, for example Open MPI, MPICH, Intel MPI, or an HPC site-provided MPI distribution.

Sanity check:

```bash
mpiexec -n 2 python - <<'PY'
from mpi4py import MPI
print(MPI.COMM_WORLD.Get_rank(), MPI.COMM_WORLD.Get_size())
PY
```

Then run Spritz diagnostics:

```bash
sprtz doctor
```

## Batch-scheduler examples

### Slurm

```bash
#!/bin/bash
#SBATCH --job-name=sprtz
#SBATCH --nodes=1
#SBATCH --ntasks=16
#SBATCH --time=00:30:00
#SBATCH --partition=compute

set -euo pipefail

module load python
module load openmpi
source .venv/bin/activate

srun -n 16 sprtz run examples/minimal.json \
  --output-dir output-slurm \
  --backend gaussian \
  --interchange netcdf \
  --parallel mpi
```

### PBS / Torque style

```bash
#!/bin/bash
#PBS -N sprtz
#PBS -l select=1:ncpus=16:mpiprocs=16
#PBS -l walltime=00:30:00

set -euo pipefail
cd "$PBS_O_WORKDIR"
source .venv/bin/activate

mpiexec -n 16 sprtz run examples/minimal.json \
  --output-dir output-pbs \
  --backend particles \
  --interchange netcdf \
  --parallel mpi
```

## Performance considerations

The dominant cost depends on the backend. Let `R` be receptors, `S` sources, `P` particles, `G` grid cells, `E` Firefront ensemble realizations, `T` time steps, `M` MPI ranks, `C` CPU workers per rank, and `A` the accelerator throughput factor.

Approximate dominant costs:

```text
SpritzMet:        O(G × T) / (M × C × A)
SpritzGaussian:   O(R × S × T) / (M × C × A)
SpritzParticles:  O(S × P × R × T) / (M × C × A)
SpritzFirefront:  O(E × G × T) / (M × C × A)
```

Communication terms:

```text
SpritzMet:        halo_exchange + final gather/write
SpritzGaussian:   final receptor gather; optional source-dimension reduction
SpritzParticles:  receptor/grid total reduction
SpritzFirefront:  ensemble statistic reduction
```

The scheduler should prefer decompositions that maximize arithmetic intensity and minimize communication. For Gaussian runs, scaling is best when receptor count is large relative to MPI ranks. For particles, source decomposition scales best with multiple similarly weighted sources; single dominant sources need particle-block decomposition for useful speedup.

## Practical recommendations

Use these rules of thumb:

- Use `serial` for debugging, tutorials, small receptor grids, and CI.
- Use `auto` for didactic scripts and examples that must work on laptops and clusters.
- Use `mpi` in production batch jobs when MPI startup failure should stop the workflow.
- Prefer NetCDF-CF for workflow interoperability.
- Use JSON `concentration_output: "grid"` only at the horizontal and vertical
  resolution needed for the analysis.
- Keep all model inputs on a filesystem visible to every MPI rank.
- Write outputs to a job-specific output directory.
- Compare a small serial and MPI smoke test before launching large jobs.

## Validation checklist

Before accepting a new parallel workflow or backend change, run:

```bash
PYTHONPATH=src python -m compileall -q src tests usecases
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m sprtz doctor
PYTHONPATH=src python -m sprtz run examples/minimal.json \
  --output-dir /tmp/sprtz_parallel_serial \
  --interchange json \
  --parallel serial
PYTHONPATH=src python -m sprtz run examples/minimal.json \
  --output-dir /tmp/sprtz_parallel_auto \
  --interchange json \
  --parallel auto
python scripts/check_release.py
```

When MPI is available, also run:

```bash
mpiexec -n 2 sprtz run examples/minimal.json \
  --output-dir /tmp/sprtz_parallel_mpi \
  --interchange netcdf \
  --parallel mpi
```

For the particle backend, repeat with:

```bash
mpiexec -n 2 sprtz run examples/minimal.json \
  --output-dir /tmp/sprtz_parallel_particles \
  --backend particles \
  --interchange netcdf \
  --parallel mpi
```

Each module-level implementation should cover these test classes as the relevant execution paths mature:

1. Serial baseline test.
2. MPI equivalence test.
3. Shared-memory equivalence test.
4. GPU tolerance test.
5. Mixed MPI plus shared-memory test.
6. Mixed MPI plus GPU test.
7. Deterministic seed and stable output ordering test.
8. Small end-to-end workflow test.

## Current limitations

The current implementation does not yet provide:

- Parallel NetCDF writing.
- Dynamic load balancing.
- Domain decomposition for time-varying puff clouds.
- Particle-block decomposition for one very large source.
- MPI-parallel visualization.

These are future extensions. The current schema prioritizes deterministic behavior, safe file output, and portability.

## Developer notes

When adding a new parallelized module:

1. Keep `mpi4py` imports isolated behind `sprtz.parallel`.
2. Make `serial` the default execution mode.
3. Use `MPIContext.partition()` for deterministic static decomposition.
4. Use rank-local accumulation and a small number of collective operations.
5. Let rank 0 perform shared file writes.
6. Add tests for serial equivalence or deterministic behavior.
7. Document the unit of parallel work: receptors, sources, time steps, tiles, or particles.
8. Update this file when the schema changes.

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
- Wilson, G., Aruliah, D. A., Brown, C. T., Hong, N. P. C., Davis, M., Guy, R. T., Haddock, S. H. D., Huff, K. D., Mitchell, I. M., Plumbley, M. D., Waugh, B., White, E. P., and Wilson, P. (2014). Best practices for scientific computing. PLOS Biology, 12(1), e1001745. https://doi.org/10.1371/journal.pbio.1001745
- Sandve, G. K., Nekrutenko, A., Taylor, J., and Hovig, E. (2013). Ten simple rules for reproducible computational research. PLOS Computational Biology, 9(10), e1003285. https://doi.org/10.1371/journal.pcbi.1003285
