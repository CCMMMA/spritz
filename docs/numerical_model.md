# Numerical model notes

Spritz v0.4.0 improves the numerical core while keeping the clean-room boundary. The implementation is guided by public atmospheric-dispersion concepts and component roles, but it does not translate or embed proprietary Fortran source code.

## Feature alignment

The public Version 7 materials describe a non-steady-state transport, dispersion, and deposition model, Version 7 additions for flare, roadway, and aerial spray sources, and newer postprocessors for averages, maxima, ranked values, and percentiles. Spritz implements independent counterparts at screening fidelity:

- non-steady Gaussian puff kernel with longitudinal, lateral, and vertical spreads;
- finite source-size treatment for area, roadway/line, volume, spray-like, and point sources;
- flare-oriented inputs such as heat release and effective release height;
- stack-tip downwash and Briggs-style plume-rise screening;
- first-order chemical decay, wet scavenging, precipitation-driven washout, dry deposition, and settling-loss factors;
- absolute weather, fire/arson, source, and firefighter-action time windows;
- source metadata for above-ground release height and screening material presets;
- concentration plus dry and wet deposition-flux columns in CSV, legacy table, and NetCDF-CF outputs;
- optional model-grid 3D concentration/deposition fields in NetCDF-CF and JSON fallback outputs;
- SpritzPost-style maximum, percentile, nth-rank, running-average, and block-average statistics;
- particle backend using the same configuration, meteorology, and output schema.

## Configuration keys

Source-level numerical keys:

```json
{
  "source_type": "point | area | volume | line | road | roadway | flare | spray",
  "latitude": 40.978473,
  "longitude": 14.384058,
  "height_agl_m": 110.0,
  "material": "generic | paper | plastic",
  "start_datetime": "2026-06-01T00:00:00+00:00",
  "end_datetime": "2026-06-01T12:00:00+00:00",
  "stack_diameter": 1.5,
  "width": 0.0,
  "length": 0.0,
  "height": 0.0,
  "heat_release": 0.0,
  "deposition_velocity": 0.001,
  "wet_scavenging": 0.00001,
  "decay_rate": 0.0,
  "settling_velocity": 0.0
}
```

`height_agl_m` is the source release height above local ground level. Chimney
JSON may also use `chimney_height_m`, `stack_height_m`, `height_on_ground_m`, or
`release_height_m`; these aliases are normalized to `stack_height`.
Source-level `start_datetime` and `end_datetime` override the global event
window for that source. This is the core multi-fire representation: multiple
fire events are multiple source records, each with its own position, height,
time window, and material.

`material` is constrained to `generic`, `paper`, or `plastic`. The numerical
kernel does not hide fuel-specific constants; use case generators translate
material choices into explicit emission rate, heat release, and exit-temperature
values in the written JSON configuration.

Run-level numerical keys:

```json
{
  "backend": "gaussian",
  "numerical_mode": "puff",
  "averaging_time_s": 3600,
  "output_interval_s": 600,
  "weather_start_datetime": "2026-06-01T00:00:00+00:00",
  "weather_end_datetime": "2026-06-01T12:00:00+00:00",
  "event_start_datetime": "2026-06-01T00:00:00+00:00",
  "event_end_datetime": "2026-06-01T12:00:00+00:00",
  "firefighters_start_datetime": "2026-06-01T06:00:00+00:00",
  "firefighters_end_datetime": "2026-06-01T09:00:00+00:00",
  "firefighters_emission_factor": 0.5,
  "precipitation_washout": true,
  "precipitation_washout_coefficient_s_per_mm_h": 0.00001,
  "concentration_output": "receptors | grid | both",
  "field_z_levels": [0.0, 25.0, 50.0],
  "stack_tip_downwash": true
}
```

Use `backend = gaussian` or `backend = gauss` for the Gaussian Spritz backend
and `backend = particles` for the Lagrangian particle backend. Use
`numerical_mode = plume` to reproduce the older steady Gaussian screening pathway.
Omit `output_interval_s` to keep the legacy single output at `time=0`. When it
is set, Spritz emits concentration/deposition rows at that interval, independent
of the meteorological input cadence. Puff-mode time-resolved output advects the
representative puff center with the mean wind; plume mode remains steady at each
requested output time.

When weather start/end datetimes are supplied, `output_interval_s` defaults to
covering the weather period. Output rows carry absolute `datetime` values. The
global fire/arson event window controls all sources that do not provide their
own source-level time window. During the firefighter-action interval, source
emissions are multiplied by `firefighters_emission_factor`.

When `precipitation_washout` is true, Spritz computes an additional first-order
wet-removal rate as:

```text
washout_rate_s-1 = precipitation_washout_coefficient_s_per_mm_h * mean_precipitation_rate_mm_h-1
```

The precipitation rate is read from the SpritzMet meteorology payload. For
WRF-driven workflows, SpritzWRF extracts common WRF rate fields or accumulated
rain increments and SpritzMet interpolates them onto the local grid. If no
precipitation field is present, the rate is zero and the option has no effect.

`concentration_output` controls where concentrations are sampled:

- `receptors` uses the named receptor list, or the model grid at `z=0` when no
  receptors are supplied.
- `grid` samples every model-grid cell at every `field_z_levels` height and
  writes `concentration_field(time, field_z, field_y, field_x)` in NetCDF-CF.
- `both` keeps named receptors and also writes the model-grid field.

## Scientific scope

The numerical methods are transparent, deterministic, unit-tested approximations suitable for research software infrastructure, migration scaffolding, education, sensitivity testing, and early-stage workflow development. Regulatory equivalence or operational acceptance requires independent validation against accepted cases and an explicit acceptance envelope.
