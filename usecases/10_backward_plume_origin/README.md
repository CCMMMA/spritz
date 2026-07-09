# Use case 10 — Backward plume-origin attribution

## Narrative

This use case estimates possible upwind source locations from odor, smoke, or
pollutant detections. It prepares meteorological evidence and computes a
backward source-likelihood product for screening and hypothesis generation.
The result is a likelihood surface, not a unique causal identification.

## Available setup scenarios

- [`demo/README.md`](demo/README.md) provides guided meteorology preparation,
  backward estimation, terrain context, visualization, and an HPC sketch.
- [`pipeline/pipeline.sh`](pipeline/pipeline.sh) runs the scripts-only Gaussian
  backward workflow:

  ```bash
  bash usecases/10_backward_plume_origin/pipeline/pipeline.sh
  ```

- [`workflow/usecase.wcl`](workflow/usecase.wcl) is documented in
  [`workflow/README.md`](workflow/README.md).
- [`dagonstar/workflow.py`](dagonstar/workflow.py) provides the Dagonstar
  orchestration sketch.

## Inputs and products

Inputs include one or more detections and meteorology consistent with their
times and locations. Real investigations should archive WRF forcing, derived
SpritzMet fields, DEM, land cover, observations, and uncertainty assumptions.
Outputs include meteorology, source-likelihood JSON or NetCDF sidecars, and
map/profile/3-D diagnostics.

## Limitations

Backward transport is sensitive to wind error, detection timing, missing
sources, chemistry, deposition, and model structure. Candidate locations must
be corroborated independently and must not be presented as proof of origin.

## References

Scientific assumptions and peer-reviewed references are maintained in the
backward-model and numerical documentation.
