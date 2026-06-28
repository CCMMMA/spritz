# Input, output, and configuration compatibility

The suite has one configuration model shared by SpritzWRF, CTGPROC, MakeGeo, SpritzMet, unified Spritz Gaussian/particle dispersion, SpritzPost, and visualization tools.

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

- SpritzMet writes `meteo.nc` with `eastward_wind(time,z,y,x)`,
  `northward_wind(time,z,y,x)`, `air_temperature(time,y,x)`,
  `atmosphere_boundary_layer_thickness(time,y,x)`, and
  `precipitation_rate(time,y,x)`.
- Spritz reads `meteo.nc` and writes `concentration.nc`; JSON `run.backend`
  or CLI `--backend` selects `gaussian`/`gauss` or `particles`.
- SpritzPost and visualization read NetCDF concentration files directly.
- Concentration outputs may contain multiple model output times when
  `run.output_interval_s` or `sprtz run --output-interval` is supplied. This
  output cadence is independent from the meteorological input cadence; the
  default remains one legacy-compatible output at `time=0`.
- Concentration NetCDF files preserve the receptor table in
  `concentration(time, receptor)`, `dry_flux(time, receptor)`, and
  `wet_flux(time, receptor)`. When weather datetimes are configured, the file
  also contains `time_datetime(time)` with ISO-8601 output datetimes. When field
  rows form a complete grid, the same
  file also contains `concentration_field(time, field_z, field_y, field_x)`
  plus gridded dry and wet deposition flux fields. Use JSON
  `run.concentration_output: "grid"` and `run.field_z_levels` to request a
  model-grid 3D field when explicit receptors are also present.

Sprtz-produced NetCDF files follow strict CF conventions for coordinate
variables, dimensions, units, and metadata. Files with a time axis must include
a CF `time(time)` coordinate. Scientific UTC datetimes are never inferred from
filenames; WRF valid time is extracted by SpritzWRF from WRF/CF metadata such as
`Times`, CF `time` units, or explicit global time attributes, then propagated to
SpritzMet and dispersion outputs.

When the optional `netCDF4` dependency is not installed, `.nc` writes fall back to a deterministic CF-shaped JSON payload so the core package remains usable in minimal CI environments. Install `.[netcdf]` for true NetCDF files.

## File-format selection

All production commands infer format from extension and also accept explicit format flags. Use `.nc` for NetCDF-CF, `.json` for JSON diagnostics, `.csv` for tabular concentration files, and extensionless/legacy names for Fortran-style text tables.

## WRF5 d03 archive input

SpritzWRF can download and read WRF5 d03 history files from the meteo@uniparthenope archive.  The URL pattern is:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

The downloader stores files locally and the SpritzWRF reader accepts common WRF
near-surface wind variables (`U10`/`V10`, `WSPD10`/`WDIR10`) and CF-like wind
names. Four-dimensional WRF wind variables are sliced as `time, level, y, x`
with independent `time_index` and `level_index` choices. SpritzWRF reads valid
time only from WRF/CF time metadata, not from the downloaded filename. It also
extracts precipitation from common rate variables (`RAINRATE`, `PRECIP_RATE`,
`precipitation_rate`, `precip_rate`) or accumulated WRF rain variables (`RAINC`,
`RAINNC`, `RAINSH`) when present. SpritzMet converts those fields into the
NetCDF-CF local product used by the rest of Spritz.


## Terrain Preprocessing

Terrain is included as `sprtz.models.terrain` and the `terrain` CLI. It provides clean-room terrain interpolation and NetCDF-CF/JSON terrain outputs for SpritzMet, MakeGeo, and dispersion workflows.
