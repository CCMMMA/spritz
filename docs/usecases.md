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

## Documentation standard

Each use case README contains purpose, workflow, inputs, commands, outputs, assumptions, and validation checks.  Commands use the same coordinate examples and WRF archive pattern so the use cases remain consistent.
