# Use case 02 — Wildfire/arson workflows

This folder provides WCL and CWL wrappers for the scripts-only pipeline. Both
invoke `pipeline/pipeline.sh` as the canonical executable sequence.

## CWL

[`workflow.cwl`](workflow.cwl) is a CWL v1.2 workflow. It exposes every
environment override supported by the pipeline as a typed input and returns
the output directory plus the generated configuration, meteorology,
concentration products, postprocessing summaries, and figures.

Create a job file such as:

```yaml
repo_root:
  class: Directory
  path: ../../..
sprtz_output_dir: data/output/wildfire_cwl
wind_speed_m_s: 6.5
emission_rate_g_s: 50.0
```

From the repository root, run it with a CWL v1.2 implementation:

```bash
cwltool \
  usecases/02_wildfire_arson_effects/workflow/workflow.cwl \
  usecases/02_wildfire_arson_effects/workflow/job.yml
```

`repo_root` is required because the command runs the checked-out pipeline and
the repository-level scripts in place. Optional paths are strings because they
are passed directly to the shell pipeline as environment variables. Relative
output paths are resolved by the pipeline after it changes to the repository
root; absolute paths are preferable with distributed CWL runners.

The runner environment must provide Bash, Python 3.10 or newer, Spritz, and the
`netcdf` and `viz` optional dependencies. The workflow does not request a
container because no project container image is defined.

## WCL

[`workflow.wcl`](workflow.wcl) is the WCL entry point for the scripts-only
wildfire/arson screening pipeline. Its workflow step invokes:

```bash
bash usecases/02_wildfire_arson_effects/pipeline/pipeline.sh
```

The WCL command must run with the repository root as its working directory.
The pipeline resolves its own location, writes the scenario configuration, and
invokes only public Python wrappers under `scripts/`.

## Why the pipeline is one WCL step

The WCL files in this repository use a deliberately small, engine-neutral
syntax consisting of `WORKFLOW`, `DESCRIPTION`, `WORKDIR`, `STEP`, and
`COMMAND`. No repository-defined syntax exists for dependencies, declared
artifacts, environment parameters, or multiline configuration generation.

Keeping `pipeline.sh` as the executable source of truth avoids duplicating its
configuration JSON and execution order in WCL. Workflow engines with richer
dependency and artifact models may expand the shell pipeline into separate
tasks, using the stages documented in
[`../pipeline/README.md`](../pipeline/README.md).

## Configuration

Environment variables supplied to the WCL process are inherited by
`pipeline.sh`. Common overrides include:

- `SPRTZ_DATA_ROOT` and `SPRTZ_OUTPUT_DIR`;
- `PYTHON`;
- `NX`, `NY`, `DX`, and `DY`;
- `WIND_SPEED_M_S` and `WIND_FROM_DIRECTION_DEG`;
- `TEMPERATURE_K`, `MIXING_HEIGHT_M`, and
  `PRECIPITATION_RATE_MM_H`;
- `EMISSION_RATE_G_S`, `SOURCE_X_M`, `SOURCE_Y_M`, and
  `SOURCE_HEIGHT_M`;
- `PARTICLE_SEED` and `OUTPUT_INTERVAL_S`.

For example, an engine may execute the WCL command with:

```bash
SPRTZ_OUTPUT_DIR=data/output/wildfire_wcl \
WIND_SPEED_M_S=6.5 \
EMISSION_RATE_G_S=50 \
  bash usecases/02_wildfire_arson_effects/pipeline/pipeline.sh
```

## Pipeline behavior

The invoked pipeline:

1. checks the runtime environment;
2. creates a deterministic synthetic wildfire scenario;
3. validates the generated configuration;
4. creates common SpritzMet meteorology;
5. runs Gaussian and particle dispersion;
6. postprocesses both concentration products;
7. renders a concentration figure for each backend.

It performs no hidden network access and does not ingest WRF, DEM, or
land-cover data. See the pipeline README for parameter defaults, dependencies,
product paths, and scientific limitations.

## Outputs

By default, products are written under `data/output/wildfire_case/`:

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

## Legacy WCL file

`usecase.wcl` describes the older demo-step workflow and remains separate for
compatibility. New scripts-only workflow integrations should use
`workflow.wcl`.

## References

No additional bibliographic references are required for this workflow
description. Scientific assumptions and peer-reviewed references are
maintained in the Spritz numerical-model and particle-model documentation.
