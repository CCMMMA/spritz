# Use case 03 — Satellite and AI-supported model evaluation

Goal: evaluate a Spritz wildfire/arson simulation against satellite-derived evidence such as smoke masks, burned-area masks, or active-fire probability grids.

The workflow is didactic and auditable:

1. **Run use case 02.** Produce a Spritz concentration file.
2. **Prepare satellite evidence.** Provide a 2-D probability or binary mask in JSON, NPY, CSV, TXT, or ASCII numeric format.
3. **Map model output to probabilities.** The script converts model concentrations to a normalized probability field.
4. **Compare model and observation.** It computes a confusion matrix and skill scores.
5. **Apply lightweight AI calibration.** A deterministic logistic calibration reports how much a simple learned transform improves alignment.
6. **Write a report.** The output JSON records inputs, thresholds, metrics, and calibration parameters.

## Create a tiny demo mask

```bash
python usecases/03_satellite_ai_evaluation/make_demo_mask.py output/demo_mask.json
```

## Run evaluation

```bash
python usecases/03_satellite_ai_evaluation/run.py \
  --concentration output/wildfire_case/model/concentration.nc \
  --satellite-mask output/demo_mask.json \
  --output output/wildfire_case/evaluation.json \
  --threshold 0.5
```

## Metrics reported

- confusion matrix: true positive, false positive, true negative, false negative;
- accuracy;
- precision;
- recall / probability of detection;
- F1 score;
- critical success index;
- false-alarm ratio;
- deterministic logistic calibration weight, bias, and RMSE.

## AI boundary

The included AI layer is intentionally lightweight and dependency-free. Production satellite evaluation can replace it with a richer classifier or segmentation model, but should keep the same audit trail: input source, preprocessing, threshold, validation split, and calibration metrics.
