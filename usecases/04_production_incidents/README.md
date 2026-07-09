# Use case 04 — Production incident catalog

## Narrative

This use case turns an auditable incident catalog into repeatable
production-style atmospheric screening cases. The bundled examples include
events at Acerra and San Marcellino and preserve incident location, start time,
duration, configuration, meteorological context, and model outputs as a
reviewable dossier.

## Available setup scenarios

- [`demo/README.md`](demo/README.md) explains catalog-driven configuration,
  archived WRF/terrain preparation, model execution, and interpretation.
- [`pipeline/pipeline.sh`](pipeline/pipeline.sh) provides a deterministic
  scripts-only industrial-release scenario with configurable grid, source, and
  wind:

  ```bash
  bash usecases/04_production_incidents/pipeline/pipeline.sh
  ```

- [`workflow/usecase.wcl`](workflow/usecase.wcl) is the engine-neutral WCL
  sketch documented in [`workflow/README.md`](workflow/README.md).
- [`dagonstar/workflow.py`](dagonstar/workflow.py) provides a
  Dagonstar-oriented task graph.

## Inputs and products

Real incident dossiers should archive the exact WRF cycle, DEM, land cover,
incident record, source assumptions, configuration, checksums, and software
version. The pipeline writes configuration JSON, NetCDF-CF meteorology and
concentration, postprocessing results, and publication diagnostics under
`data/04_production_incidents/` by default.

Date-time arguments use `YYYYMMDDZhhmm`; physical NetCDF time comes from
configuration and CF/WRF metadata rather than filenames.

## Limitations

Catalog entries alone do not define validated emissions. Operational analysis
requires source characterization, meteorological and terrain validation,
observations, uncertainty analysis, and independent review.

## References

Scientific assumptions and peer-reviewed references are maintained in the
dispersion and production-readiness documentation.
