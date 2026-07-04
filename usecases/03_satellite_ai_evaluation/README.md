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
tools/meteouniparthenope-wrf-download.py 20260527Z0000 --hours 1 --domain d03 --data-root data/wrf/d03
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

If the upstream use case 02 output is under `output/wildfire_case`, create the
matching GEO product before 3-D plume rendering:

```bash
sprtz-terrain fetch \
  --center-lat 40.827 \
  --center-lon 14.518 \
  --nx 201 \
  --ny 201 \
  --dx 100 \
  --dy 100 \
  --dem data/dem/cop30_naples.tif \
  --landuse data/landcover/lc100_naples.tif \
  --landuse-mapping copernicus-lc100 \
  --cache-dir output/terrain-cache \
  --output output/wildfire_case/geo.nc
```

Use case 02 can write particle and Gaussian outputs under `model_compare/`.
Choose the backend concentration file that matches the satellite product being
evaluated. When `--calpuff-binary` is used upstream, keep the
`concentration_calpuff.dat` sidecar with the NetCDF-CF concentration output for
external binary-comparison workflows.

## Create a tiny demo mask

```bash
python usecases/03_satellite_ai_evaluation/step_01_make_demo_mask.py output/demo_mask.json
```

## Run evaluation

```bash
python usecases/03_satellite_ai_evaluation/step_02_evaluate.py \
  --concentration output/wildfire_case/model_compare/particles/concentration.nc \
  --satellite-mask output/demo_mask.json \
  --output output/wildfire_case/evaluation.json \
  --threshold 0.5
```

## Plot the evaluated NetCDF map

The evaluation step calls `tools/plotter.py` for NetCDF concentration inputs.
To regenerate the evaluated concentration map explicitly, run:

```bash
python tools/plotter.py output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --time-index 1 \
  --output output/wildfire_case/model_compare/particles/concentration_map.png
```

For three-dimensional inspection of the evaluated plume, render the same
NetCDF with the terrain/GEO product used by the upstream wildfire case:

```bash
python tools/render3d.py output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --time-index 1 \
  --terrain output/wildfire_case/geo.nc \
  --mode surface \
  --ground-color terrain \
  --output output/wildfire_case/model_compare/particles/concentration_3d.png
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
