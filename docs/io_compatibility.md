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
  `northward_wind(time,z,y,x)`, optional diagnostic `U10M(time,y,x)` /
  `V10M(time,y,x)`, WRF-derived `temperature_2m_c(time,y,x)`,
  `relative_humidity_2m(time,y,x)`, station-derived `air_temperature(time,y,x)`,
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
- Gaussian and particle gridded outputs use the same coordinate contract:
  `time(time)`, `field_z(field_z)`, `field_y(field_y)`, and
  `field_x(field_x)`. Use case 02 validates those axes before writing
  particle/Gaussian comparison metrics.

Sprtz-produced NetCDF files follow strict CF conventions for coordinate
variables, dimensions, units, and metadata. Files with a time axis must include
a CF `time(time)` coordinate. Scientific UTC datetimes are never inferred from
filenames; WRF valid time is extracted by SpritzWRF from WRF/CF metadata such as
`Times`, CF `time` units, or explicit global time attributes, then propagated to
SpritzMet and dispersion outputs.

When the optional `netCDF4` dependency is not installed, `.nc` writes fall back to a deterministic CF-shaped JSON payload so the core package remains usable in minimal CI environments. Install `.[netcdf]` for true NetCDF files.

## CALMET.DAT binary export

SpritzMet can also write a clean-room `CALMET.DAT`-compatible binary export
from a `LocalMeteorology` object:

```python
from sprtz.models import spritzmet

spritzmet.write_calmet_dat("data/output/CALMET.DAT", met)
```

The writer uses Fortran sequential unformatted records with 32-bit record
markers, 32-bit integer dimensions, and 32-bit floating-point meteorological
arrays. Records include a text header, grid dimensions, local grid spacing,
projected coordinates, latitude/longitude, vertical levels, time labels,
eastward and northward wind slabs in `time,z,y,x` order, precipitation rate,
and optional 2 m temperature and relative humidity fields. Missing values are
stored as `-9999.0`.

The export is intended for model-evaluation workflows that need a binary
`CALMET.DAT` artifact. NetCDF-CF remains the canonical Spritz interchange
format because it preserves CF coordinates, named variables, attributes,
vertical-level metadata, and optional fields without relying on fixed binary
record positions.

## CALPUFF-style concentration binary export

Gaussian and particle concentration runs can export complete gridded
concentration fields to a clean-room CALPUFF-style binary sidecar:

```bash
spritz --config examples/minimal.json \
  --meteo output/meteo.nc \
  --output output/concentration.calpuff \
  --backend particles \
  --format calpuff
```

The writer requires rows that form a complete `time, field_z, field_y, field_x`
grid. It writes Fortran sequential unformatted records with a text header,
integer dimensions, `x/y/z/time` coordinates, time labels, and 32-bit floating
point slabs for concentration, dry flux, and wet flux. Missing or invalid
floating-point values are exported as `-9999.0`.

Use case 02 can write the same sidecar for each backend with
`--calpuff-binary`; the files are named `concentration_calpuff.dat` inside the
particle and Gaussian output directories. These files are intended for external
comparison workflows and are not a claim of official CALPUFF distribution
compatibility. NetCDF-CF remains the canonical Sprtz interchange and should be
archived with any binary export.

## Vertical-level storage strategy

The best storage strategy for `sprtz.puff`, `spritz.particles`, and
`spritz.firefront` is to keep SpritzMet meteorology internally as one canonical
four-dimensional wind cube:

- `eastward_wind(time,z,y,x)` and `northward_wind(time,z,y,x)` for transport;
- `z(z)` with `level_meters_kind` metadata identifying height above local
  ground or height above mean sea level;
- surface diagnostics such as `U10M(time,y,x)`, `V10M(time,y,x)`,
  `precipitation_rate(time,y,x)`, `temperature_2m_c(time,y,x)`, and
  `relative_humidity_2m(time,y,x)`.

The Gaussian puff and particle modules can sample the 4D wind cube by output
time, vertical release height, and grid cell while retaining deterministic
fallbacks for 2D legacy inputs. The firefront module should consume the
near-surface diagnostic level, preferring `U10M/V10M` when present and otherwise
interpolating from the lowest physically valid `z` level. Binary `CALMET.DAT`
and CALPUFF-style concentration outputs should be generated only as exports
from these canonical representations so all modules see the same horizontal,
temporal, and vertical semantics.

## File-format selection

All production commands infer format from extension and also accept explicit format flags. Use `.nc` for NetCDF-CF, `.json` for JSON diagnostics, `.csv` for tabular concentration files, `.calpuff` / `.puff` / `.bin` or `--format calpuff` for the clean-room CALPUFF-style concentration binary export, and extensionless/legacy names for Fortran-style text tables.

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
`RAINNC`, `RAINSH`) when present. `T2` is converted to Celsius, `RH2` is
converted to a 0-1 rate, and relative humidity can be derived from `Q2`,
surface pressure, and `T2` when direct `RH2` is absent. SpritzMet converts
those fields into the NetCDF-CF local product used by the rest of Spritz.


## Terrain Preprocessing

Terrain is included as `sprtz.models.terrain` and the `terrain` CLI. It provides clean-room terrain resampling and NetCDF-CF/JSON terrain outputs for SpritzMet, MakeGeo, and dispersion workflows.
