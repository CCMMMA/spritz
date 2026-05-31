# Architecture

Sprtz uses a shared configuration and I/O layer plus independent model components. Every component exposes a `run(...)` function and pure computational functions suitable for tests.

```text
Fortran-style .inp or JSON config
        |
        +-> SpritzWRF metadata adapter for WRF/NetCDF inputs
        +-> CTGPROC land-use category aggregation
        +-> MakeGeo terrain/land-use GEO table builder
        |
        v
SpritzMet diagnostic meteorology -> NetCDF-CF meteo.nc
        |
        +-> Spritz Gaussian puff/deposition backend -> concentration.nc/csv/legacy table
        +-> Sprtz particle backend ------> concentration.nc/csv/legacy table
        |
        v
SpritzPost statistics -> post.json
        |
        v
Visualization -> publication figures
```

## Clean-room rule

The repository implements behavior from first principles and public component roles. It does not translate original Fortran routines or redistribute upstream data.

## Interoperability rule

NetCDF-CF is preferred for new module-to-module exchange. Legacy control files and tabular outputs remain supported to ease migration from Fortran-era workflows.


## Parallel layer

`sprtz.parallel.mpi` contains the optional MPI abstraction used by concentration backends. It exposes serial-safe helpers, balanced partitioning, gather/broadcast operations, and root-only output coordination. The layer keeps `mpi4py` optional so every module remains importable on non-HPC systems. The complete execution schema is documented in `docs/parallelization.md`.

## Numerical kernels

The Gaussian backend can operate in `puff` or `plume` mode. The default `puff` mode uses finite source dimensions, effective release height, first-order loss/deposition, and dry/wet flux outputs. The particle backend uses the same input and output schema and is deterministic for a fixed seed.

## SpritzWRF and SpritzMet in operational use cases

High-resolution meteorological use cases use explicit clean-room module names. `sprtz.models.spritzwrf` handles WRF NetCDF access, field normalization, and meteo@uniparthenope WRF5 d03 downloading. `sprtz.models.spritzmet` handles centered local grids, deterministic vector interpolation, and NetCDF-CF meteorological output.

Use case 01 calls SpritzWRF first and SpritzMet second.  Use case 02 reuses the same wind product before building a wildfire/arson source configuration.  This keeps the use cases consistent and prevents ad-hoc WRF parsing in scenario scripts.


## Terrain Preprocessing

Terrain is included as `sprtz.models.terrain` and the `terrain` CLI. It provides clean-room terrain interpolation and NetCDF-CF/JSON terrain outputs for SpritzMet, MakeGeo, and dispersion workflows.
