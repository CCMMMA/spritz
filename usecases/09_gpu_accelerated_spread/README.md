# Use case 09 — GPU-accelerated fire spread

## Narrative

This use case demonstrates optional acceleration of SpritzFire workloads.
Acceleration changes execution strategy, not scientific inputs, configuration,
CF metadata, or expected results. GPU detection remains lazy and any backend
failure falls back safely to NumPy/CPU execution.

## Available setup scenarios

- [`demo/README.md`](demo/README.md) documents GPU selection, CPU fallback,
  optional WRF/terrain preparation, and fire visualization.
- [`pipeline/pipeline.sh`](pipeline/pipeline.sh) runs the public firefront
  workflow and diagnostics:

  ```bash
  bash usecases/09_gpu_accelerated_spread/pipeline/pipeline.sh
  ```

- [`workflow/usecase.wcl`](workflow/usecase.wcl) and
  [`workflow/README.md`](workflow/README.md) provide WCL adaptation.
- [`dagonstar/workflow.py`](dagonstar/workflow.py) provides a scheduler-facing
  task sketch.

## Inputs and products

The default scenario is suitable for portability and fallback checks. Larger
real-area runs require the same validated meteorology, DEM, land cover, fuel,
and provenance as CPU runs. Outputs include firefront NetCDF, context,
postprocessing, and 2-D/profile/3-D diagnostics.

## Limitations

GPU availability does not establish numerical equivalence or speedup.
Production use must compare accelerated and NumPy outputs, record backend and
hardware provenance, and verify performance with representative workloads.

## References

Scientific assumptions and peer-reviewed references are maintained in the
SpritzFire, parallelization, and numerical-model documentation.
