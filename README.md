# PyPuff

PyPuff is a GitHub-ready, clean-room, pure Python 3 project inspired by the CALPUFF modeling system and the packaging style of PyTerrel/PyMakegeo.

It provides shared configuration, legacy-control parsing, NetCDF-CF interoperability, command-line tools, examples, tests, a Gaussian puff dispersion backend, a particle-based alternative backend, CALPOST-style postprocessing, and publishing-quality visualization.

> Status: beta production software infrastructure. This repository does **not** contain, translate, embed, or redistribute original CALPUFF Fortran sources, executables, manuals, sample data, or proprietary parameter tables.

## Components

| Command | Module | Role |
| --- | --- | --- |
| `pycalwrf` | `pypuff.models.calwrf` | Legacy-compatible WRF/NetCDF metadata adapter. |
| PyWRF API | `pypuff.models.pywrf` | Clean-room WRF extraction/downloader, former CALWRF role. |
| PyMET API | `pypuff.models.pymet` | Clean-room local diagnostic meteorology/downscaling, former CALMET role. |
| `pyterrel` | `pypuff.models.pyterrel` | Clean-room terrain interpolation/preprocessing, former TERREL role. |
| `pyctgproc` | `pypuff.models.ctgproc` | Land-use category aggregation. |
| `pymakegeo-lite` | `pypuff.models.makegeo` | Terrain/land-use GEO table builder. |
| `pycalmet` | `pypuff.models.calmet` | Diagnostic gridded meteorology builder. |
| `pypuff-model` | `pypuff.models.calpuff` | Gaussian puff dispersion and deposition kernel. |
| `pypuff-particles` | `pypuff.models.particles` | Particle-based PyPuff alternative using the same inputs/outputs. |
| `pycalpost` | `pypuff.models.calpost` | Receptor statistics and threshold summaries. |
| `pypuff-plot` | `pypuff.models.visualization` | Publishing-quality figures. |
| `pypuff run` | `pypuff.workflow` | End-to-end orchestration. |

## Installation

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -e .[netcdf,viz]
# optional MPI/HPC support
python -m pip install -e .[netcdf,viz,mpi]
```

For development:

```bash
python -m pip install -e .[dev,netcdf,viz]
python -m pytest -q
python -m compileall src tests
python scripts/check_release.py
```

## Quick start

For a complete step-by-step path from WRF download to PyPuff visualization, see `docs/getting_started.md`.

Preferred NetCDF-CF workflow:

```bash
pypuff run examples/minimal.json --output-dir output --interchange netcdf
pypuff run examples/minimal.json --output-dir output-particles --backend particles --interchange netcdf
mpiexec -n 4 pypuff run examples/minimal.json --output-dir output-mpi --interchange netcdf --parallel auto
pypuff-plot --input output/concentration.nc --output output/concentration.png
pypuff doctor
```

Legacy-compatible workflow:

```bash
pycalmet --config examples/minimal.inp --output output/meteo.json --format json
pypuff-model --config examples/minimal.inp --meteo output/meteo.json --output output/concentration.csv --format csv
pypuff-particles --config examples/minimal.inp --meteo output/meteo.json --output output/particle_concentration.csv --format csv
pycalpost --input output/concentration.csv --output output/post.json
```

## Input/output policy

MPI parallel execution is available through the optional `mpi4py` extra for the Gaussian and particle backends. See `docs/parallelization.md` for the detailed schema and `docs/parallel_mpi.md` for command examples.

The suite accepts a shared JSON configuration model and tolerant Fortran-style `.inp` control files. New module interoperability prefers NetCDF-CF. CSV and legacy text outputs are retained for migration and comparison workflows. See `docs/io_compatibility.md` and `docs/pywrf_pymet.md`.

## Numerical scope

Version 0.4.x adds non-steady Gaussian puff calculations, finite source-size handling for point/area/volume/line-road/flare/spray-style sources, plume rise, stack-tip downwash, dry and wet deposition fluxes, decay/scavenging/settling losses, and CALPOST-style averages, maxima, ranked values, and percentiles. See `docs/numerical_model.md`.

## Scientific boundary

This repository is production-ready as Python software infrastructure when the local diagnostic command reports success. Run `pypuff doctor` in the target environment, and use `pypuff doctor --require-netcdf --require-viz` when NetCDF-CF and publishing figures are mandatory. Regulatory or operational equivalence to official CALPUFF executables must be established by independent validation for the intended use case. See `docs/validation.md`.

## Repository layout

```text
src/pypuff/       Python package
tests/               pytest suite
examples/            coherent JSON, legacy, raster examples
docs/                architecture, PyWRF/PyMET, I/O, validation, production, visualization notes
.github/workflows/   CI template
```

## License

MIT for the Python code in this repository. CALPUFF names are used only to label compatibility concepts and known public file roles.

## Operational use cases

PyPuff includes a root-level `usecases/` folder with reproducible templates for:

- high-resolution wind-field interpolation from 1 km WRF to a 100 m local grid centered on a supplied latitude/longitude;
- arson/wildfire screening simulations using the same PyPuff configuration and output conventions as the main suite;
- model evaluation against satellite-derived masks with a lightweight deterministic AI calibration layer.

Install the package, then run the root-level didactic scripts. The use cases are intentionally not importable suite modules:

```bash
python usecases/01_high_resolution_wind_field/run.py --download-date 2026-05-27 --download-cycle-hour 0 --output wrf_100m_wind.nc --center-lat 40.85 --center-lon 14.27
python usecases/02_wildfire_arson_effects/run.py --download-date 2026-05-27 --download-cycle-hour 0 --output-dir wildfire_case --center-lat 40.85 --center-lon 14.27 --temperature-k 1100
python usecases/03_satellite_ai_evaluation/run.py --concentration wildfire_case/model/concentration.nc --satellite-mask satellite_mask.json --output wildfire_case/evaluation.json
```

The use cases prefer NetCDF-CF products when `netCDF4` is installed and fall back to JSON/CSV for lightweight runs and automated tests. They are documented examples under `usecases/`, not part of the `pypuff` package namespace.
