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
- Write outputs atomically where practical.
- Only rank 0 should write shared output files in MPI workflows.
- Preserve fallback paths for environments without NetCDF, MPI, or visualization dependencies.
- Avoid hidden network access except in explicit downloader commands or functions documented as such.

## Numerical-modeling expectations

Sprtz is scientific software. Numerical changes must be documented and tested.

When changing physics or numerics:

- Add or update tests for conservation, monotonicity, deterministic behavior, or known limiting cases.
- Document assumptions in `docs/numerical_model.md` or the relevant use-case documentation.
- Keep empirical coefficients visible, named, and configurable where possible.
- Avoid hard-coding undocumented constants in deep implementation code.
- Do not claim regulatory equivalence without external validation.

## Configuration and I/O conventions

Sprtz should prefer NetCDF-CF for module interoperability while retaining tolerant JSON and legacy-style input support.

When adding new fields:

- Update `src/sprtz/config.py`.
- Update JSON examples and, where relevant, legacy `.inp` examples.
- Update NetCDF-CF metadata and JSON fallback behavior.
- Update tests and documentation.
- Preserve unknown legacy-control-file keys where the tolerant parser already supports them.

## Use-case conventions

Each use case must remain outside the installable suite namespace and have a runnable documented folder under `usecases/NN_name/`. Shared didactic helpers may live directly under `usecases/`, but do not add `src/sprtz/usecases/` or use-case entry points to `pyproject.toml`.

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
