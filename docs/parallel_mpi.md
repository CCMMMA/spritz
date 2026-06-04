# MPI parallel execution

For the full parallelization schema, work partitioning rules, I/O contract, and HPC batch examples, see [`parallelization.md`](parallelization.md).

Spritz supports optional MPI parallelism through `mpi4py` for the unified concentration-producing backends:

- `sprtz.models.spritz`, the Gaussian Spritz screening backend;
- `sprtz.models.particles`, the particle-based Spritz backend selected by
  JSON `run.backend: "particles"` or CLI `--backend particles`.

Serial execution remains the default and requires no MPI libraries.  MPI support is activated only when the package is installed with the `mpi` extra and commands are launched with an MPI runtime.

## Installation

```bash
python -m pip install -e .[netcdf,viz,mpi]
```

On HPC systems, install `mpi4py` against the same MPI implementation used by the scheduler or environment modules.

## CLI usage

Serial default:

```bash
sprtz run examples/minimal.json --output-dir output --interchange netcdf
```

Automatic MPI when launched with multiple ranks:

```bash
mpiexec -n 4 sprtz run examples/minimal.json --output-dir output-mpi --interchange netcdf --parallel auto
```

Required MPI mode, which fails immediately if `mpi4py` is unavailable:

```bash
mpiexec -n 4 sprtz run examples/minimal.json --output-dir output-mpi --backend particles --parallel mpi
```

Direct model commands also accept the same flag:

```bash
mpiexec -n 4 spritz --config examples/minimal.json --meteo output/meteo.nc --output output/concentration.nc --format netcdf --parallel mpi
mpiexec -n 4 spritz --config examples/minimal.json --meteo output/meteo.nc --output output/particle_concentration.nc --format netcdf --backend particles --parallel mpi
```

`sprtz-particles` remains a compatibility alias for older particle-only scripts.

## Parallelization strategy

The Gaussian backend partitions receptors across ranks, computes local receptor concentrations, gathers rows in rank order, and writes the final output on rank 0 only.

The particle backend partitions sources across ranks and uses per-source random seeds. This makes the particle result deterministic with respect to MPI partitioning: changing the number of ranks should not change the random stream used for a given source.

In end-to-end workflows, rank 0 produces shared SpritzMet and SpritzPost files. All ranks participate in the concentration backend, and rank 0 writes the concentration file.

## File semantics

NetCDF-CF remains the preferred interchange format. MPI runs write exactly one
concentration output file from rank 0, avoiding multi-writer NetCDF corruption.
When grid output is requested, that one file contains both receptor-table
variables and `concentration_field(time, field_z, field_y, field_x)`. Future
versions may add parallel NetCDF output for very large domains, but the current
implementation prioritizes deterministic, portable HPC behavior.

## Operational notes

Use `--parallel auto` in scripts that must also work on laptops. Use `--parallel mpi` in production batch jobs when MPI is expected and a missing MPI environment should be treated as an error.
