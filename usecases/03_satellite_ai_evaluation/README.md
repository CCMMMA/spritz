# Use case 03 - Model evaluation with satellite images and artificial intelligence

## Purpose

Evaluate a PyPuff wildfire/arson simulation against a satellite-derived smoke, fire, hot-spot, or burned-area mask.  The use case supports transparent verification metrics and a deterministic AI-style calibration layer that can be replaced by a more advanced ML model in operational deployments.

## Workflow

```text
PyPuff concentration/deposition product + satellite mask -> thresholding -> confusion matrix -> skill metrics -> AI calibration report
```

## Inputs

1. Concentration file from use case 02 or any PyPuff run.  Supported formats include JSON/CSV/TXT/NetCDF-CF-compatible fallback products.
2. Satellite-derived mask.  Supported formats:
   - JSON with a `mask` array
   - `.npy`
   - CSV, TXT, or numeric ASCII grids
3. Optional threshold used to convert concentration into modeled affected/not-affected pixels.

The satellite mask should be georeferenced and resampled consistently with the PyPuff receptor or grid product before formal evaluation.  This example focuses on the verification logic, not satellite retrieval physics.

## Demo mask

Create a deterministic demonstration mask:

```bash
python make_demo_mask.py --output output/satellite_mask.json --nx 20 --ny 20
```

## Run evaluation

```bash
pypuff-usecase-evaluate \
  --concentration output/wildfire_case/model/concentration.nc \
  --satellite-mask output/satellite_mask.json \
  --output output/evaluation.json \
  --threshold 0.1
```

## Metrics

The report includes:

- confusion matrix: true positives, false positives, false negatives, true negatives
- accuracy
- precision
- recall / probability of detection
- F1 score
- CSI / threat score
- false-alarm ratio
- deterministic AI calibration parameters and calibrated scores

## AI layer

The included AI layer is intentionally lightweight and deterministic.  It behaves like a reproducible logistic calibration model over concentration-derived features.  In production, replace it with a trained model that documents:

- satellite sensor and product version
- cloud/smoke/burned-area uncertainty
- training/validation split
- calibration period
- spatial resolution and reprojection method
- false-alarm handling

## Operational caveats

Satellite images do not observe ground-level concentration directly.  They may detect thermal anomalies, smoke optical depth, burned area, or qualitative plume presence.  Use the metrics as evidence for model evaluation, not as a standalone regulatory validation.
