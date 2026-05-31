# Particle-based Sprtz alternative

`sprtz.models.particles` implements a Lagrangian particle screening backend that accepts the same `SuiteConfig`, the same SpritzMet meteorology files, and writes the same receptor concentration table as the Gaussian Spritz backend.

CLI:

```bash
sprtz-particles --config examples/minimal.json --meteo output/meteo.nc --output output/particle_concentration.nc
sprtz run examples/minimal.json --backend particles --interchange netcdf --output-dir output-particles
```

The particle backend is deterministic for a fixed seed. Relevant `run` keys are `particles`, `seed`, `particle_duration_s`, `particle_sigma_h`, `particle_sigma_z`, and `particle_receptor_radius`.

Scientific scope: this is an interoperability-ready particle module for teaching, sensitivity tests, and migration scaffolding. Operational use needs independent validation and a documented acceptance envelope.
