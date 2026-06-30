# Parallelization schema

Spritz uses an optional MPI parallelization layer designed for deterministic atmospheric-dispersion workflows on both laptops and HPC clusters. The same code path can run in serial mode, in automatic MPI mode, or in explicit MPI mode without changing the scenario configuration files. Backend selection can live in JSON `run.backend` or be overridden with `--backend`.

Spritz also supports optional CUDA acceleration through CuPy. GPU execution is requested with `--gpu-backend auto` or `--gpu-backend cupy`; CPU NumPy remains the default and always works without CUDA libraries.

This document describes the production execution schema, how work is partitioned, which files are read and written by each rank, and how to run and validate parallel jobs.

## Goals

Spritz parallelization follows five design goals.

1. **Serial first**: every model must run without MPI or `mpi4py` installed.
2. **Optional HPC acceleration**: MPI is enabled only when requested or when `--parallel auto` detects a multi-rank communicator.
3. **Deterministic results**: serial and parallel runs should produce equivalent outputs for the same backend, configuration, and random seed.
4. **Safe output writing**: only rank 0 writes shared concentration, meteorology, post-processing, and workflow files.
5. **Clean interoperability**: NetCDF-CF remains the preferred file exchange format between SpritzWRF, SpritzMet, Terrain, Spritz, SpritzPost, and the use-case scripts.

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
└── mpi.py
```

The central object is `MPIContext`. It wraps `MPI.COMM_WORLD` when MPI is active and exposes the same small API when Spritz is running serially:

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

## Work partitioning

Spritz currently uses static balanced partitioning with contiguous blocks. For `n_items` units of work, `size` MPI ranks, and one `rank`, the partition is:

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

## Stage-specific best models

Spritz uses different parallelization units for different numerical kernels:

| Stage | MPI unit | GPU unit | Reason |
|---|---|---|---|
| SpritzMet | spatial grid rows, including WRF-to-local-grid downscaling | local grid-array operations | meteorology is cell-wise gridded downscaling. |
| Spritz Gaussian | receptors | source/receptor vector geometry | receptor rows are independent after meteorology is known. |
| Spritz particles | sources | particles for each local source | source RNG streams stay deterministic across MPI sizes. |
| SpritzFire | stochastic realizations | CA arrays per rank | ensemble realizations are independent; one GPU per rank avoids communication. |

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
    transport particles with mean wind and stochastic spread
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

## File I/O rules

The I/O contract is intentionally conservative.

| File class | Writer | Readers | Notes |
|---|---|---|---|
| Configuration JSON / `.inp` | User | All ranks | Small text inputs; read independently. |
| SpritzMet meteorology NetCDF/JSON | Rank 0 | All ranks | Rank 0 writes, all ranks read after a barrier. |
| Concentration NetCDF/CSV/legacy table | Rank 0 | User / SpritzPost | Rank 0 writes gathered results. |
| Post-processing JSON | Rank 0 | User | Produced after concentration output exists. |
| Visualization figures | Serial scripts or rank 0 | User | Visualization is not currently MPI-parallel. |

Rank 0 only writing is deliberate. It avoids multi-writer NetCDF corruption and keeps the package portable across MPI implementations and filesystems. Future versions may add parallel NetCDF/HDF5 output for very large domains, but that will require optional dependencies and filesystem-specific validation.

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

The dominant cost depends on the backend.

For the Gaussian backend, the approximate operation count is:

```text
O(number_of_receptors × number_of_sources)
```

Since receptors are partitioned, scaling is best when the receptor count is
large relative to the number of MPI ranks. For gridded 3D field output, the
effective receptor count is `nx × ny × number_of_field_z_levels`.

For the particle backend, the approximate operation count is:

```text
O(number_of_sources × number_of_particles × number_of_receptors)
```

Since sources are partitioned, scaling is best when there are multiple sources
with similar emission-weighted particle counts. Gridded 3D field output
increases the receptor-distance checks by `nx × ny × number_of_field_z_levels`.
For a single dominant source, the current source-partitioning schema provides
limited speedup.

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
