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

wrf = spritzwrf.load_near_surface_wind(
    "data/wrf/wrf5_d03_20260527Z0000.nc",
    time_index=None,
    level_index=None,
)
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

When DEM elevation and land-cover fields have already been regridded to the
same local SpritzMet grid, pass them as `dem_elevation_m` and `land_cover`.
SpritzMet then follows a clean-room CALMET-style diagnostic downscaling
sequence: objective WRF interpolation to the local grid, terrain/slope and
elevation wind adjustment, land-cover roughness exposure adjustment, and
orographic plus land-cover precipitation factors. The implementation is not a
copy, port, or regulatory-equivalent CALMET release; its coefficients are named
in `sprtz.models.spritzmet` and bounded for deterministic screening workflows.
Without these optional arrays, the pipeline preserves the original
WRF-to-local-grid interpolation behavior.

Use case 01 exposes the same path from the command line:

```bash
python usecases/01_high_resolution_wind_field/step_01_downscale_wind.py \
  --wrf data/wrf/d03/wrf5_d03_20260621Z0000.nc \
  --output data/output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 \
  --ny 101 \
  --vertical-levels-m usecase01-exponential \
  --dem data/dem/cop30_naples.tif \
  --land-cover data/landcover/lc100_naples.tif
```

SpritzWRF handles WRF/CF dimensions explicitly. Four-dimensional wind variables
are interpreted as `time, level, y, x` when dimension names such as `Time`,
`bottom_top`, `south_north`, and `west_east` are present; `time_index` and
`level_index` are selected independently. Pass `None` for either index to
preserve the full axis; use case 01 does this by default so the ordinary command
downscales all available WRF times and all wind levels. SpritzWRF reads
precipitation rate variables named `RAINRATE`, `PRECIP_RATE`, `precipitation_rate`, or
`precip_rate`. If the WRF file contains accumulated rain variables (`RAINC`,
`RAINNC`, `RAINSH`), SpritzWRF uses the increment at the requested `time_index`
as a millimeters-per-hour screening rate, or all increments when all times are
preserved. SpritzMet downscales the precipitation field using the same
local-grid transform as the wind field.

Use case 01 can set the output vertical coordinate explicitly with
`--vertical-levels-m`. The named preset `usecase01-exponential` expands to 21
heights above local ground using `10 * exp(0.46 * x)` for integer `x=0..20`;
the height list must have the same length as the preserved WRF wind-level axis.

SpritzWRF also owns WRF valid-time extraction. It reads datetimes only from
WRF/CF time metadata such as `Times`, CF `time` units, or explicit global time
attributes. It does not infer datetimes from WRF filenames. SpritzMet propagates
that selected UTC datetime to the local NetCDF-CF `time(time)` coordinate.

## Output conventions

SpritzMet writes a strict NetCDF-CF product containing local x/y, vertical
level `z`, latitude/longitude, eastward/northward wind, wind speed,
meteorological wind direction, and `precipitation_rate` in `mm h-1`. Wind
variables are stored as `eastward_wind(time,z,y,x)` and
`northward_wind(time,z,y,x)`. Surface precipitation is stored as
`precipitation_rate(time,y,x)`. Products with a physical valid time include a
CF `time(time)` coordinate with absolute UTC units. JSON fallback uses the same
logical dimensionality for WRF-derived local products. When physical
`level_meters` metadata is available, `z` is written as metres above local
ground; otherwise it remains a vertical level index.

Set `run.precipitation_washout: true` in the Spritz JSON configuration to use
the downscaled precipitation rate as an additional wet-removal term in the
Gaussian and particle concentration backends.

For station-driven configurations, station records may include
`precipitation_rate` in `mm h-1`. If no station precipitation is supplied,
`run.default_precipitation_rate` provides the uniform fallback.
