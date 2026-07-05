# Spritz User Manual

## Scientific Scope

This manual documents Sprtz configuration, execution, and interpretation for scientific users. It separates public workflow syntax from model assumptions and points readers to method-specific documentation for validation context.

Spritz is a clean-room, MIT-licensed, pure Python toolkit for atmospheric puff
and dispersion modeling workflows. It provides shared configuration, tolerant
legacy-control parsing, SpritzWRF WRF ingestion, SpritzMet meteorology,
unified Gaussian and particle dispersion, SpritzPost statistics, Terrain/GEO
preprocessing, NetCDF-CF interchange, and visualization.

Spritz is research and workflow infrastructure. It is not presented as a
regulatory-equivalent replacement for any third-party modeling suite. Operational
or regulatory use requires independent validation for the intended domain,
meteorology, emissions, receptors, and acceptance criteria.

## Installation

Use Python 3.10 or newer.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .[dev,netcdf,viz]
```

Optional extras:

```bash
python -m pip install -e .[mpi]
python -m pip install -e .[geo,netcdf,viz]
python -m pip install -e .[maps,viz]
```

Run local diagnostics:

```bash
sprtz doctor
sprtz doctor --require-netcdf --require-viz
```

## Core Workflow

The standard workflow is:

```text
configuration
  -> optional Terrain/GEO acquisition
  -> SpritzMet meteorology
  -> Spritz Gaussian or particle concentration backend
  -> SpritzPost statistics
  -> optional visualization
```

Run the complete workflow:

```bash
sprtz run examples/minimal.json --output-dir output --interchange netcdf
```

Validate a configuration:

```bash
sprtz validate examples/minimal.json
```

The workflow writes:

- `meteo.nc` or `meteo.json`: SpritzMet meteorology.
- `concentration.nc` or `concentration.csv`: concentration and deposition.
- `post.json`: SpritzPost summary statistics.
- `geo.nc` or `geo.json`: optional Terrain/GEO product when enabled.

## Configuration File Structure

JSON is the richest configuration format. Legacy `.inp` files remain supported
for tolerant migration workflows.

Minimal top-level JSON structure:

```json
{
  "grid": {},
  "stations": [],
  "sources": [],
  "receptors": [],
  "run": {},
  "terrain": {}
}
```

### Grid

The grid defines the local model domain.

```json
{
  "grid": {
    "nx": 101,
    "ny": 101,
    "dx": 100.0,
    "dy": 100.0,
    "x0": 0.0,
    "y0": 0.0,
    "projection": "LOCAL"
  }
}
```

`nx` and `ny` are positive integer counts. `dx` and `dy` are positive spacing
values in meters for local-grid workflows.

### Stations

Stations provide wind, temperature, and mixing-height observations for
diagnostic SpritzMet downscaling.

```json
{
  "stations": [
    {
      "id": "S1",
      "x": 0.0,
      "y": 0.0,
      "wind_speed": 3.0,
      "wind_dir": 270.0,
      "temperature": 294.0,
      "mixing_height": 900.0,
      "precipitation_rate": 0.0
    }
  ]
}
```

`wind_dir` is the meteorological direction from which the wind blows, in
degrees. If no stations are supplied, SpritzMet uses deterministic default
values from `run.default_u`, `run.default_v`, `run.default_temperature`, and
`run.default_mixing_height`. `precipitation_rate` is optional, in `mm h-1`, and
is used by precipitation washout when enabled. If no stations are supplied,
`run.default_precipitation_rate` provides a uniform precipitation field.

WRF-driven SpritzWRF -> SpritzMet downscaling can also use weather-station
measurements from CSV as an optional residual correction after deterministic,
AI, or diffusion downscaling. Use `--station-measurements stations.csv` in use
case 01. CSV rows may provide local `x,y` coordinates in meters or
`latitude,longitude`; observation columns are `wind_speed` with `wind_dir`,
and/or `precipitation_rate`.

### Sources

Sources define emission points or finite source geometries.

```json
{
  "sources": [
    {
      "id": "P1",
      "x": 100.0,
      "y": 1000.0,
      "z": 0.0,
      "emission_rate": 25.0,
      "source_type": "point",
      "height_agl_m": 40.0,
      "material": "generic",
      "start_datetime": "2026-06-01T00:00:00+00:00",
      "end_datetime": "2026-06-01T12:00:00+00:00",
      "stack_height": 40.0,
      "stack_diameter": 1.5,
      "exit_velocity": 12.0,
      "exit_temperature": 370.0,
      "deposition_velocity": 0.001,
      "wet_scavenging": 0.00001,
      "decay_rate": 0.0
    }
  ]
}
```

Supported `source_type` values are `point`, `area`, `volume`, `line`, `road`,
`roadway`, `flare`, and `spray`. Finite source dimensions use `width`,
`length`, and `height`. Loss terms are first-order screening terms and must be
validated for each scientific application.

`height_agl_m` records source height above local ground level. For chimney
workflows, Spritz also accepts `chimney_height_m`, `stack_height_m`,
`height_on_ground_m`, and `release_height_m` aliases and maps them to the
effective stack height used by the dispersion kernel. Keep `z` for terrain or
source base elevation and `height_agl_m` for the above-ground release height.

`material` is validated as one of `generic`, `paper`, or `plastic`. The core
dispersion model preserves that metadata; use case 02 converts the material
preset into documented screening temperature, heat-release, and emission
assumptions before writing the Spritz configuration.

Multiple fire or emission events are represented by multiple entries in
`sources`. Each source can carry its own `latitude`, `longitude`,
`height_agl_m`, `start_datetime`, `end_datetime`, and `material`.

### Time Windows And Firefighter Actions

Spritz supports absolute ISO-8601 datetimes for weather, event, and firefighter
periods. Use timezone-aware strings when the distinction matters.

```json
{
  "run": {
    "weather_start_datetime": "2026-06-01T00:00:00+00:00",
    "weather_end_datetime": "2026-06-01T12:00:00+00:00",
    "event_start_datetime": "2026-06-01T00:00:00+00:00",
    "event_end_datetime": "2026-06-01T12:00:00+00:00",
    "firefighters_start_datetime": "2026-06-01T06:00:00+00:00",
    "firefighters_end_datetime": "2026-06-01T09:00:00+00:00",
    "firefighters_emission_factor": 0.5,
    "output_interval_s": 3600.0
  }
}
```

When `output_interval_s` is set and weather start/end datetimes are present,
Spritz uses the weather period as the default output duration. Source-level
start/end datetimes override the global event window for that source. During the
firefighter window, emissions are multiplied by `firefighters_emission_factor`,
which must be between 0 and 1. Output rows include an ISO-8601 `datetime`
column or NetCDF `time_datetime` coordinate when absolute weather time is known.

### Precipitation Washout

Precipitation washout is controlled from JSON:

```json
{
  "run": {
    "precipitation_washout": true,
    "precipitation_washout_coefficient_s_per_mm_h": 0.00001
  }
}
```

SpritzWRF extracts WRF precipitation when common rate variables
(`RAINRATE`, `PRECIP_RATE`, `precipitation_rate`, `precip_rate`) exist. If only
accumulated WRF rain fields are available (`RAINC`, `RAINNC`, `RAINSH`), it
uses the increment at the selected WRF time as a millimeters-per-hour screening
rate. Four-dimensional WRF wind variables are sliced as `time, level, y, x`
with independent `time_index` and `level_index` selections. SpritzMet
downscales the selected wind and precipitation fields to the local grid and
writes wind as `eastward_wind(time,z,y,x)` / `northward_wind(time,z,y,x)` and
diagnostic 10 m wind, when available, as `U10M(time,y,x)` /
`V10M(time,y,x)`. Surface precipitation is written as
`precipitation_rate(time,y,x)`. When washout is
enabled, Spritz adds `coefficient * mean_precipitation_rate` to each source wet
scavenging rate.

If WRF precipitation is unavailable, SpritzMet writes zero precipitation. For
station-only or synthetic runs, `run.default_precipitation_rate` can provide a
uniform local-grid value.

### Receptors

Receptors are explicit concentration sampling points.

```json
{
  "receptors": [
    {
      "id": "R1",
      "x": 1000.0,
      "y": 1000.0,
      "z": 1.5,
      "latitude": 40.926506,
      "longitude": 14.380875
    }
  ]
}
```

Latitude and longitude are optional. When present, visualization can plot
geographic receptor maps directly. If `receptors` is empty and
`concentration_output` is not set, Spritz samples the model grid at `z=0`.

## Backend Selection

Spritz uses one concentration command and one workflow. The backend is selected
from JSON `run.backend` or a CLI override.

```json
{
  "run": {
    "backend": "gaussian"
  }
}
```

Accepted backend values:

- `gaussian` or `gauss`: Gaussian Spritz puff/plume backend.
- `particles` or `particle`: Lagrangian particle screening backend.

CLI override:

```bash
sprtz run examples/minimal.json --backend particles --output-dir output-particles
spritz --config examples/minimal.json --meteo output/meteo.nc --output output/concentration.nc --backend particles --format netcdf
```

`sprtz-particles` remains available as a compatibility alias for older scripts,
but new workflows should use `spritz --backend particles` or JSON `run.backend`.

## Gaussian Run Options

Gaussian run options live under `run`.

```json
{
  "run": {
    "backend": "gaussian",
    "numerical_mode": "puff",
    "stability": "D",
    "averaging_time_s": 3600.0,
    "output_interval_s": 600.0,
    "output_duration_s": 3600.0,
    "output_start_s": 600.0,
    "weather_start_datetime": "2026-06-01T00:00:00+00:00",
    "weather_end_datetime": "2026-06-01T12:00:00+00:00",
    "event_start_datetime": "2026-06-01T00:00:00+00:00",
    "event_end_datetime": "2026-06-01T12:00:00+00:00",
    "precipitation_washout": true,
    "stack_tip_downwash": true,
    "threshold": 0.00001
  }
}
```

`numerical_mode` can be `puff` or `plume`. If `output_interval_s` is omitted,
Spritz writes one legacy-compatible output at `time=0`. If it is supplied,
Spritz writes rows at the requested cadence, independent from the meteorological
input cadence.

## Particle Run Options

Particle options also live under `run`.

```json
{
  "run": {
    "backend": "particles",
    "particles": 2000,
    "seed": 42,
    "particle_duration_s": 3600.0,
    "particle_sigma_h": 250.0,
    "particle_sigma_z": 80.0,
    "particle_receptor_radius": 400.0
  }
}
```

For a fixed seed, particle results are deterministic. MPI particle runs use a
per-source random stream so changing rank count does not change the stream used
for a given source. Heat-release plume rise is sampled by particle travel age:
young particles stay close to release height, while older particles are lifted
according to the same clean-room plume-rise screening relation used by the
Gaussian backend.

## Receptor Tables And 3D Fields

Spritz always writes a receptor-table view for concentration output. In NetCDF-CF
this table is:

```text
concentration(time, receptor)
dry_flux(time, receptor)
wet_flux(time, receptor)
x(receptor), y(receptor), z(receptor), receptor_id(receptor)
```

To request a model-grid concentration field, set `run.concentration_output`.

```json
{
  "run": {
    "backend": "gaussian",
    "concentration_output": "grid",
    "field_z_levels": [0.0, 25.0, 50.0]
  }
}
```

`field_z_levels` may also be generated from a documented distribution. The
exponential preset below creates 21 plume-field altitudes in metres above mean sea level using
`10 * exp(level_index)` for `level_index` values `0..20`.

```json
{
  "run": {
    "concentration_output": "grid",
    "field_z_levels": {
      "preset": "exponential",
      "count": 21,
      "base_m": 10.0
    }
  }
}
```

Accepted `concentration_output` values:

- `receptors`: sample explicit receptors, or grid cells at `z=0` if no
  receptors are supplied.
- `grid`: sample every model-grid cell at every `field_z_levels` altitude.
- `both`: sample explicit receptors and the model-grid field.

When the rows form a complete grid, NetCDF-CF output also includes:

```text
concentration_field(time, field_z, field_y, field_x)
dry_flux_field(time, field_z, field_y, field_x)
wet_flux_field(time, field_z, field_y, field_x)
field_x(field_x), field_y(field_y), field_z(field_z)
```

If the configuration metadata contains `center_lat` and `center_lon`, generated
grid-field receptor rows also include WGS84 `latitude` and `longitude`. For
centered odd grids, the middle field cell is `x=0, y=0` and maps back to that
configured geographic center.

If `netCDF4` is not installed, `.nc` output falls back to JSON with the same
logical `rows` table and a `field` object when gridded output is available.

For large domains, remember that grid output creates `nx * ny *
len(field_z_levels)` receptor calculations for each output time.

Complete gridded outputs can also be written as clean-room CALPUFF-style binary
concentration files:

```bash
spritz --config examples/minimal.json \
  --meteo output/meteo.nc \
  --output output/concentration.calpuff \
  --format calpuff \
  --backend particles
```

This binary export preserves the same `time`, `field_z`, `field_y`, and
`field_x` grid used by NetCDF-CF concentration fields and stores concentration,
dry flux, and wet flux slabs. It is intended for comparison workflows; NetCDF-CF
remains the canonical Sprtz interchange.

## Direct Commands

Run SpritzMet:

```bash
spritzmet --config examples/minimal.json --output output/meteo.nc --format netcdf
```

Run unified Spritz concentration:

```bash
spritz --config examples/minimal.json --meteo output/meteo.nc --output output/concentration.nc --format netcdf
spritz --config examples/minimal.json --meteo output/meteo.nc --output output/particle.nc --format netcdf --backend particles
spritz --config examples/minimal.json --meteo output/meteo.nc --output output/particle.calpuff --format calpuff --backend particles
```

Run SpritzPost:

```bash
spritzpost --input output/concentration.nc --output output/post.json --threshold 0.00001
```

Plot concentration:

```bash
sprtz-plot --input output/concentration.nc --output output/concentration.png --title "Scenario A"
```

`tools/plotter.py` can render receptor-table NetCDF variables and gridded
fields such as `concentration_field` by passing `--variable concentration_field`
and selecting `--time-index` / `--level-index` as needed.
Zero or negative mass concentration is drawn transparent, and products carrying
both WGS84 longitude/latitude and local `x/y` axes show both coordinate systems
on map axes.
Use `tools/plotter.py --animate` to create map animations over every available
time frame, and set GIF repetition with `--gif-loop` (`0` loops forever). Use
`tools/profiler.py` for centralized time-varying vertical profiles from
`wind_speed(time,z,y,x)` or
`concentration_field(time,field_z,field_y,field_x)`; add `--animate` and
`--gif-loop` to create simulation-long profile GIFs with explicit loop control.
Profiler figures include the longitude/latitude of the local `x=0, y=0` point
when the NetCDF provides geographic coordinates.
Use `tools/render3d.py` for static or animated three-dimensional surface and
voxel views of compatible gridded volume variables. It uses all vertical levels
by default. With `--terrain geo.nc`, it offsets height-above-ground plume levels
by the local DEM, masks height-above-sea-level plume levels below the DEM, and
uses ASL model levels as vertical ticks. It draws the ground with a terrain
elevation color scale unless `--ground-color land-cover` is selected. Use
`--vertical-exaggeration N` with `N >= 1` to exaggerate vertical relief in the
display; longitude and latitude are used for 3-D horizontal tick labels when
available.

## Terrain And GEO Products

Spritz has two Terrain surfaces:

- `terrain`: lightweight local ASCII-raster resampling.
- `sprtz-terrain fetch`: provider-style DEM and land-cover acquisition,
  caching, regridding, land-use remapping, surface parameters, and GEO output.

Offline local example:

```bash
sprtz-terrain fetch --config examples/highres_terrain_local.json --json
sprtz run examples/highres_terrain_local.json --output-dir output-terrain-local --interchange json
```

Online providers require explicit opt-in:

```bash
sprtz-terrain fetch --config examples/highres_terrain_auto.json --allow-network
```

Terrain outputs should preserve provenance such as DEM source, dataset,
resolution, access date, land-cover source/year, source and target CRS,
resampling methods, cache key, and software version. Never bilinearly
resample categorical land-cover classes with continuous methods.

## NetCDF-CF And Fallbacks

NetCDF-CF is preferred for module interoperability. Install `.[netcdf]` for
true NetCDF files. Without `netCDF4`, `.nc` writes use deterministic JSON
fallback payloads so minimal environments and tests remain usable.

Sprtz-produced NetCDF files follow strict CF conventions. Files with a time
axis include a CF `time(time)` coordinate; when a physical datetime is known,
its units are absolute UTC units such as
`seconds since 2026-05-27 00:00:00 UTC`. SpritzWRF extracts WRF valid time from
WRF/CF metadata (`Times`, CF `time`, or explicit global time attributes) and
never from filenames.

CSV and legacy text outputs are useful for migration and tabular inspection.
They preserve receptor rows, concentration, dry flux, wet flux, and coordinates,
but they do not carry a structured 3D field array.

## MPI And HPC

Serial is the default:

```bash
sprtz run examples/minimal.json --parallel serial
```

Automatic MPI when launched under an MPI runtime:

```bash
mpiexec -n 4 sprtz run examples/minimal.json --parallel auto --interchange netcdf
```

Required MPI:

```bash
mpiexec -n 4 sprtz run examples/minimal.json --parallel mpi --backend particles
```

Only rank 0 writes shared meteorology, concentration, post-processing, and
workflow files. Gaussian runs partition receptors. Particle runs partition
sources.

## Visualization

Use `sprtz-plot` for local or geographic receptor scatter maps. Geographic
plots can use receptor latitude/longitude directly or transform local
coordinates when the grid center is supplied.

```bash
sprtz-plot \
  --input output/concentration.nc \
  --output output/concentration_map.png \
  --coordinates geographic \
  --center-lat 40.926506 \
  --center-lon 14.380875
```

Network map tiles are never fetched implicitly. Use `--tile-provider` and
`--allow-network-basemap` only when online basemaps are explicitly desired.

## Use Cases

Documented didactic workflows live under repository-level `usecases/` and are
not package modules.

- `01_high_resolution_wind_field`: SpritzWRF to SpritzMet WRF downscaling.
- `02_wildfire_arson_effects`: wildfire/arson screening scenario.
- `03_satellite_ai_evaluation`: compare concentration output with a satellite
  mask.
- `04_production_incidents`: catalog-driven receptor and map workflow.
- `05_sailing_wind_forecast`: high-resolution wind product schema for sailing.
- `06_acerra_waste_to_energy`: 12-hour Acerra waste-to-energy chimney screening
  scenario starting on 2026-06-01 with 110 m above-ground release height.

Each use case has its own README with inputs, commands, outputs, assumptions,
and validation notes.

## Required Checks Before Completing Changes

From the repository root:

```bash
python -m compileall -q src tests
python -m pytest -q
python -m sprtz doctor
python -m sprtz validate examples/minimal.json
python -m sprtz run examples/minimal.json --output-dir /tmp/sprtz_smoke --interchange json
find . -type d -name __pycache__ -prune -exec rm -rf {} +
rm -rf .pytest_cache .mypy_cache .ruff_cache build dist
find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete
python scripts/check_release.py
```

When `netCDF4` is installed:

```bash
python -m sprtz run examples/minimal.json --output-dir /tmp/sprtz_smoke_nc --interchange netcdf
```

When MPI is installed:

```bash
mpiexec -n 2 python -m sprtz run examples/minimal.json --output-dir /tmp/sprtz_smoke_mpi --parallel mpi --interchange json
```

## Troubleshooting

`configuration file not found`: check the path passed to `sprtz validate`,
`sprtz run`, or `spritz --config`.

`run.backend must be gaussian/gauss or particles`: use one of the supported
backend values in JSON or CLI.

`run.concentration_output must be receptors, grid, or both`: check the
field-output mode spelling.

`run.field_z_levels must be non-negative`: vertical field levels are altitudes
above mean sea level in metres.

No true NetCDF file was produced: install `netCDF4` with `python -m pip install
-e .[netcdf]`. Without it, Spritz writes JSON fallback payloads.

MPI command runs serially: use `--parallel mpi` to require MPI and fail fast when
`mpi4py` or an MPI launcher is unavailable. Use `--parallel auto` for portable
scripts that may run on laptops.

No geographic map appears: provide receptor latitude/longitude or supply
`--center-lat` and `--center-lon` so local x/y coordinates can be transformed.

## References

- Wilson, G., Aruliah, D. A., Brown, C. T., Hong, N. P. C., Davis, M., Guy, R. T., Haddock, S. H. D., Huff, K. D., Mitchell, I. M., Plumbley, M. D., Waugh, B., White, E. P., and Wilson, P. (2014). Best practices for scientific computing. PLOS Biology, 12(1), e1001745. https://doi.org/10.1371/journal.pbio.1001745
- Sandve, G. K., Nekrutenko, A., Taylor, J., and Hovig, E. (2013). Ten simple rules for reproducible computational research. PLOS Computational Biology, 9(10), e1003285. https://doi.org/10.1371/journal.pcbi.1003285
- Hanna, S. R. (1989). Confidence limits for air quality model evaluations, as estimated by bootstrap and jackknife resampling methods. Journal of the Air and Waste Management Association, 39(9), 1170-1175.
- Chang, J. C., and Hanna, S. R. (2004). Air quality model performance evaluation. Meteorology and Atmospheric Physics, 87, 167-196.
