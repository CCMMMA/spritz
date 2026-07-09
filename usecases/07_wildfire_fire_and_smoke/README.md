# Use case 07 — Coupled wildfire fire and smoke

## Narrative

This use case demonstrates the `fire+puff` sequence: SpritzFire first computes
fire evolution, then the standard Spritz dispersion workflow transports smoke
using the same scenario context. The separation makes one-way fire-to-smoke
coupling explicit and keeps fire spread, meteorology, emissions, and plume
products independently inspectable.

## Available setup scenarios

- [`demo/README.md`](demo/README.md) gives the guided coupled run and optional
  WRF, terrain, land-cover, and rendering preparation.
- [`pipeline/pipeline.sh`](pipeline/pipeline.sh) runs a scripts-only coupled
  workflow:

  ```bash
  bash usecases/07_wildfire_fire_and_smoke/pipeline/pipeline.sh
  ```

- [`workflow/usecase.wcl`](workflow/usecase.wcl) and
  [`workflow/README.md`](workflow/README.md) provide WCL integration.
- [`dagonstar/workflow.py`](dagonstar/workflow.py) is the Dagonstar task-graph
  sketch.

## Inputs and products

The bundled setup is synthetic. Real-area coupling should use aligned WRF,
DEM, and categorical land-cover inputs and validated time-dependent fire
emissions. Outputs include firefront, meteorological context, smoke
concentration, postprocessing, and visual diagnostics.

## Limitations

Coupled screening does not replace validated fire-emission inventories,
plume-injection physics, chemistry, data assimilation, or operational fire
forecasting. Review both fire and smoke assumptions independently.

## References

Scientific assumptions and peer-reviewed references are maintained in the
SpritzFire, particle-model, and numerical-model documentation.
