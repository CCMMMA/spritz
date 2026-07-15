# Use case 02 — Wildfire/arson scripts-only pipeline

This pipeline provides a deterministic, self-contained wildfire smoke
screening run using public command wrappers and the repository-level unified
plotter. Bash writes the scenario JSON; Spritz scripts validate it, interpolate
synthetic meteorology, run Gaussian and particle dispersion, postprocess both
results, and render figures.

This is intentionally different from the WRF-driven workflow in
[`../demo/README.md`](../demo/README.md). The demo is the appropriate workflow
for incident-specific WRF forcing, terrain-aware downscaling, geographic fire
locations, and backend comparison metrics.

For the WRF-driven MPI workflow on SLURM, including separate particle and
Gaussian stages, use the batch example in
[`../demo/README.md`](../demo/README.md#mpi-execution-on-a-slurm-cluster).

## Run

From the repository root or any other working directory:

```bash
bash usecases/02_wildfire_arson_effects/pipeline/pipeline.sh
```

The script resolves the repository root from its own location. Products are
written to `data/output/wildfire_case/` by default.

The NetCDF and plotting stages require the corresponding optional dependencies
from the `netcdf` and `viz` extras:

```bash
python3 -m pip install -e '.[netcdf,viz]'
```

## Scenario

The default scenario uses:

- a `31 × 31` local Cartesian grid with 100 m spacing;
- one synthetic upwind station with 4 m/s wind from 270 degrees;
- one generic area source at `(1500 m, 1500 m)`;
- a 35 g/s emission rate and 10 m release height above local ground;
- three explicit receptors;
- concentration fields at 0, 10, 50, and 100 m;
- Gaussian and particle backends using the same SpritzMet field;
- a fixed particle seed of `1234`;
- an hourly output interval.

The pipeline performs no network access and does not ingest WRF, DEM, or
land-cover data.

## Configuration

Set `SPRTZ_DATA_ROOT` to replace the repository-level `data/` root, or set
`SPRTZ_OUTPUT_DIR` to select the exact output directory.

All scenario settings may be overridden with environment variables:

| Variable | Default | Meaning |
| --- | ---: | --- |
| `PYTHON` | `python3` | Python interpreter |
| `NX`, `NY` | `31` | Local-grid dimensions |
| `DX`, `DY` | `100` | Grid spacing in metres |
| `WIND_SPEED_M_S` | `4.0` | Synthetic station wind speed |
| `WIND_FROM_DIRECTION_DEG` | `270.0` | Meteorological wind-from direction |
| `TEMPERATURE_K` | `298.0` | Station air temperature |
| `MIXING_HEIGHT_M` | `1000.0` | Mixing height |
| `PRECIPITATION_RATE_MM_H` | `0.2` | Precipitation rate |
| `EMISSION_RATE_G_S` | `35.0` | Source emission rate |
| `SOURCE_X_M`, `SOURCE_Y_M` | `1500.0` | Source coordinates |
| `SOURCE_HEIGHT_M` | `10.0` | Release height above local ground |
| `PARTICLE_SEED` | `1234` | Particle-backend random seed |
| `OUTPUT_INTERVAL_S` | `3600` | Concentration output interval |

For example:

```bash
WIND_SPEED_M_S=6.5 \
EMISSION_RATE_G_S=50 \
SPRTZ_OUTPUT_DIR=data/output/wildfire_sensitivity \
  bash usecases/02_wildfire_arson_effects/pipeline/pipeline.sh
```

## Pipeline stages

1. `scripts/sprtz_doctor.py` reports runtime and optional-feature availability.
2. Bash writes `wildfire_event.json`.
3. `scripts/sprtz.py validate` validates the configuration.
4. `scripts/spritzmet.py` writes the common NetCDF-CF meteorological field.
5. `scripts/spritz.py` runs Gaussian dispersion.
6. `scripts/spritz.py` runs particle dispersion with an explicit seed.
7. `scripts/spritzpost.py` summarizes the Gaussian output.
8. `scripts/spritzpost.py` summarizes the particle output.
9. `tools/plotter.py` renders one figure for each backend.

No Python module under `usecases/` is invoked by the pipeline.

## Products

The output directory contains:

```text
wildfire_event.json
meteo.nc
model_compare/
  gaussian/
    concentration.nc
    post.json
  particles/
    concentration.nc
    post.json
figures/
  gaussian_concentration.png
  particle_concentration.png
```

The two concentration products share the same configuration and meteorological
forcing. This scripts-only pipeline does not currently write the demo
workflow's `particle_gaussian_comparison.json`; comparisons can be performed
from the two NetCDF products.

## Scientific limitations

This is a clean-room teaching and screening scenario, not a certified
fire-emission inventory or regulatory-equivalent model. Its single synthetic
station is useful for deterministic software and workflow checks but does not
represent real atmospheric structure. Operational assessment requires
incident-specific fuel loading, combustion phase, plume-injection height,
terrain, time-varying meteorology, observations, and independent validation.

## References

No additional bibliographic references are required for this workflow
description. Scientific assumptions and peer-reviewed references are maintained
in the Spritz numerical-model and particle-model documentation.
