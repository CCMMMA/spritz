# Use case 01 — High-resolution wind-field interpolation

Goal: obtain a local 100 m wind and precipitation-rate field centered on a user-supplied latitude and longitude, starting from a 1 km WRF5 d03 file.

This didactic workflow is deliberately explicit:

1. **Acquire WRF 1 km data.** Use a local WRF NetCDF file or download from the meteo@uniparthenope archive.
2. **SpritzWRF step.** Extract latitude, longitude, near-surface wind components, and precipitation when available from the WRF file.
3. **SpritzMet step.** Build a local azimuthal-equidistant grid centered on the requested coordinate.
4. **Interpolation step.** Interpolate SpritzWRF wind vectors and precipitation onto the SpritzMet 100 m grid.
5. **Output step.** Write NetCDF-CF by default, or JSON for lightweight runs.

The WRF archive pattern is:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

## Data preparation

Prepare WRF input with the repository downloader:

```bash
tools/meteouniparthenope-wrf-download.py 20260527Z0000 \
  --hours 1 \
  --domain d03 \
  --data-root data
```

Prepare terrain for workflows that also need surface elevation:

```bash
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_naples.tif

python3 tools/copernicus-lc100-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/landcover/lc100_naples.tif
```

The WRF file feeds SpritzWRF/SpritzMet directly. The COP30 GeoTIFF feeds
`sprtz-terrain fetch` as a local DEM input, and LC100 feeds the matching local
land-cover input when `sprtz[geo]` is installed; see
`docs/copernicus-cop30-dem-download.md` and
`docs/copernicus-lc100-download.md`.

## Run with automatic download

```bash
python usecases/01_high_resolution_wind_field/step_01_interpolate_wind.py \
  --download-time 20260527Z0000 \
  --download-dir data/wrf \
  --output output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 --ny 101 \
  --dx 100 --dy 100
```

## Print the URL without downloading

```bash
python usecases/01_high_resolution_wind_field/step_01_interpolate_wind.py \
  --download-time 20260527Z0000 \
  --output ignored.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --print-download-url
```

## Run with an existing WRF file

```bash
python usecases/01_high_resolution_wind_field/step_01_interpolate_wind.py \
  --wrf data/wrf/wrf5_d03_20260527Z0000.nc \
  --output output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27
```

## Classroom/demo run without WRF data

```bash
python usecases/01_high_resolution_wind_field/step_01_interpolate_wind.py \
  --allow-synthetic \
  --json \
  --output output/demo_wind.json \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 21 --ny 21
```

## Expected products

- `wrf_100m_wind.nc` or `.json`
- variables/fields: `latitude`, `longitude`, `eastward_wind`, `northward_wind`, `wind_speed`, `wind_from_direction`, `precipitation_rate`

## Teaching notes

The script uses production modules `sprtz.models.spritzwrf` and `sprtz.models.spritzmet`, but the scenario orchestration lives only in this folder. This keeps the suite compact and keeps educational workflows easy to inspect.
