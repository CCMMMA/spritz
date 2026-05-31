# Use case 01 — High-resolution wind-field interpolation

Goal: obtain a local 100 m wind field centered on a user-supplied latitude and longitude, starting from a 1 km WRF5 d03 file.

This didactic workflow is deliberately explicit:

1. **Acquire WRF 1 km data.** Use a local WRF NetCDF file or download from the meteo@uniparthenope archive.
2. **SpritzWRF step.** Extract latitude, longitude, and near-surface wind components from the WRF file.
3. **SpritzMet step.** Build a local azimuthal-equidistant grid centered on the requested coordinate.
4. **Interpolation step.** Interpolate SpritzWRF wind vectors onto the SpritzMet 100 m grid.
5. **Output step.** Write NetCDF-CF by default, or JSON for lightweight runs.

The WRF archive pattern is:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

## Run with automatic download

```bash
python usecases/01_high_resolution_wind_field/run.py \
  --download-date 2026-05-27 \
  --download-cycle-hour 0 \
  --download-dir data/wrf \
  --output output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 --ny 101 \
  --dx 100 --dy 100
```

## Print the URL without downloading

```bash
python usecases/01_high_resolution_wind_field/run.py \
  --download-date 2026-05-27 \
  --download-cycle-hour 0 \
  --output ignored.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --print-download-url
```

## Run with an existing WRF file

```bash
python usecases/01_high_resolution_wind_field/run.py \
  --wrf data/wrf/wrf5_d03_20260527Z0000.nc \
  --output output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27
```

## Classroom/demo run without WRF data

```bash
python usecases/01_high_resolution_wind_field/run.py \
  --allow-synthetic \
  --json \
  --output output/demo_wind.json \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 21 --ny 21
```

## Expected products

- `wrf_100m_wind.nc` or `.json`
- variables/fields: `latitude`, `longitude`, `eastward_wind`, `northward_wind`, `wind_speed`, `wind_from_direction`

## Teaching notes

The script uses production modules `sprtz.models.spritzwrf` and `sprtz.models.spritzmet`, but the scenario orchestration lives only in this folder. This keeps the suite compact and keeps educational workflows easy to inspect.
