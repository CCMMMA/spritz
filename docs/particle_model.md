# Particle-based Spritz alternative

## Scientific Scope

This document describes the particle-based Sprtz alternative to the Gaussian backend. It frames the method as a stochastic Lagrangian screening model with deterministic seeds and comparable gridded outputs.

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

`sprtz-particles` remains as a compatibility alias for older scripts and forces the same particle backend. The particle backend is deterministic for a fixed seed. Relevant `run` keys are `particles`, `seed`, `particle_duration_s`, `particle_advection_steps`, `particle_kx_m2_s`, `particle_ky_m2_s`, `particle_kz_m2_s`, `particle_sigma_h`, `particle_sigma_z`, `particle_receptor_radius`, `particle_vertical_boundary`, `particle_top_boundary`, and `particle_top_m`.

Horizontal and vertical turbulent diffusion use a Fickian random walk in each
advection substep:

```text
dx_random = sqrt(2 Kx dt) N(0, 1)
dy_random = sqrt(2 Ky dt) N(0, 1)
dz_random = sqrt(2 Kz dt) N(0, 1)
```

This makes ensemble variance grow linearly with elapsed time instead of with
the number of numerical substeps. If explicit diffusivity keys are absent,
legacy `particle_sigma_h` is interpreted as a target one-dimensional spread
over `particle_duration_s`, not as a per-step displacement. Vertical boundaries
are explicit: `particle_vertical_boundary = reflect` mirrors particles above
ground, while `absorb_deposit` removes their airborne mass at ground contact.
`particle_top_boundary = reflect` mirrors particles below `particle_top_m`;
`open` removes mass that leaves the model top. Decay, wet scavenging, dry
deposition, and settling reduce particle weights with first-order exponential
loss factors, so airborne mass remains non-negative.

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

## References

- Weil, J. C., Sykes, R. I., and Venkatram, A. (1992). Evaluating air-quality models: review and outlook. Journal of Applied Meteorology, 31(10), 1121-1145.
- Draxler, R. R., and Hess, G. D. (1998). An overview of the HYSPLIT_4 modelling system for trajectories, dispersion, and deposition. Australian Meteorological Magazine, 47(4), 295-308.
- Stohl, A., Forster, C., Frank, A., Seibert, P., and Wotawa, G. (2005). Technical note: The Lagrangian particle dispersion model FLEXPART version 6.2. Atmospheric Chemistry and Physics, 5, 2461-2474.
- Courant, R., Friedrichs, K., and Lewy, H. (1928). Uber die partiellen Differenzengleichungen der mathematischen Physik. Mathematische Annalen, 100, 32-74.
- LeVeque, R. J. (1997). Wave propagation algorithms for multidimensional hyperbolic systems. Journal of Computational Physics, 131(2), 327-353.
