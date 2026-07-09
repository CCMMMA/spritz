# Use case 06 — Acerra waste-to-energy screening

## Narrative

This use case models a didactic 12-hour point-source release from the Acerra
waste-to-energy plant. It demonstrates chimney configuration, a release height
above local ground, deterministic meteorology, Gaussian dispersion,
postprocessing, and visual reporting without claiming facility-specific
regulatory equivalence.

## Available setup scenarios

- [`demo/README.md`](demo/README.md) documents the geographic source,
  configuration builder, optional WRF/terrain preparation, and model run.
- [`pipeline/pipeline.sh`](pipeline/pipeline.sh) provides a self-contained
  scripts-only screening scenario:

  ```bash
  bash usecases/06_acerra_waste_to_energy/pipeline/pipeline.sh
  ```

- [`workflow/usecase.wcl`](workflow/usecase.wcl) and
  [`workflow/README.md`](workflow/README.md) provide the WCL setup.
- [`dagonstar/workflow.py`](dagonstar/workflow.py) provides an external
  Dagonstar orchestration sketch.

## Inputs and products

The default setup uses placeholder deterministic meteorology. A
production-style rerun should use archived WRF forcing, COP30 terrain, LC100
land cover, and validated stack and emissions data. Outputs include
configuration, meteorology, concentration, postprocessing summaries, and
publication figures under `data/06_acerra_waste_to_energy/` by default.

## Limitations

The bundled source and meteorological values are didactic. Regulatory or health
assessment requires authoritative emissions, stack operation, chemistry,
building effects, observations, and independently validated methods.

## References

Scientific assumptions and peer-reviewed references are maintained in the
dispersion and numerical-model documentation.
