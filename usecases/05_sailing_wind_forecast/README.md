# Use case 05 — High-resolution sailing wind forecast

## Narrative

This use case creates a forecast-ready local wind product for precision
sailing applications. It represents initialization time, outlook, geographic
domain, horizontal and vertical spacing, and forecast time resolution
explicitly. The bundled Bay of Naples setup demonstrates deterministic
high-resolution wind generation at a fixed 10-minute (600-second) output
cadence and visualization while preserving strict
NetCDF-CF coordinates and absolute UTC time.

## Available setup scenarios

- [`demo/README.md`](demo/README.md) provides the configurable forecast
  builder, domain conventions, products, and real-data preparation guidance.
- [`pipeline/pipeline.sh`](pipeline/pipeline.sh) runs a compact deterministic
  scripts-only sailing forecast:

  ```bash
  bash usecases/05_sailing_wind_forecast/pipeline/pipeline.sh
  ```

- [`workflow/usecase.wcl`](workflow/usecase.wcl) describes the demo command for
  workflow engines; see [`workflow/README.md`](workflow/README.md).
- [`dagonstar/workflow.py`](dagonstar/workflow.py) is the Dagonstar integration
  sketch.

## Inputs and products

The didactic setup can generate synthetic winds; production-oriented studies
should prepare WRF forcing plus aligned DEM and land cover through the shared
SpritzWRF → SpritzMet path. Outputs include forecast JSON or NetCDF-CF wind
fields and 2-D, vertical-profile, and 3-D visualizations. Data remains under
the repository-level `data/` tree unless overridden.

## Limitations

The synthetic setup demonstrates interfaces and resolution contracts; it is
not a marine forecast. Operational sailing support requires observations,
validated forcing, coastal-flow evaluation, uncertainty characterization, and
timely forecast verification.

## References

Scientific assumptions and peer-reviewed references are maintained in the
SpritzWRF/SpritzMet and numerical-model documentation.
