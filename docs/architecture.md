# Architecture

![Spritz architecture](assets/spritz_architecture.svg)

Spritz is organized as a clean-room Python suite with one shared configuration
model and independent model components. Every production component exposes a
small Python API and a deterministic command-line surface.

## Input Configuration Layer

Spritz accepts JSON configuration, tolerant INP-style legacy control files, and
CLI options. JSON remains the richest format because it can carry domain,
terrain, meteorology, source, receptor, workflow, and provenance settings in one
portable document.

## Orchestration Layer

`sprtz run` coordinates the standard workflow:

1. optional Terrain acquisition and GEO generation;
2. SpritzMet meteorology;
3. unified Spritz Gaussian or particle dispersion;
4. SpritzPost statistics.

The same modules can be invoked directly through their console scripts or Python
`run(...)` functions for batch/HPC integration.

## Meteorological Preprocessing

SpritzWRF reads WRF-oriented NetCDF inputs and normalizes clean-room near-surface
wind and precipitation fields. SpritzMet creates diagnostic meteorology on the
model grid, supports WRF-to-local-grid interpolation in didactic use cases, and
writes NetCDF-CF or JSON outputs. The meteorology layer remains
optional-dependency friendly:
NetCDF support is used when installed, while JSON fallback keeps tests and
lightweight deployments deterministic.

## Terrain And Land-Use Preprocessing

Terrain now has two layers:

- `sprtz.models.terrain` keeps the existing local ASCII-grid interpolation API
  and `terrain` CLI for backward compatibility.
- `sprtz.terrain` provides production-style acquisition concepts: local and
  online provider interfaces, deterministic cache metadata, AOI/domain handling,
  continuous DEM resampling, categorical land-cover resampling, land-cover to
  Spritz land-use remapping, surface-parameter derivation, and NetCDF-CF/JSON GEO
  output with provenance.

MakeGeo and CTGPROC remain lightweight clean-room helpers for GEO tables and
category aggregation.

## Dispersion Engines

The unified Spritz concentration layer selects the Gaussian or particle backend
from JSON `run.backend` or CLI `--backend`. The Gaussian backend supports puff
and plume modes, finite source dimensions, effective release height, dry/wet
deposition fluxes, first-order losses, precipitation washout, source/event time
windows, firefighter emission factors, deterministic receptor outputs, and
model-grid 3D concentration fields. The particle backend consumes the same
configuration and meteorology exchange products, honors the same time-window and
washout controls, writes the same output schema, and is deterministic for a
fixed seed.

## Post-Processing And Outputs

SpritzPost computes maxima, averages, ranked values, percentiles, and threshold
summaries from concentration/deposition outputs. Module exchange prefers
NetCDF-CF. Concentration NetCDF files keep the receptor table and, for complete
grid outputs, include `concentration_field(time, field_z, field_y, field_x)`.
CSV, JSON, and legacy-style outputs remain available for portability and
migration workflows.

## Visualization

`sprtz-plot` renders local or geographic concentration maps from CSV, JSON, or
NetCDF-CF outputs. It supports receptor latitude/longitude, local-grid to WGS84
transforms, high-DPI output, offline raster basemaps, and explicit opt-in web
tile basemaps.

## HPC And MPI Compatibility

`sprtz.parallel.mpi` keeps MPI optional. Serial runs use the same API as MPI
runs. MPI-enabled workflows partition receptor computations, gather results, and
write shared outputs only on rank 0 to avoid multi-writer NetCDF corruption.

## Clean-Room Rule

The repository implements behavior from first principles and public component
roles. It does not translate proprietary routines, redistribute proprietary data,
or claim regulatory equivalence without independent validation.
