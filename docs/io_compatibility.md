# Input, output, and configuration compatibility

The suite has one configuration model shared by SpritzWRF, CTGPROC, MakeGeo, SpritzMet, Spritz, the particle alternative, SpritzPost, and visualization tools.

## Legacy Suite Files

The Python implementation accepts the same *classes* of files used by legacy Fortran-era workflows:

- Spritz/SpritzMet-style control files with `KEY = VALUE`, `KEY: VALUE`, or whitespace-separated records and `!` comments;
- station, source, receptor, grid, stability, threshold, and run-control keys used in the examples;
- CSV/text concentration tables that preserve receptor and concentration columns;
- WRF/NetCDF inputs inspected by SpritzWRF-style adapters;
- ASCII raster inputs for CTGPROC/MakeGeo-style terrain and land-use preprocessing.

This is not a byte-for-byte parser for every historical Fortran control record. Unknown keys are preserved in `SuiteConfig.raw` / `run` so projects can extend parsers without breaking old input decks.

## Preferred interoperability format: NetCDF-CF

New module-to-module exchange prefers NetCDF-CF:

- SpritzMet writes `meteo.nc` with `eastward_wind`, `northward_wind`, `air_temperature`, and `atmosphere_boundary_layer_thickness`.
- Spritz and `sprtz-particles` read `meteo.nc` and write `concentration.nc`.
- SpritzPost and visualization read NetCDF concentration files directly.
- Concentration outputs may contain multiple model output times when
  `run.output_interval_s` or `sprtz run --output-interval` is supplied. This
  output cadence is independent from the meteorological input cadence; the
  default remains one legacy-compatible output at `time=0`.

When the optional `netCDF4` dependency is not installed, `.nc` writes fall back to a deterministic CF-shaped JSON payload so the core package remains usable in minimal CI environments. Install `.[netcdf]` for true NetCDF files.

## File-format selection

All production commands infer format from extension and also accept explicit format flags. Use `.nc` for NetCDF-CF, `.json` for JSON diagnostics, `.csv` for tabular concentration files, and extensionless/legacy names for Fortran-style text tables.

## WRF5 d03 archive input

SpritzWRF can download and read WRF5 d03 history files from the meteo@uniparthenope archive.  The URL pattern is:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

The downloader stores files locally and the SpritzWRF reader accepts common WRF near-surface wind variables (`U10`/`V10`, `WSPD10`/`WDIR10`) and CF-like wind names.  SpritzMet converts those fields into the NetCDF-CF local product used by the rest of Sprtz.


## Terrain Preprocessing

Terrain is included as `sprtz.models.terrain` and the `terrain` CLI. It provides clean-room terrain interpolation and NetCDF-CF/JSON terrain outputs for SpritzMet, MakeGeo, and dispersion workflows.
