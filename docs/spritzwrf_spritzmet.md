# SpritzWRF and SpritzMet interoperability

## Scientific Scope

This document describes SpritzWRF and SpritzMet interoperability. It focuses on dimension-aware WRF ingestion, local-grid downscaling, vertical wind-profile constraints, and reproducible meteorological metadata.

Spritz uses clean-room module names for the WRF-to-meteorology part of the workflow:

- **SpritzWRF** (`sprtz.models.spritzwrf`) reads WRF/WRF-like NetCDF data, extracts near-surface wind, precipitation, 2 m temperature, and 2 m relative humidity, and can download WRF5 d03 history files from the meteo@uniparthenope archive.
- **SpritzMet** (`sprtz.models.spritzmet`) creates local projected grids, builds diagnostic meteorology, and writes NetCDF-CF meteorological fields consumed by Spritz dispersion modules.

These modules are clean-room Python APIs that implement a compatible workflow and prefer NetCDF-CF interchange.

## meteo@uniparthenope WRF5 d03 History Files

The downloader constructs URLs using this `history` directory pattern:

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
    parallel="auto",
)
spritzmet.write_local_meteorology("output/wrf_100m_wind.nc", met)
spritzmet.write_calmet_dat("output/CALMET.DAT", met)
```

When DEM elevation and land-cover fields have already been regridded to the
same local SpritzMet grid, pass them as `dem_elevation_m` and `land_cover`.
SpritzMet then follows a clean-room CALMET-style diagnostic downscaling
sequence: objective WRF downscaling to the local grid, terrain/slope and
elevation wind adjustment, land-cover roughness exposure adjustment, and
orographic plus land-cover precipitation factors. The implementation is not a
copy, port, or regulatory-equivalent CALMET release; its coefficients are named
in `sprtz.models.spritzmet` and bounded for deterministic screening workflows.
When WRF provides `T2`, SpritzMet writes 2 m temperature in Celsius and applies
a DEM lapse-rate correction if `dem_elevation_m` is supplied. When WRF provides
`RH2`, it is written as a unitless 0-1 relative-humidity rate; if only `Q2`,
surface pressure, and `T2` are present, SpritzWRF derives the rate from those
fields. DEM temperature corrections preserve vapor pressure and recompute the
humidity rate. Land cover is used for wind roughness and precipitation
adjustments, while the thermodynamic scalar correction is DEM based.
Without these optional arrays, the pipeline preserves the original
WRF-to-local-grid downscaling behavior.

`downscale_wrf_to_local_grid` defaults to `downscaling_mode="deterministic"`.
That mode uses DEM elevation and land cover whenever they are supplied. The
optional `ai` and `diffusion` modes run built-in clean-room NumPy downscalers by
default. The `ai` mode applies a deterministic feature-residual refinement using
local meteorological detail plus DEM and roughness features when present. The
`diffusion` mode applies terrain-conditioned anisotropic diffusion refinement
with mean-preserving bounds. Callers may override either path with
`ai_model` or `diffusion_model` callables, and output metadata records whether
the built-in or supplied model was applied.
All modes can be improved with `station_measurements`, which applies
inverse-distance residual corrections from observed wind and precipitation
without changing the underlying downscaling method. For command-line workflows,
station measurements are read from CSV with either local `x,y` coordinates in
meters or `latitude,longitude` columns. Observation columns are
`wind_speed`/`wind_dir` and/or `precipitation_rate`.

Use case 01 exposes the same path from the command line:

```bash
python usecases/01_high_resolution_wind_field/step_01_downscale_wind.py \
  --wrf data/wrf/d03/wrf5_d03_20260621Z0000.nc \
  --output data/output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 \
  --ny 101 \
  --config usecases/01_high_resolution_wind_field/config.json \
  --dem data/dem/cop30_naples.tif \
  --land-cover data/landcover/lc100_naples.tif \
  --station-measurements data/stations/weather_observations.csv \
  --calmet-dat data/output/CALMET.DAT \
  --downscaling-mode deterministic \
  --parallel auto
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

SpritzWRF reads 2 m thermodynamic fields when available. `T2`/`TEMP2` are
converted to Celsius when stored in Kelvin. `RH2` values larger than 1.5 are
interpreted as percent and converted to a 0-1 rate. If `RH2` is missing but
`Q2`, surface pressure, and `T2` exist, relative humidity is computed from
specific humidity and saturation vapor pressure.

Use case 01 can set the output vertical coordinate explicitly with
`--vertical-levels-m` or through
`usecases/01_high_resolution_wind_field/config.json`. The documented use-case
configuration sets fixed heights above mean sea level:
`10, 15, 25, 50, 75, 100, 150, 250, 500, 750, 1000, 1250` m. Four-dimensional
WRF wind is interpreted as `time, level, y, x` with levels in metres above sea
level. Three-dimensional diagnostic wind such as `U10/V10` is interpreted as
`time, y, x` at 10 m above local ground. Precipitation stays three-dimensional
as `time, y, x`.

Downstream Gaussian and particle dispersion sampling preserves that near-surface
constraint. If diagnostic `U10M/V10M` exists and the first physical model level
is aloft, the sampler inserts the diagnostic 10 m above-ground wind as the
lower-boundary layer before interpolating the `time,z,y,x` cube.

SpritzWRF also owns WRF valid-time extraction. It reads datetimes only from
WRF/CF time metadata such as `Times`, CF `time` units, or explicit global time
attributes. It does not infer datetimes from WRF filenames. SpritzMet propagates
that selected UTC datetime to the local NetCDF-CF `time(time)` coordinate.

## Output conventions

SpritzMet writes a strict NetCDF-CF product containing local x/y, vertical
level `z`, latitude/longitude, eastward/northward wind, wind speed,
meteorological wind direction, `precipitation_rate` in `mm h-1`, optional
`temperature_2m_c` in Celsius, and optional `relative_humidity_2m` as a
unitless 0-1 rate. Wind
variables are stored as `eastward_wind(time,z,y,x)` and
`northward_wind(time,z,y,x)`. Surface precipitation is stored as
`precipitation_rate(time,y,x)`. Diagnostic 2 m scalar fields are stored as
`temperature_2m_c(time,y,x)` and `relative_humidity_2m(time,y,x)`. Products
with a physical valid time include a
CF `time(time)` coordinate with absolute UTC units. JSON fallback uses the same
logical dimensionality for WRF-derived local products. When physical
`level_meters` metadata is available, `z` is written as metres above local
ground; otherwise it remains a vertical level index.

For binary model-evaluation workflows, `spritzmet.write_calmet_dat` writes a
CALMET.DAT-compatible export using Fortran sequential unformatted records and
the same SpritzMet `time,z,y,x` wind cube. NetCDF-CF remains the canonical
module-to-module format for Spritz dispersion, particle, and firefront modules;
the binary file is generated from that canonical representation so vertical
level meaning is not duplicated across modules.

Set `run.precipitation_washout: true` in the Spritz JSON configuration to use
the downscaled precipitation rate as an additional wet-removal term in the
Gaussian and particle concentration backends.

For station-driven configurations, station records may include
`precipitation_rate` in `mm h-1`. If no station precipitation is supplied,
`run.default_precipitation_rate` provides the uniform fallback.

## References

- Powers, J. G., Klemp, J. B., Skamarock, W. C., Davis, C. A., Dudhia, J., Gill, D. O., Coen, J. L., Gochis, D. J., Ahmadov, R., Peckham, S. E., Grell, G. A., Michalakes, J., Trahan, S., Benjamin, S. G., Alexander, C. R., Dimego, G. J., Wang, W., Schwartz, C. S., Romine, G. S., Liu, Z., Snyder, C., Chen, F., Barlage, M. J., Yu, W., and Duda, M. G. (2017). The Weather Research and Forecasting Model: overview, system efforts, and future directions. Bulletin of the American Meteorological Society, 98(8), 1717-1737. https://doi.org/10.1175/BAMS-D-15-00308.1
- Hong, S.-Y., Dudhia, J., and Chen, S.-H. (2004). A revised approach to ice microphysical processes for the bulk parameterization of clouds and precipitation. Monthly Weather Review, 132(1), 103-120.
- Weil, J. C., Sykes, R. I., and Venkatram, A. (1992). Evaluating air-quality models: review and outlook. Journal of Applied Meteorology, 31(10), 1121-1145.
- Draxler, R. R., and Hess, G. D. (1998). An overview of the HYSPLIT_4 modelling system for trajectories, dispersion, and deposition. Australian Meteorological Magazine, 47(4), 295-308.
- Stohl, A., Forster, C., Frank, A., Seibert, P., and Wotawa, G. (2005). Technical note: The Lagrangian particle dispersion model FLEXPART version 6.2. Atmospheric Chemistry and Physics, 5, 2461-2474.
