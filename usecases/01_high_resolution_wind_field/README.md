# Use case 01 - High-resolution wind field interpolation

## Purpose

Create a 100 m near-surface wind product centered at a user-provided latitude and longitude, starting from a 1 km WRF5 d03 NetCDF field.  This use case is the meteorological foundation for urban smoke, fire, arson, odour, and accidental-release scenarios where the WRF grid is too coarse for local receptor placement.

## Clean-room module chain

This use case explicitly follows the new PyPuff naming and architecture:

```text
WRF5 d03 NetCDF -> PyWRF -> PyMET -> NetCDF-CF local wind product
```

- **PyWRF** replaces the former CALWRF role.  It reads WRF variables such as `XLAT`, `XLONG`, `U10`, `V10`, `WSPD10`, and `WDIR10` and normalizes them into a typed Python wind field.
- **PyMET** replaces the former CALMET role for this use case.  It creates an azimuthal-equidistant local grid centered on the requested coordinate and interpolates PyWRF vectors onto the 100 m grid.

No original Fortran source code is copied or translated.

## Input data

A WRF NetCDF file must contain one of these variable combinations:

- `XLAT`/`XLONG` and `U10`/`V10`
- `XLAT`/`XLONG` and `WSPD10`/`WDIR10`
- CF-style `latitude`/`longitude` and `eastward_wind`/`northward_wind`

The preferred WRF 1 km source is the meteo@uniparthenope WRF5 d03 history archive:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

## Download and run

Download and process a cycle directly:

```bash
pypuff-usecase-wind \
  --download-date 2026-05-27 \
  --download-cycle-hour 0 \
  --download-dir data/wrf \
  --output output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100
```

Print the exact archive URL without downloading:

```bash
pypuff-usecase-wind \
  --download-date 2026-05-27 \
  --download-cycle-hour 0 \
  --output output/placeholder.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --print-download-url
```

Use an already downloaded WRF file:

```bash
pypuff-usecase-wind \
  --wrf data/wrf/wrf5_d03_20260527Z0000.nc \
  --output output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27
```

Dependency-light smoke test without WRF data:

```bash
python run.py \
  --output output/wrf_100m_wind.json \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --json \
  --allow-synthetic
```

Synthetic mode is deterministic and is only for tests and demonstrations.

## Output

Default output is NetCDF-CF when `netCDF4` is installed.  The file contains:

- local `x` and `y` coordinates in metres
- `latitude` and `longitude`
- `eastward_wind`
- `northward_wind`
- `wind_speed`
- `wind_from_direction`
- metadata describing the PyWRF → PyMET pipeline and source WRF file

JSON fallback contains the same physical fields as arrays and metadata.

## Quality checks

Before using the product operationally:

1. Verify that the WRF cycle covers the event time.
2. Inspect the center-cell wind speed and direction.
3. Plot the resulting vectors and compare with available observations.
4. Check coastal and orographic areas carefully; inverse-distance interpolation is deterministic and robust but not a full dynamic downscaling model.
5. Store the WRF archive URL, cycle hour, PyPuff version, and command line in the case record.
