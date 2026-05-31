# SpritzWRF and SpritzMet interoperability

Sprtz uses clean-room module names for the WRF-to-meteorology part of the workflow:

- **SpritzWRF** (`sprtz.models.spritzwrf`) reads WRF/WRF-like NetCDF data, extracts near-surface wind, and can download WRF5 d03 history files from the meteo@uniparthenope archive.
- **SpritzMet** (`sprtz.models.spritzmet`) creates local projected grids, builds diagnostic meteorology, and writes NetCDF-CF meteorological fields consumed by Sprtz dispersion modules.

These modules are clean-room Python APIs that implement a compatible workflow and prefer NetCDF-CF interchange.

## meteo@uniparthenope WRF5 d03 archive

The downloader constructs URLs using this pattern:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

Example URL construction from Python:

```python
from sprtz.models.spritzwrf import meteo_uniparthenope_wrf_url

url = meteo_uniparthenope_wrf_url("2026-05-27", 0)
print(url)
```

Download from Python:

```python
from sprtz.models.spritzwrf import download_meteo_uniparthenope_wrf

path = download_meteo_uniparthenope_wrf("data/wrf", run_date="2026-05-27", cycle_hour=0)
```

Use case 01 exposes the same downloader from the command line.

## SpritzWRF to SpritzMet pipeline

```python
from sprtz.models import spritzwrf, spritzmet

wrf = spritzwrf.load_near_surface_wind("data/wrf/wrf5_d03_20260527Z0000.nc")
met = spritzmet.downscale_wrf_to_local_grid(
    wrf,
    center_lat=40.85,
    center_lon=14.27,
    nx=101,
    ny=101,
    dx_m=100,
    dy_m=100,
)
spritzmet.write_local_meteorology("output/wrf_100m_wind.nc", met)
```

## Output conventions

SpritzMet writes a NetCDF-CF product containing local x/y, latitude/longitude, eastward/northward wind, wind speed, and meteorological wind direction.  JSON fallback is available for test and low-dependency environments.
