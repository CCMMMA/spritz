# Production readiness

This repository is production-ready as Python software infrastructure: it is installable, typed, deterministic for a given input, covered by unit tests, has explicit exceptions, atomic writes for core outputs, CLI error handling, CI, and coherent documentation.

It is not claimed to be a regulatory replacement for any third-party modeling system. Production scientific use requires project-specific verification, validation against accepted reference cases, and review by qualified atmospheric-science practitioners.

## Operational properties

- Pure Python package with optional extras for NetCDF, visualization, MPI, and geospatial Terrain acquisition.
- Shared configuration model across all suite modules.
- Tolerant Fortran-style control-file parser for migration inputs.
- Preferred NetCDF-CF module interoperability.
- Deterministic Gaussian and particle backends.
- Stable CSV/JSON/legacy table output pathways.
- Optional NetCDF-CF/JSON fallback 3D concentration fields for model-grid runs.
- Time-aware source windows, firefighter action windows, source height above
  ground level, material metadata, and precipitation washout are represented in
  the ordinary JSON configuration.
- GitHub Actions CI for Python 3.10, 3.11, and 3.12.

## Recommended deployment

Use a virtual environment, install with `pip install .[netcdf,viz]`, or `pip install .[geo,netcdf,viz]` when Terrain acquisition must read GeoTIFF/COG products. Commit exact input files with a run manifest, and archive output artifacts with the package version and Git commit.

For WRF-driven wet-removal studies, archive the WRF file, the selected
`time_index` and `level_index`, the SpritzMet 4D wind product
(`time,z,y,x`), the surface `precipitation_rate(time,y,x)` product, and the
configured `precipitation_washout_coefficient_s_per_mm_h`. For fire or chimney
cases, record source `height_agl_m`, material preset or explicit emission
assumptions, event start/end datetimes, and any firefighter-action period.


## Parallel production execution

The suite supports optional MPI execution with `mpi4py` for the Gaussian and particle concentration backends. Serial execution remains the default. In MPI workflows, shared output files are written by rank 0 after deterministic gathers, preventing concurrent writes to CSV, JSON, legacy text, NetCDF-CF files, or clean-room CALPUFF-style binary sidecars.

## Runtime diagnostics

Run the built-in diagnostic command after installation and in operational containers:

```bash
sprtz doctor
sprtz doctor --require-netcdf --require-viz
# add --require-mpi on MPI production nodes
```

The command is local-only and checks Python version, required dependencies, optional NetCDF/visualization/MPI extras when requested, importability, and the typed-package marker. It does not contact external services or write files.

## Release hygiene

Before tagging a release, run:

```bash
python -m compileall src tests
python -m pytest -q
find . -type d -name __pycache__ -prune -exec rm -rf {} +
find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
python scripts/check_release.py
```

The release check verifies required docs, use-case documentation, typed package metadata, and absence of Python bytecode/cache directories in the repository archive.


## Terrain Preprocessing

Terrain is included as `sprtz.models.terrain`, the backward-compatible `terrain` CLI, and the provider-based `sprtz-terrain fetch` workflow. Offline local rasters are supported without network access. Online Copernicus DEM and ESA WorldCover providers require explicit opt-in and deployment-specific catalog/credential configuration. Derived GEO products must preserve provenance metadata for source datasets, CRS, resampling methods, cache key, and Spritz software version.


## Use-case packaging boundary

The root-level didactic use cases are not package modules and are not exposed as installed CLI entry points. This keeps production suite APIs separated from educational scenario orchestration.
