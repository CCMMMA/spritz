# Particle-based Spritz alternative

`sprtz.models.particles` implements a Lagrangian particle screening backend that accepts the same `SuiteConfig`, the same SpritzMet meteorology files, and writes the same receptor table and optional gridded field schema as the Gaussian Spritz backend. For SpritzMet NetCDF inputs, particles are advected through the full `eastward_wind(time,z,y,x)` / `northward_wind(time,z,y,x)` cube with deterministic substeps; when diagnostic `U10M/V10M` is available and the first physical `z` level is aloft, that 10 m above-ground wind is used as the lower-boundary layer. 2D legacy meteorology still uses a deterministic fallback.

CLI:

```bash
sprtz run examples/minimal.json --backend particles --interchange netcdf --output-dir output-particles
spritz --config examples/minimal.json --meteo output/meteo.nc --output output/particle_concentration.nc --backend particles --format netcdf
spritz --config examples/minimal.json --meteo output/meteo.nc --output output/particle_concentration.calpuff --backend particles --format calpuff
```

JSON can select particles without a CLI override:

```json
{
  "run": {
    "backend": "particles",
    "particles": 2000,
    "seed": 42
  }
}
```

`sprtz-particles` remains as a compatibility alias for older scripts and forces the same particle backend. The particle backend is deterministic for a fixed seed. Relevant `run` keys are `particles`, `seed`, `particle_duration_s`, `particle_advection_steps`, `particle_sigma_h`, `particle_sigma_z`, and `particle_receptor_radius`.

The particle backend also honors the shared Spritz run controls for source
activity windows, firefighter emission reduction, precipitation washout, and
optional 3D gridded output. Source-level `start_datetime` and `end_datetime`
control whether each source contributes at a requested output time; during a
configured firefighter window the source contribution is multiplied by
`run.firefighters_emission_factor`. When `run.precipitation_washout` is true,
the backend adds the WRF/SpritzMet `precipitation_rate` wet-removal term to the
particle loss rate. Heat-release plume rise is evaluated from each particle's
sampled travel age, so newly released particles remain near the release height
while older particles rise through the buoyant plume.

When `concentration_output` requests a complete grid, `--format calpuff` writes
a clean-room CALPUFF-style binary concentration export with the same horizontal,
vertical, and temporal axes as NetCDF-CF output. NetCDF-CF remains the canonical
Sprtz interchange.

Scientific scope: this is an interoperability-ready particle module for teaching, sensitivity tests, and migration scaffolding. Operational use needs independent validation and a documented acceptance envelope.
