# AGENTS.md

This file gives repository-specific instructions for AI coding agents and human contributors working on Sprtz.

## Project identity and clean-room boundary

Sprtz is an MIT-licensed, clean-room, pure Python atmospheric puff and dispersion modeling toolkit. It is inspired by the public workflows and file conventions of established puff-modeling suites, but it must not contain copied, translated, mechanically ported, or reverse-engineered proprietary source code.

When making changes:

- Do not copy source code, proprietary examples, proprietary parameter tables, manuals, or binary assets from third-party atmospheric modeling suites.
- Do not present Sprtz as an official third-party release or regulatory-equivalent replacement.
- Keep compatibility language precise: Sprtz supports compatible workflows, tolerant control-file parsing, NetCDF-CF interchange, and clean-room numerical implementations.
- Preserve the MIT license and the `NOTICE` clean-room statement.

## Repository layout

Key paths:

- `src/sprtz/` — package source code.
- `src/sprtz/models/` — model components, including SpritzWRF, SpritzMet, Spritz Gaussian, particle backend, CTGPROC, MakeGeo, Terrain, and visualization.
- `src/sprtz/io/` — JSON, legacy-style text, and NetCDF-CF I/O helpers.
- `usecases/` — documented runnable didactic use-case folders. Use cases must not be packaged under `src/sprtz/`.
- `examples/` — minimal stable examples used by docs and tests.
- `docs/` — architecture, validation, I/O, MPI, numerical, visualization, use-case, and production-readiness documentation.
- `tests/` — pytest suite.
- `scripts/check_release.py` — release hygiene checker.
- `tools/` — miscellaneous developer and maintenance scripts that are not part of
  the installable package or public CLI.

## Development environment

Use Python 3.10 or newer.

Recommended local setup:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .[dev,netcdf,viz]
```

Optional MPI support:

```bash
python -m pip install -e .[mpi]
```

MPI execution must remain optional. Serial execution must work without `mpi4py`, without `netCDF4`, and without `matplotlib` unless a feature explicitly requires those optional extras.

When adding, removing, or changing runtime, optional, development, or tooling
dependencies in `pyproject.toml` or setup instructions, keep the root
`requirements.txt` file updated with matching install requirements.

## Required checks before completing changes

Run these from the repository root:

```bash
python -m compileall -q src tests
python -m pytest -q
python -m sprtz doctor
python -m sprtz validate examples/minimal.json
python -m sprtz run examples/minimal.json --output-dir /tmp/sprtz_smoke --interchange json
find . -type d -name __pycache__ -prune -exec rm -rf {} +
rm -rf .pytest_cache .mypy_cache .ruff_cache build dist
find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete
python scripts/check_release.py
```

For NetCDF-related changes, also run when `netCDF4` is installed:

```bash
python -m sprtz run examples/minimal.json --output-dir /tmp/sprtz_smoke_nc --interchange netcdf
```

For MPI-related changes, also run when `mpi4py` and an MPI launcher are available:

```bash
mpiexec -n 2 python -m sprtz run examples/minimal.json --output-dir /tmp/sprtz_smoke_mpi --parallel mpi --interchange json
```

## Coding standards

- Prefer small, typed, deterministic functions.
- Use standard-library facilities unless an optional scientific dependency is already declared.
- Keep optional dependencies optional and import them lazily.
- Keep CLI behavior deterministic and suitable for batch/HPC runs.
- Use the standard `logging` module for all operational, diagnostic, and user-facing runtime messages; do not use `print()` in package modules, scripts, or use-case programs.
- Use unit tests for new behavior and bug fixes. Keep tests deterministic and
  focused on public behavior, numerical invariants, parsing, validation, and
  fallback paths.
- Write outputs atomically where practical.
- Only rank 0 should write shared output files in MPI workflows.
- Preserve fallback paths for environments without NetCDF, MPI, or visualization dependencies.
- Avoid hidden network access except in explicit downloader commands or functions documented as such.
- Add step-by-step comments in scientifically sensitive code paths, especially terrain acquisition, reprojection, resampling, land-cover remapping, surface-parameter derivation, NetCDF writing, and provenance capture.

## Numerical-modeling expectations

Sprtz is scientific software. Numerical changes must be documented and tested.

When changing physics or numerics:

- Add or update tests for conservation, monotonicity, deterministic behavior, or known limiting cases.
- Document assumptions in `docs/numerical_model.md` or the relevant use-case documentation.
- Keep empirical coefficients visible, named, and configurable where possible.
- Avoid hard-coding undocumented constants in deep implementation code.
- Do not claim regulatory equivalence without external validation.

## SpritzWRF/SpritzMet dynamical downscaling

WRF-driven downscaling must preserve the generic SpritzWRF -> SpritzMet
pipeline rather than adding use-case-only physics. Use case 01 may demonstrate
the workflow, but production behavior belongs in `src/sprtz/models/spritzwrf.py`
and `src/sprtz/models/spritzmet.py`.

When changing WRF ingestion or local-grid downscaling:

- Keep WRF extraction clean-room and dimension-aware. `time_index` and
  `level_index` must remain independent, and `None` must preserve the full
  corresponding axis where supported.
- Reuse the local azimuthal-equidistant inverse-distance neighbour plan for all
  WRF-derived fields on the same target grid so wind, precipitation,
  diagnostic 10 m wind, 2 m temperature, and 2 m humidity share the same
  horizontal sampling geometry.
- Preserve diagnostic `U10M`/`V10M` as `time,y,x` outputs whenever available.
  Treat them as wind at 10 m above local ground. For height-above-ground
  vertical grids, anchor at 10 m. For height-above-sea-level grids with DEM,
  anchor at `DEM + 10 m`. Without DEM, apply the sea-level equality only on
  land-cover cells classified as water, where sea surface height is assumed
  approximately equal to mean sea level.
- Do not assume `wind_speed_10m == wind_speed(z=10 m above sea level)` on land.
  That equality is valid only where the model vertical reference and local
  ground/sea surface reference coincide. Over generic terrain, `U10M`/`V10M`
  are 10 m above local ground and should anchor the vertical profile at
  `ground elevation + 10 m` when the grid is above sea level.
- Avoid simple linear-only vertical interpolation for WRF wind downscaling.
  When physical levels are known, constrain vertical profiles with a documented
  wind-shear formulation using height above terrain, DEM elevation, and
  land-cover roughness. Keep the constraint bounded, preserve useful WRF model
  shear through blending, and mask above-sea-level wind levels below DEM as
  `NaN` before output.
- Extract WRF `T2`/equivalent fields as `temperature_2m_c` in Celsius. Extract
  `RH2`/equivalent fields as `relative_humidity_2m` as a unitless `0..1` rate.
  If direct RH is absent, deriving RH from `Q2`, surface pressure, and `T2` is
  acceptable when documented and tested.
- Use DEM elevation for 2 m temperature lapse-rate correction, and recompute
  2 m relative humidity by preserving vapor pressure through that temperature
  correction. Land cover should enter deterministic downscaling through
  documented roughness/precipitation adjustments unless a new thermodynamic
  land-cover correction is explicitly justified, named, bounded, and tested.
- Use DEM and land-cover inputs whenever they are supplied to
  `downscale_wrf_to_local_grid`; output metadata must state whether each was
  used and for which adjustment family.
- Keep optional MPI parallelism behind `sprtz.parallel`. WRF-to-local-grid
  downscaling may partition target rows across ranks, but serial output must
  remain equivalent and shared NetCDF/JSON writes must be rank-0 only.
- Update NetCDF-CF output, JSON fallback payloads, `tools/plotter.py` where
  relevant, tests, `docs/numerical_model.md`, `docs/spritzwrf_spritzmet.md`,
  use-case documentation, and README whenever WRF-derived downscaled fields or
  metadata conventions change.

## Scientific reproducibility and provenance

All downloaded or derived geospatial products must carry provenance sufficient to
reproduce or audit the run. Terrain/GEO outputs must include, when relevant:

- `dem_source`, `dem_dataset`, `dem_resolution`, `dem_access_date`;
- `landuse_source`, `landuse_dataset`, `landuse_year`, `landuse_resolution`;
- `source_crs`, `target_crs`;
- `resampling_dem`, `resampling_landuse`;
- `cache_key`, `software_version`.

Keep DEM, DTM, and DSM terminology precise. Keep land cover distinct from land
use. Never bilinearly interpolate categorical land-cover classes; use nearest
neighbor or a documented majority/aggregation method.

## Configuration and I/O conventions

Sprtz should prefer NetCDF-CF for module interoperability while retaining tolerant JSON and legacy-style input support.

Use a single shared `config.json` text for Spritz component configuration where
practical. Runnable shell/use-case scripts may expose an optional
`--config config.json`; when the same option appears in both JSON and on the
command line, the command-line value has priority.

All Sprtz-produced NetCDF files must follow strict CF conventions for
coordinates, dimensions, units, and metadata. Any file with a time dimension
must provide a CF-compliant `time` coordinate variable with absolute UTC units
when a physical datetime is known; do not infer scientific datetimes from file
or directory names. WRF valid time must be managed by SpritzWRF from WRF/CF time
metadata such as `Times`, CF `time` units, or explicit WRF global time
attributes, and then propagated to downstream SpritzMet and dispersion NetCDF
outputs.

When adding new fields:

- Update `src/sprtz/config.py`.
- Update JSON examples and, where relevant, legacy `.inp` examples.
- Update NetCDF-CF metadata and JSON fallback behavior.
- Update `tools/plotter.py` and `docs/plotter.md` whenever produced NetCDF
  formats, variables, dimensions, coordinates, or metadata conventions change.
- Update tests and documentation.
- Preserve unknown legacy-control-file keys where the tolerant parser already supports them.

## Terrain data acquisition rules

Terrain has two compatible surfaces:

- `src/sprtz/models/terrain.py` and the `terrain` CLI preserve the lightweight
  local ASCII-grid workflow.
- `src/sprtz/terrain/` and `sprtz-terrain fetch` implement provider-based DEM
  and land-cover acquisition, cache metadata, regridding, land-use remapping,
  surface parameters, and GEO output.

When changing Terrain:

- Local raster workflows must work without network access and without optional
  geospatial dependencies.
- Online providers must require explicit user opt-in, clear configuration, and
  actionable errors for missing network access, credentials, catalogs, CRS
  support, or optional packages.
- Tests must not contact external services unless guarded by an explicit
  environment variable such as `SPRTZ_RUN_NETWORK_TESTS=1`.
- Preserve exact grid alignment between Terrain, SpritzMet, and dispersion
  outputs. Validate dimensions, spacing, CRS/projection choices, nodata values,
  and empty or invalid AOIs.
- Keep cache keys deterministic and include provider, dataset/version/year,
  AOI/tile identity, resolution, CRS, and source timestamp or retrieval date
  where available.

## Use-case conventions

Each use case must remain outside the installable suite namespace and have a runnable documented folder under `usecases/NN_name/`. Shared didactic helpers may live directly under `usecases/`, but do not add `src/sprtz/usecases/` or use-case entry points to `pyproject.toml`.

All use cases must treat the repository-level `data/` directory as their data
root for file I/O. Read inputs from paths under `data/` and write generated
use-case products under `data/` unless the user explicitly supplies another
path.

Any date-time used as a script argument or script parameter must use the compact
UTC format `YYYYMMDDZhhmm`, for example `20260601Z0000`. Keep this format in
CLI help, examples, use-case docs, tests, and downloader instructions whenever
users pass date-time values to scripts.

Use-case documentation should include:

- Purpose and scientific scope.
- Inputs and outputs.
- CLI examples.
- Data requirements.
- Assumptions and limitations.
- Production checklist.

Use case `01_high_resolution_wind_field` must route WRF ingestion through SpritzWRF and meteorological interpolation through SpritzMet. The meteo@uniparthenope downloader must follow this URL pattern:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

## Documentation rules

Keep documentation coherent with the current package name, CLI names, and version.

- Use `Sprtz` for the project name.
- Use `sprtz` for the Python package and main CLI.
- Use `SpritzWRF` for WRF ingestion and `SpritzMet` for meteorological interpolation.
- Use `Spritz` for the Gaussian dispersion model and `sprtz` for the package/CLI.
- Keep examples runnable from the repository root.
- Keep README, docs, examples, CLI help, and tests synchronized whenever public
  APIs or user-facing commands change.
- Document public APIs and CLI options, including optional dependencies and
  network requirements.
- End each documentation file with a bibliographic references section when
  references are needed. Use only peer-reviewed journal articles and conference
  proceedings as bibliographic sources; do not cite non-peer-reviewed web pages,
  manuals, blogs, vendor pages, or proprietary documentation as bibliography
  entries.

## Release hygiene

Release archives must not include generated caches or build artifacts.

Forbidden in release trees:

- `build/`
- `dist/`
- `.pytest_cache/`
- `.mypy_cache/`
- `.ruff_cache/`
- `__pycache__/`
- `*.pyc` or `*.pyo`
- large downloaded operational data files, especially NetCDF files

Run `python scripts/check_release.py` before packaging.

## Safe editing priorities

When improving the repository, prefer this order:

1. Preserve public APIs and CLI compatibility.
2. Preserve deterministic scientific outputs.
3. Strengthen validation and error messages.
4. Update tests.
5. Update docs.
6. Keep optional dependencies optional.



## Terrain and didactic use cases

Terrain is a core clean-room suite model under `src/sprtz/models/terrain.py` and covers terrain interpolation/preprocessing. Didactic use cases must remain under the repository-level `usecases/` folder only. Do not add `src/sprtz/usecases` or install use-case entry points; use-case scripts should import production suite APIs and keep scenario orchestration outside the package namespace.

## SpritzFire coding rules

- SpritzFire code must remain clean-room and must not copy proprietary fire-model source, parameter tables, or manuals.
- MPI is optional. Serial fire spread must run without `mpi4py`, `netCDF4`, `scipy`, `pandas`, `numba`, or GPU libraries.
- Fire constants must be named at module scope, not embedded in loops.
- RandomFront spotting runs after each CA step and must not mutate the nominal transition table.
- FIRMS MAP_KEY values must never be hard-coded or logged in plaintext.
- Buoyancy correction is one-way fire-to-wind and must not mutate input arrays.
- GPU backend detection must be lazy and fall back to NumPy on any error.
- SpritzMet MPI domain decomposition is independent from SpritzFire realization splitting.
