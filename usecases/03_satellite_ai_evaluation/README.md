# Use case 03 — Satellite and AI-supported model evaluation

Goal: evaluate a Spritz wildfire/arson simulation against satellite-derived evidence such as smoke masks, burned-area masks, or active-fire probability grids.

The workflow is didactic and auditable:

1. **Run use case 02.** Produce a Spritz concentration file.
2. **Prepare satellite evidence.** Provide a 2-D probability or binary mask in JSON, NPY, CSV, TXT, or ASCII numeric format.
3. **Map model output to probabilities.** The script converts model concentrations to a normalized probability field.
4. **Compare model and observation.** It computes a confusion matrix and skill scores.
5. **Apply lightweight AI calibration.** A deterministic logistic calibration reports how much a simple learned transform improves alignment.
6. **Write a report.** The output JSON records inputs, thresholds, metrics, and calibration parameters.

NetCDF/time convention: any evaluated NetCDF input is expected to follow strict
CF metadata. The evaluator reads model times from CF `time`/`time_datetime`
metadata when present and does not infer datetimes from filenames.

## Data preparation

This use case evaluates outputs produced by use case 02. Prepare that upstream
run with the WRF and COP30 helper scripts:

```bash
tools/meteouniparthenope-wrf-download.py 20260527Z0000 --hours 1 --domain d03 --data-root data
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_naples.tif
python3 tools/copernicus-lc100-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/landcover/lc100_naples.tif
```

The WRF file supports SpritzWRF/SpritzMet forcing. When preparing high-resolution
meteorology, pass the DEM as `--dem` and LC100 as `--land-cover` so SpritzMet
uses both terrain and land cover for wind and precipitation downscaling. The
same rasters can also feed `sprtz-terrain fetch` when the evaluated scenario
includes standalone terrain/GEO products.

Use case 02 writes `CALMET.DAT` next to the WRF-derived SpritzMet forcing by
default. Keep that binary artifact with the evaluated concentration output when
comparing Spritz results against external model-evaluation tools.

## Create a tiny demo mask

```bash
python usecases/03_satellite_ai_evaluation/step_01_make_demo_mask.py output/demo_mask.json
```

## Run evaluation

```bash
python usecases/03_satellite_ai_evaluation/step_02_evaluate.py \
  --concentration output/wildfire_case/model/concentration.nc \
  --satellite-mask output/demo_mask.json \
  --output output/wildfire_case/evaluation.json \
  --threshold 0.5
```

## Plot the evaluated NetCDF map

The evaluation step calls `tools/plotter.py` for NetCDF concentration inputs.
To regenerate the evaluated concentration map explicitly, run:

```bash
python tools/plotter.py output/wildfire_case/model/concentration.nc \
  --variable concentration \
  --output output/wildfire_case/model/concentration_map.png
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
