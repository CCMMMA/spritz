# Examples

`minimal.json` and `minimal.inp` describe the same synthetic domain: a 5 x 4 local grid, two stations, one point source, and two receptors.

Recommended interoperability workflow uses NetCDF-CF:

```bash
sprtz run examples/minimal.json --output-dir output --interchange netcdf
sprtz run examples/minimal.json --output-dir output-particles --backend particles --interchange netcdf
sprtz-plot --input output/concentration.nc --output output/concentration.png
```

`minimal.json` makes the default `run.backend` explicit. Set
`"backend": "particles"` in JSON, or pass `--backend particles`, to use the
particle backend. Set `"concentration_output": "grid"` and provide
`"field_z_levels": [0.0, 25.0, 50.0]` when a gridded 3D concentration field is
needed in NetCDF-CF output. The point source also shows `height_agl_m` and
`material`; `run.precipitation_washout` is explicitly false so the baseline
example stays numerically stable.

For time-aware or WRF-precipitation-driven runs, add keys such as:

```json
{
  "run": {
    "weather_start_datetime": "2026-06-01T00:00:00+00:00",
    "weather_end_datetime": "2026-06-01T12:00:00+00:00",
    "event_start_datetime": "2026-06-01T00:00:00+00:00",
    "event_end_datetime": "2026-06-01T12:00:00+00:00",
    "precipitation_washout": true
  }
}
```

High-resolution Terrain examples:

```bash
sprtz-terrain fetch --config examples/highres_terrain_local.json --json
sprtz run examples/highres_terrain_local.json --output-dir output-terrain-local --interchange json
sprtz-terrain fetch --config examples/highres_terrain_auto.json --allow-network
```

`highres_terrain_local.json` is the offline CI-safe example. `highres_terrain_auto.json`
documents the Copernicus DEM and ESA WorldCover provider configuration and
requires explicit network/provider access.

Legacy-compatible text/CSV workflow is still available:

```bash
spritzmet --config examples/minimal.inp --output output/meteo.json --format json
spritz --config examples/minimal.inp --meteo output/meteo.json --output output/concentration.csv --format csv
spritz --config examples/minimal.inp --meteo output/meteo.json --output output/particle_concentration.csv --format csv --backend particles
spritzpost --input output/concentration.csv --output output/post.json
```

`sprtz-particles` remains a compatibility alias for older scripts.
