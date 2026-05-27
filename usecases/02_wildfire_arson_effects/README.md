# Use case 02 - Arson or wildfire effects

## Purpose

Create and run a smoke/particulate dispersion scenario for an arson or wildfire ignition point.  The scenario is configured from burning latitude/longitude, burning temperature, start time, duration, and burning area.  Wind forcing is derived from WRF 1 km data using the same PyWRF → PyMET pipeline described in use case 01.

## Workflow

```text
WRF5 d03 NetCDF -> PyWRF -> PyMET 100 m wind -> wildfire source config -> PyPuff Gaussian or particle backend -> concentrations/deposition
```

The particle backend is the default because it is better suited to event-style releases and plume meander experiments.  The Gaussian backend remains useful for fast screening and comparisons.

## Inputs

Required event parameters:

- `--center-lat`, `--center-lon`: local modeling domain center, normally the burning location.
- `--temperature-k`: burning temperature in kelvin.
- `--start`: event timestamp, preferably ISO-8601.
- `--duration-s`: burning duration in seconds.
- `--area-m2`: burning area in square metres.

Meteorological input options:

- `--wrf path/to/wrf5_d03_YYYYMMDDZhh00.nc` for local files.
- `--download-date YYYY-MM-DD --download-cycle-hour hh` for direct meteo@uniparthenope download.
- `--allow-synthetic-wrf` only for smoke tests.

## Download WRF and run the particle model

```bash
pypuff-usecase-wildfire \
  --download-date 2026-05-27 \
  --download-cycle-hour 0 \
  --download-dir data/wrf \
  --output-dir output/wildfire_case \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --temperature-k 1100 \
  --start 2026-05-27T10:00:00Z \
  --duration-s 3600 \
  --area-m2 2500 \
  --backend particles \
  --interchange netcdf
```

Run from an existing WRF file:

```bash
pypuff-usecase-wildfire \
  --wrf data/wrf/wrf5_d03_20260527Z0000.nc \
  --output-dir output/wildfire_case \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --temperature-k 1100 \
  --start 2026-05-27T10:00:00Z
```

## Outputs

The case directory contains:

- `wrf_100m_wind.nc` or `.json`: PyWRF → PyMET local wind product.
- `wildfire_event.json`: generated PyPuff configuration.
- `model/meteo.nc`: PyPuff meteorology interchange product.
- `model/concentration.nc`: concentration/deposition product.
- `model/post.json`: post-processing statistics.

## Parameterization notes

The heat-release and particulate emission estimates are screening defaults.  For production wildfire work, replace them with local fuel-load, combustion-efficiency, fire-radiative-power, or emission-factor estimates.  The generated config records the assumptions so it can be edited before rerunning the model.

## Validation checklist

- Confirm event coordinates and timestamp.
- Confirm WRF cycle and forecast/analysis validity time.
- Inspect the 100 m wind product before running dispersion.
- Compare model concentrations or plume footprint against observations, satellite products, cameras, reports, or field measurements.
- Use case 03 for satellite/AI-supported evaluation.
