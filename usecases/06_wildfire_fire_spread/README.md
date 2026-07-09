# Use case 06 — Wildfire fire spread

## Narrative

This use case demonstrates SpritzFire on a small synthetic domain. It produces
stochastic fire-arrival probability, mean arrival time, and perimeter products
while keeping serial execution available without optional MPI, GPU, SciPy,
pandas, or Numba dependencies.

## Available setup scenarios

- [`demo/README.md`](demo/README.md) explains the minimal fire-spread run,
  optional real-area WRF/terrain preparation, maps, and 3-D rendering.
- [`pipeline/pipeline.sh`](pipeline/pipeline.sh) runs the public `firefront`
  workflow and publication diagnostics:

  ```bash
  bash usecases/06_wildfire_fire_spread/pipeline/pipeline.sh
  ```

- [`workflow/usecase.wcl`](workflow/usecase.wcl) is the workflow-engine sketch
  described by [`workflow/README.md`](workflow/README.md).
- [`dagonstar/workflow.py`](dagonstar/workflow.py) is the Dagonstar-oriented
  setup.

## Inputs and products

The default configuration is synthetic and deterministic for a fixed seed.
Real-area studies should prepare aligned meteorology, DEM, and categorical land
cover. Products include `firefront.nc`, meteorological context, postprocessing,
arrival/probability fields, perimeter data, and publication figures.

## Limitations

The use case demonstrates clean-room stochastic spread behavior; it is not an
operational fire-behavior forecast. Fuel, suppression, spotting, terrain,
weather, and observation assumptions require validation for any real event.

## References

Scientific assumptions and peer-reviewed references are maintained in the
SpritzFire and numerical-model documentation.
