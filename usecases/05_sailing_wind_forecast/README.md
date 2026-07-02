# Use case 05 - High-resolution sailing wind forecast

Goal: build a high-resolution forecast-ready wind product for precision
professional sailing applications. The use case is parameterized by:

- initialization date at UTC Z00;
- outlook in hours;
- geographic bounding box;
- horizontal resolution in metres;
- vertical resolution in metres;
- time resolution in seconds.

The bundled defaults target a Bay of Naples race area with 100 m horizontal
resolution, 10 m vertical resolution, and 10 minute time resolution. The
initialization date defaults to the current UTC day at Z00, and the default
outlook is 24 hours.

For consistency with use case 01 wind products, operational Bay of Naples
studies can use the same physical vertical-level convention: the first level is
10 m above local ground and the 21-level exponential list follows
`10 * exp(0.46 * x)` for integer `x=0..20`. The bundled synthetic sailing
forecast still accepts `--vertical-resolution-m` for regular teaching grids.

NetCDF/time convention: the forecast NetCDF writes a strict CF `time(time)`
coordinate with absolute UTC units derived from the initialization datetime and
forecast lead seconds. The JSON payload keeps `valid_time_s` as forecast lead
seconds for scripting convenience. Wind variables are written as
`eastward_wind(time,z,y,x)`, `northward_wind(time,z,y,x)`,
`wind_speed(time,z,y,x)`, and `wind_from_direction(time,z,y,x)`.

Default race-area polygon:

```json
{
  "coordinates": [
    [14.18, 40.78],
    [14.18, 40.85],
    [14.33, 40.85],
    [14.33, 40.78],
    [14.18, 40.78]
  ]
}
```

## Data preparation

The bundled run is deterministic and offline, but operational forecast studies
should prepare the same data roots used by the other use cases:

```bash
tools/meteouniparthenope-wrf-download.py 20260601Z0000 \
  --hours 24 \
  --domain d03 \
  --data-root data/wrf/d03
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.78 --north 40.85 \
  --west 14.18 --east 14.33 \
  --output data/dem/cop30_bay_of_naples.tif
python3 tools/copernicus-lc100-download.py \
  --south 40.78 --north 40.85 \
  --west 14.18 --east 14.33 \
  --output data/landcover/lc100_bay_of_naples.tif
```

The WRF files are the source for replacing the synthetic wind field. Pass the
COP30 DEM as `--dem` and LC100 land cover as `--land-cover` when preparing
SpritzMet wind and precipitation products; the same rasters can also be used by
`sprtz-terrain fetch` for shoreline or terrain-aware preprocessing.

```bash
python usecases/05_sailing_wind_forecast/step_01_build_forecast.py \
  --output output/sailing/bay_of_naples_forecast.json
```

Pin an initialization date explicitly:

```bash
python usecases/05_sailing_wind_forecast/step_01_build_forecast.py \
  --initialization-time 20260601Z0000 \
  --outlook-hours 24 \
  --bbox 14.18,40.78,14.33,40.85 \
  --horizontal-resolution-m 100 \
  --vertical-resolution-m 10 \
  --time-resolution-s 600 \
  --output output/sailing/bay_of_naples_forecast.json
```

To prepare the matching SpritzWRF/SpritzMet wind product from use case 01 for
the same race area, pass the vertical-level preset on that command line:

```bash
python usecases/01_high_resolution_wind_field/step_01_downscale_wind.py \
  --date 20260626Z0000 \
  --hours 24 \
  --download-dir data/wrf/d03/ \
  --output data/output/wrf_100m_wind_bbox.nc \
  --south 40.78 --north 40.85 --west 14.18 --east 14.33 \
  --dx 100 --dy 100 \
  --vertical-levels-m usecase01-exponential \
  --dem data/dem/cop30_naples.tif \
  --land-cover data/landcover/lc100_naples.tif
```

The default product is deterministic and offline. It uses a synthetic
sea-breeze-like field so downstream sailing analytics can test the full
space-height-time schema. Replace the synthetic field with an authoritative
forecast provider before operational race decisions.

## Plot the forecast NetCDF map

When `netCDF4` and plotting dependencies are available, the script also writes
`bay_of_naples_forecast.nc` and calls `tools/plotter.py`. To regenerate the
surface wind-speed map explicitly, run:

```bash
python tools/plotter.py output/sailing/bay_of_naples_forecast.nc \
  --variable wind_speed \
  --time-index 0 \
  --level-index 0 \
  --output output/sailing/bay_of_naples_forecast_wind_speed_map.png
```

Expected fields include:

- longitude and latitude axes;
- `z` height levels in metres;
- CF `time(time)` coordinates and ISO `time_datetime(time)` values;
- JSON `valid_time_s` lead times in seconds from initialization;
- eastward and northward wind as `time,z,y,x`;
- wind speed as `time,z,y,x`;
- wind-from direction as `time,z,y,x`;
- gust-speed proxy as `time,z,y,x`.
