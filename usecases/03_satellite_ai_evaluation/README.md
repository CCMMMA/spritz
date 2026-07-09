# Use case 03 — Satellite and AI-supported evaluation

## Narrative

This use case evaluates modeled wildfire smoke against satellite-derived
evidence such as smoke masks, burned-area masks, or active-fire probability
grids. It normalizes model concentration, computes confusion-matrix skill
scores, and applies a deterministic lightweight logistic calibration. The
purpose is auditable model evaluation, not opaque replacement of atmospheric
physics by AI.

## Available setup scenarios

- [`demo/README.md`](demo/README.md) provides the guided evaluation workflow,
  including preparation of use-case 02 output and satellite evidence.
- [`pipeline/pipeline.sh`](pipeline/pipeline.sh) creates a reproducible
  scripts-only reference concentration field and publication diagnostics:

  ```bash
  bash usecases/03_satellite_ai_evaluation/pipeline/pipeline.sh
  ```

- [`workflow/usecase.wcl`](workflow/usecase.wcl) describes the demo steps for
  workflow-engine adaptation; see [`workflow/README.md`](workflow/README.md).
- [`dagonstar/workflow.py`](dagonstar/workflow.py) is a Dagonstar-oriented
  orchestration sketch.

## Inputs and products

Evaluation accepts model concentration plus a two-dimensional probability or
binary mask in the documented JSON, NPY, CSV, TXT, or numeric ASCII formats.
The demo writes an auditable metrics and calibration report. The batch pipeline
instead focuses on a stable reference NetCDF concentration product,
postprocessing summary, and 2-D/profile/3-D diagnostics.

Satellite acquisition, geolocation, cloud screening, temporal matching, and
uncertainty remain explicit upstream responsibilities. NetCDF time is read from
CF metadata and never inferred from filenames.

## Limitations

Skill scores depend strongly on alignment, thresholds, representativeness, and
satellite retrieval limitations. The bundled calibration is intentionally
simple and must not be interpreted as operational AI validation.

## References

Scientific assumptions and peer-reviewed references are maintained in the
model-evaluation and numerical documentation.
