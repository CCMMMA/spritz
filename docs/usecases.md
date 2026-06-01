# Operational use cases

The root-level `usecases/` directory contains three documented operational templates.  They are meant to be copied into project-specific case folders and version-controlled with event metadata.

## 01 - High-resolution wind field interpolation

This use case implements the meteorological preprocessing chain:

```text
meteo@uniparthenope WRF5 d03 or local WRF NetCDF -> SpritzWRF -> SpritzMet -> 100 m NetCDF-CF wind field
```

It supports direct downloads from:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

The default grid is 101 x 101 points at 100 m spacing, centered on the requested coordinate.

## 02 - Arson or wildfire effects

This use case consumes the same WRF/SpritzWRF/SpritzMet path as use case 01, then builds a Sprtz scenario from event location, burning temperature, start time, duration, area, and emission assumptions.  It can run the Gaussian or particle backend and writes the ordinary Sprtz model outputs.

## 03 - Satellite and AI-supported model evaluation

This use case evaluates Sprtz concentration/deposition output against a satellite-derived mask and reports confusion-matrix metrics, CSI/threat score, false-alarm ratio, probability of detection, and deterministic AI-style calibration output.

## 04 - Production incident catalog

This use case reads a semicolon-delimited incident catalog and builds validated
Sprtz configurations with event metadata, local receptors, WGS84 receptor
coordinates, and optional geographic concentration maps. The bundled rows cover
the supplied Acerra `2021_44` incident on 30/07/2021 at 14:00 for 3 hours and
the San Marcellino `2023_14` incident on 14/07/2023 at 15:00 for 3 hours.

## 05 - High-resolution sailing wind forecast

This use case creates a forecast-ready wind product over a latitude/longitude
bounding box, with explicit initialization date at Z00, outlook in hours,
horizontal resolution, vertical resolution, and time resolution. The default
example targets a Bay of Naples race area for precision top class professional
sailing: current UTC day at Z00, 100 m horizontal resolution, 10 m vertical
resolution, and 10 minute temporal resolution. The bundled implementation is deterministic and
offline so downstream race-planning tooling can validate the full
space-height-time schema before authoritative forecast data are connected.

## Documentation standard

Each use case README contains purpose, workflow, inputs, commands, outputs, assumptions, and validation checks.  Commands use the same coordinate examples and WRF archive pattern so the use cases remain consistent.
