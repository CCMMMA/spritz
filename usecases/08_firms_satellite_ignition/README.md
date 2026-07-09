# Use case 08 — FIRMS satellite ignition

## Narrative

This use case converts NASA FIRMS/VIIRS detections into candidate SpritzFire
ignition points. It keeps network access and credentials explicit, filters
detections through documented controls, and preserves a credential-free
offline surrogate for deterministic workflow testing.

## Available setup scenarios

- [`demo/README.md`](demo/README.md) documents live FIRMS acquisition,
  `FIRMS_MAP_KEY` handling, meteorology/terrain preparation, and fire products.
- [`pipeline/pipeline.sh`](pipeline/pipeline.sh) runs the offline
  FIRMS-compatible surrogate without credentials:

  ```bash
  bash usecases/08_firms_satellite_ignition/pipeline/pipeline.sh
  ```

- [`workflow/usecase.wcl`](workflow/usecase.wcl) and
  [`workflow/README.md`](workflow/README.md) provide workflow-engine setup.
- [`dagonstar/workflow.py`](dagonstar/workflow.py) is the Dagonstar-oriented
  integration sketch.

## Inputs and products

Live operation requires an externally supplied FIRMS key, detection date and
area, plus aligned meteorology and terrain for spread interpretation. Keys must
never be hard-coded or logged. Outputs include filtered ignition data,
firefront NetCDF, meteorological context, summaries, and visual diagnostics.

## Limitations

Satellite detections have timing, cloud, geolocation, confidence, and
completeness limitations. A detection is evidence, not proof of exact ignition
time or origin. Operational use requires corroboration and validated spread
inputs.

## References

Scientific assumptions and peer-reviewed references are maintained in the
SpritzFire and satellite-evaluation documentation.
