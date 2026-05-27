# Architecture

PyPuff uses a shared configuration and I/O layer plus independent model components. Every component exposes a `run(...)` function and pure computational functions suitable for tests.

```text
Fortran-style .inp or JSON config
        |
        +-> CALWRF metadata adapter for WRF/NetCDF inputs
        +-> CTGPROC land-use category aggregation
        +-> MAKEGEO terrain/land-use GEO table builder
        |
        v
CALMET diagnostic meteorology -> NetCDF-CF meteo.nc
        |
        +-> PyPuff Gaussian puff/deposition backend -> concentration.nc/csv/legacy table
        +-> PyPuff particle backend -------> concentration.nc/csv/legacy table
        |
        v
CALPOST statistics -> post.json
        |
        v
Visualization -> publication figures
```

## Clean-room rule

The repository implements behavior from first principles and public component roles. It does not translate original Fortran routines or redistribute upstream data.

## Interoperability rule

NetCDF-CF is preferred for new module-to-module exchange. Legacy control files and tabular outputs remain supported to ease migration from Fortran-era workflows.


## Parallel layer

`pypuff.parallel.mpi` contains the optional MPI abstraction used by concentration backends. It exposes serial-safe helpers, balanced partitioning, gather/broadcast operations, and root-only output coordination. The layer keeps `mpi4py` optional so every module remains importable on non-HPC systems. The complete execution schema is documented in `docs/parallelization.md`.

## Numerical kernels

The Gaussian backend can operate in `puff` or `plume` mode. The default `puff` mode uses finite source dimensions, effective release height, first-order loss/deposition, and dry/wet flux outputs. The particle backend uses the same input and output schema and is deterministic for a fixed seed.

## PyWRF and PyMET in operational use cases

Starting with v0.4.2, high-resolution meteorological use cases use explicit clean-room module names.  `pypuff.models.pywrf` implements the former CALWRF role: WRF NetCDF access, field normalization, and meteo@uniparthenope WRF5 d03 downloading.  `pypuff.models.pymet` implements the former CALMET local interpolation role: centered local grids, deterministic vector interpolation, and NetCDF-CF meteorological output.

Use case 01 calls PyWRF first and PyMET second.  Use case 02 reuses the same wind product before building a wildfire/arson source configuration.  This keeps the use cases consistent and prevents ad-hoc WRF parsing in scenario scripts.


## PyTerrel terrain preprocessing

PyTerrel is included as `pypuff.models.pyterrel` and the `pyterrel` CLI. It provides clean-room TERREL-role terrain interpolation and NetCDF-CF/JSON terrain outputs for PyMET, MAKEGEO, and dispersion workflows.
