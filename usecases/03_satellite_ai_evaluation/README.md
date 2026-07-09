# Use case 03 — Satellite and AI-supported evaluation

## Narrative

This use case evaluates Gaussian and particle dispersion for the 19 June 2024
Aversa construction-material-storage fire against a same-day Sentinel-5P
TROPOMI L2 UV Aerosol Index smoke-plume pattern. It includes WRF and satellite acquisition,
SpritzWRF/SpritzMet domain preparation, satellite alignment, plotting, metrics,
and deterministic lightweight logistic calibration.

## Available setup scenarios

- [`demo/README.md`](demo/README.md) provides the guided evaluation workflow,
  including data acquisition, domain preparation, both dispersion backends,
  satellite alignment, and the interpretation boundary imposed by the
  same-day overpass.
- [`pipeline/pipeline.sh`](pipeline/pipeline.sh) creates a reproducible
  scripts-only concentration field, satellite mask, evaluation report, and
  diagnostic figure:

  ```bash
  bash usecases/03_satellite_ai_evaluation/pipeline/pipeline.sh
  ```

- [`workflow/workflow.cwl`](workflow/workflow.cwl) wraps the same canonical
  pipeline for a CWL v1.2 runner; see [`workflow/README.md`](workflow/README.md).
- [`dagonstar/workflow.py`](dagonstar/workflow.py) is a Dagonstar-oriented
  orchestration sketch.

## Inputs and products

The workflow is self-contained and does not invoke or read another use case.
Its offline mode generates a demonstration mask; network mode downloads WRF
and Sentinel-5P data. Evaluation also accepts model
concentration plus a two-dimensional probability or binary mask in the
documented JSON, NPY, CSV, TXT, or numeric ASCII formats.
Both the demo and batch pipeline write an auditable metrics and calibration
report. The batch pipeline additionally creates a stable reference NetCDF
concentration product, pixelwise difference and ratio products, a statistics
CSV, and a rendered concentration diagnostic.

Satellite acquisition, geolocation, cloud screening, temporal matching, and
uncertainty remain explicit upstream responsibilities. NetCDF time is read from
CF metadata and never inferred from filenames.

## Limitations

The verified Sentinel-5P orbit overlaps the modeled event. Aerosol Index is
more directly responsive to absorbing smoke than NO₂, but it is still a
column-sensitive optical index rather than near-surface mass concentration.
Results therefore compare normalized spatial patterns and do not by themselves
establish event attribution or operational validation.

## References

Scientific assumptions and peer-reviewed references are maintained in the
model-evaluation and numerical documentation.
