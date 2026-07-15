# Use case 03 — Dispersion validation and satellite-supported evaluation

## Validation hierarchy

Formal validation is based on paired controlled-tracer concentrations, not on
downscaled satellite imagery. Use case 03 now separates three evidence levels:

1. deterministic analytical and numerical invariants maintained by the Sprtz
   test suite, including non-negativity, conservation, deterministic seeds, and
   limiting cases;
2. independent controlled-release observations scored at matching receptor and
   averaging times for both Gaussian and particle backends;
3. the Aversa satellite workflow as an incident consistency evaluation only.

The preferred first field benchmark is Prairie Grass for continuous near-ground
passive releases across stability classes. Copenhagen SF₆ is the preferred
elevated-source benchmark. ETEX and CAPTEX are reserved for future regional
domains. Third-party experimental measurements are not redistributed in this
clean-room repository; provide an independently obtained CSV using
[`controlled_tracer_observations.csv.sample`](controlled_tracer_observations.csv.sample).

Run the same observation file separately against each backend:

```bash
python usecases/03_satellite_ai_evaluation/demo/step_00_validate_controlled_tracer.py \
  --model data/controlled_tracer/gaussian.csv \
  --observations data/controlled_tracer/observations.csv \
  --experiment prairie-grass --backend gaussian --unit ug_m3 \
  --detection-limit 0.1 \
  --output data/output/satellite_ai_evaluation/validation/prairie_grass_gaussian.json

python usecases/03_satellite_ai_evaluation/demo/step_00_validate_controlled_tracer.py \
  --model data/controlled_tracer/particles.csv \
  --observations data/controlled_tracer/observations.csv \
  --experiment prairie-grass --backend particles --unit ug_m3 \
  --detection-limit 0.1 \
  --output data/output/satellite_ai_evaluation/validation/prairie_grass_particles.json
```

The scorer requires exact `receptor_id,time_s` pairing and reports fractional
bias, normalized mean-square error, FAC2, FAC5, correlation, RMSE, MAE, and
detection contingency counts. Model and observation concentrations must already
use the same species, averaging interval, and unit.

## Aversa incident narrative

The supplementary case evaluates Gaussian and particle dispersion for the 19 June 2024
Aversa construction-material-storage fire against a same-day Sentinel-5P
TROPOMI L2 tropospheric NO₂ column. UV Aerosol Index remains a secondary
smoke-footprint diagnostic. It includes WRF and satellite acquisition,
SpritzWRF/SpritzMet domain preparation, satellite alignment, plotting, metrics,
and deterministic lightweight logistic calibration.

## Available setup scenarios

- [`demo/README.md`](demo/README.md) provides the guided evaluation workflow,
  including data acquisition, domain preparation, both dispersion backends,
  satellite alignment, and the interpretation boundary imposed by the
  same-day overpass. It also includes a complete SLURM example for MPI
  meteorological downscaling, particle dispersion, and Gaussian dispersion.
- [`slurm/README.md`](slurm/README.md) documents the preferred staged,
  non-blocking SLURM submission workflow and its MPI stages.
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

The canonical network request uses the broader same-orbit bbox
`12.00 39.00 16.50 43.00` at `256×256`. A domain-only 32×32 Aerosol Index
request can return an all-masked GeoTIFF even when the HTTP request succeeds;
it is documented only as a negative diagnostic in `demo/README.md`. Do not use
an empty raster for alignment. `--allow-empty` is reserved for retaining its
request and response as negative provenance.

## Limitations

The verified Sentinel-5P orbit overlaps the modeled event. The primary workflow
vertically integrates multi-level Spritz NO₂ concentration, converts it to
mol m⁻², and aggregates it to native TROPOMI pixels. The Sentinel Hub GeoTIFF
does not carry the averaging kernel, Spritz treats NO₂ as a passive tracer, and
no background column is modeled, so raw-column results remain screening
diagnostics rather than regulatory validation. Aerosol Index is used only for
secondary plume-footprint comparison.

## References

Chang, J. C., & Hanna, S. R. (2004). Air quality model performance evaluation.
*Meteorology and Atmospheric Physics, 87*, 167–196.

Van Dop, H., et al. (1998). ETEX: A European tracer experiment; observations,
dispersion modelling and emergency response. *Atmospheric Environment, 32*,
4089–4094.

Hanna, S. R., Chang, J. C., & Strimaitis, D. G. (1993). Hazardous gas model
evaluation with field observations. *Atmospheric Environment Part A, 27*,
2265–2285.
