# SpritzWRF and SpritzMet interoperability

Spritz uses clean-room module names for the WRF-to-meteorology part of the workflow:

- **SpritzWRF** (`sprtz.models.spritzwrf`) reads WRF/WRF-like NetCDF data, extracts near-surface wind and precipitation, and can download WRF5 d03 history files from the meteo@uniparthenope archive.
- **SpritzMet** (`sprtz.models.spritzmet`) creates local projected grids, builds diagnostic meteorology, and writes NetCDF-CF meteorological fields consumed by Spritz dispersion modules.

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

SpritzWRF reads precipitation rate variables named `RAINRATE`, `PRECIP_RATE`,
`precipitation_rate`, or `precip_rate`. If the WRF file contains accumulated
rain variables (`RAINC`, `RAINNC`, `RAINSH`), SpritzWRF uses the increment at
the requested `time_index` as a millimeters-per-hour screening rate. SpritzMet
interpolates the precipitation field using the same local-grid transform as the
wind field.

SpritzWRF also owns WRF valid-time extraction. It reads datetimes only from
WRF/CF time metadata such as `Times`, CF `time` units, or explicit global time
attributes. It does not infer datetimes from WRF filenames. SpritzMet propagates
that selected UTC datetime to the local NetCDF-CF `time(time)` coordinate.

## Output conventions

SpritzMet writes a strict NetCDF-CF product containing local x/y, latitude/longitude, eastward/northward wind, wind speed, meteorological wind direction, and `precipitation_rate` in `mm h-1`. Products with a physical valid time include a CF `time(time)` coordinate with absolute UTC units. JSON fallback is available for test and low-dependency environments.

Set `run.precipitation_washout: true` in the Spritz JSON configuration to use
the interpolated precipitation rate as an additional wet-removal term in the
Gaussian and particle concentration backends.

For station-driven configurations, station records may include
`precipitation_rate` in `mm h-1`. If no station precipitation is supplied,
`run.default_precipitation_rate` provides the uniform fallback.
