# Use case 02 — Wildfire or arson effects

## Narrative

This use case builds a reproducible screening assessment for smoke released by
a wildfire or arson event. The full demo starts from a known geographic fire
location, routes WRF forcing through SpritzWRF and SpritzMet, constructs
documented screening source terms, and runs particle and Gaussian dispersion
against the same meteorology. Its products support comparison of plume timing,
spatial patterns, vertical structure, deposition, and backend differences.

This is a clean-room teaching and screening workflow, not a certified
fire-emission inventory or regulatory-equivalent assessment.

## Available setup scenarios

### WRF-driven guided demo

[`demo/README.md`](demo/README.md) documents the complete geographic workflow:
WRF acquisition, optional COP30/LC100 terrain preparation, 100 m wind
downscaling, event configuration, both dispersion backends, comparison, and
visualization. Use it for incident-oriented experiments and scientific
inspection.

The guided demo also provides a complete SLURM batch example for MPI
meteorological downscaling followed by particle and Gaussian dispersion; see
[`demo/README.md`](demo/README.md#mpi-execution-on-a-slurm-cluster).
Separate non-blocking launchers and their dependency graph are documented in
[`slurm/README.md`](slurm/README.md).

### Offline scripts-only pipeline

[`pipeline/pipeline.sh`](pipeline/pipeline.sh) runs a deterministic local-grid
scenario using only public wrappers under `scripts/`. It uses synthetic station
meteorology and performs no network access:

```bash
bash usecases/02_wildfire_arson_effects/pipeline/pipeline.sh
```

See [`pipeline/README.md`](pipeline/README.md) for parameters and outputs.

### CWL and WCL

[`workflow/workflow.cwl`](workflow/workflow.cwl) exposes the scripts-only
pipeline through CWL v1.2 with typed inputs and declared products.
[`workflow/workflow.wcl`](workflow/workflow.wcl) provides the corresponding
engine-neutral WCL entry point. Details are in
[`workflow/README.md`](workflow/README.md).

### Dagonstar

[`dagonstar/workflow.py`](dagonstar/workflow.py) is an external-orchestrator
sketch. Dagonstar must be installed and configured separately.

## Inputs and products

The full setup uses WRF meteorology and may use DEM and categorical land cover.
The offline setup generates its own configuration and meteorology. Principal
products include event JSON, NetCDF-CF meteorology, particle and Gaussian
concentrations, postprocessing reports, comparison metrics in the full demo,
and optional maps, profiles, animations, and 3-D renders.

When running the full setup on an HPC system with a shared outbound IP, use the
LC100 shared-cache procedure in [`demo/README.md`](demo/README.md). Direct GDAL
range reads can exhaust Zenodo's per-IP request limit.

All operational data belongs under the repository-level `data/` tree unless an
explicit path is supplied. Date-time arguments use `YYYYMMDDZhhmm`.

## Limitations

Operational interpretation requires validated fuel loading, combustion phase,
plume-injection height, terrain, observations, and independent evaluation.
Material presets and source estimates in the demo are configurable screening
assumptions, not universal Spritz core constants.

## References

Scientific assumptions and peer-reviewed references are maintained in the
numerical-model, particle-model, and SpritzWRF/SpritzMet documentation.
