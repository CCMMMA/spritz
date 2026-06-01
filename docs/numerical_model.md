# Numerical model notes

Sprtz v0.4.0 improves the numerical core while keeping the clean-room boundary. The implementation is guided by public atmospheric-dispersion concepts and component roles, but it does not translate or embed proprietary Fortran source code.

## Feature alignment

The public Version 7 materials describe a non-steady-state transport, dispersion, and deposition model, Version 7 additions for flare, roadway, and aerial spray sources, and newer postprocessors for averages, maxima, ranked values, and percentiles. Sprtz implements independent counterparts at screening fidelity:

- non-steady Gaussian puff kernel with longitudinal, lateral, and vertical spreads;
- finite source-size treatment for area, roadway/line, volume, spray-like, and point sources;
- flare-oriented inputs such as heat release and effective release height;
- stack-tip downwash and Briggs-style plume-rise screening;
- first-order chemical decay, wet scavenging, dry deposition, and settling-loss factors;
- concentration plus dry and wet deposition-flux columns in CSV, legacy table, and NetCDF-CF outputs;
- SpritzPost-style maximum, percentile, nth-rank, running-average, and block-average statistics;
- particle backend using the same configuration, meteorology, and output schema.

## Configuration keys

Source-level numerical keys:

```json
{
  "source_type": "point | area | volume | line | road | roadway | flare | spray",
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

Run-level numerical keys:

```json
{
  "numerical_mode": "puff",
  "averaging_time_s": 3600,
  "output_interval_s": 600,
  "stack_tip_downwash": true
}
```

Use `numerical_mode = plume` to reproduce the older steady Gaussian screening pathway.
Omit `output_interval_s` to keep the legacy single output at `time=0`. When it
is set, Spritz emits concentration/deposition rows at that interval, independent
of the meteorological input cadence. Puff-mode time-resolved output advects the
representative puff center with the mean wind; plume mode remains steady at each
requested output time.

## Scientific scope

The numerical methods are transparent, deterministic, unit-tested approximations suitable for research software infrastructure, migration scaffolding, education, sensitivity testing, and early-stage workflow development. Regulatory equivalence or operational acceptance requires independent validation against accepted cases and an explicit acceptance envelope.
