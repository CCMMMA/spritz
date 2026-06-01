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

```bash
python usecases/05_sailing_wind_forecast/run.py \
  --output output/sailing/bay_of_naples_forecast.json
```

Pin an initialization date explicitly:

```bash
python usecases/05_sailing_wind_forecast/run.py \
  --initialization-date 2026-06-01 \
  --outlook-hours 24 \
  --bbox 14.18,40.78,14.33,40.85 \
  --horizontal-resolution-m 100 \
  --vertical-resolution-m 10 \
  --time-resolution-s 600 \
  --output output/sailing/bay_of_naples_forecast.json
```

The default product is deterministic and offline. It uses a synthetic
sea-breeze-like field so downstream sailing analytics can test the full
space-height-time schema. Replace the synthetic field with an authoritative
forecast provider before operational race decisions.

Expected fields include:

- longitude and latitude axes;
- height levels in metres;
- valid times in seconds from initialization;
- eastward and northward wind;
- wind speed;
- wind-from direction;
- gust-speed proxy.
