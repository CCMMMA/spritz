# Use case 11 — Backward fire-origin attribution

## Narrative

This use case estimates likely ignition locations from observed burned or fire
points and wind direction. It combines backward firefront attribution with a
forward context simulation so candidate origins can be inspected against the
same meteorological and fire-spread assumptions.

## Available setup scenarios

- [`demo/README.md`](demo/README.md) documents guided ignition estimation,
  optional WRF/terrain preparation, likelihood mapping, 3-D context, and HPC
  execution.
- [`pipeline/pipeline.sh`](pipeline/pipeline.sh) runs the scripts-only
  attribution and context workflow:

  ```bash
  bash usecases/11_backward_fire_origin/pipeline/pipeline.sh
  ```

- [`workflow/usecase.wcl`](workflow/usecase.wcl) and
  [`workflow/README.md`](workflow/README.md) provide WCL setup.
- [`dagonstar/workflow.py`](dagonstar/workflow.py) is the Dagonstar-oriented
  task graph.

## Inputs and products

Inputs include observed fire points, wind context, and firefront
configuration. Real investigations should add aligned WRF meteorology, DEM,
land cover, fuel information, observation uncertainty, and provenance.
Products include ignition-likelihood output, meteorological and forward-fire
context, postprocessing, and publication diagnostics.

## Limitations

Backward likelihood does not prove causation or exact ignition time. Results
are sensitive to observation coverage, wind, terrain, fuel, suppression,
spotting, and model assumptions and require independent corroboration.

## References

Scientific assumptions and peer-reviewed references are maintained in the
SpritzFire, backward-model, and numerical documentation.
