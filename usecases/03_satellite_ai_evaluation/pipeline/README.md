# Satellite AI Evaluation Pipeline

## Scientific Purpose

This pipeline produces a reproducible reference concentration field and publication-quality visual diagnostics for evaluation workflows. It replaces earlier scenario-specific mask generation with script-only Sprtz execution and renderable model artifacts.

This pipeline uses public command-line programs from `scripts/` for Sprtz model execution and avoids use-case-specific demonstration scripts. It is suitable for workflow engines because each scientific stage is an explicit process with concrete file inputs and outputs.

## Operational Contract

Run from the repository root, or from any other working directory:

```bash
bash usecases/03_satellite_ai_evaluation/pipeline/pipeline.sh
```

Products are written under `data/03_satellite_ai_evaluation/` by default. Set `SPRTZ_DATA_ROOT` to change the data root or `SPRTZ_OUTPUT_DIR` to choose the exact output directory. The script sets `MPLCONFIGDIR` and `XDG_CACHE_HOME` under the output directory by default for clean headless rendering.

## Parameters

- This pipeline has no use-case-specific environment overrides beyond `SPRTZ_DATA_ROOT`, `SPRTZ_OUTPUT_DIR`, `MPLCONFIGDIR`, and `XDG_CACHE_HOME`.

All parameters may be overridden as shell environment variables.

## Expected Products

- `model/meteo.nc`
- `model/concentration.nc`
- `model/post.json`
- `figures/reference_wind_map.png`
- `figures/reference_wind_profile.png`
- `figures/reference_wind_3d.png`

## Step-by-Step Method

### Step 1: Runtime environment diagnostic

Records optional runtime capabilities before model or rendering work begins.

```bash
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"
```

### Step 2: Reference Sprtz workflow execution

Runs the stable minimal Sprtz example through the public workflow wrapper to create a NetCDF concentration product for evaluation or visual QA.

```bash
python3 "${SCRIPTS_DIR}/sprtz.py" run "${REPO_ROOT}/examples/minimal.json" --output-dir "${OUT_DIR}/model" --interchange netcdf
```

### Step 3: 2-D reference wind rendering

Creates a 600 DPI map from the gridded meteorology product, which is the renderable NetCDF field produced by this reference workflow.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render.py" "${OUT_DIR}/model/meteo.nc" --variable wind_speed ...
```

### Step 4: Vertical reference wind profile rendering

Samples the reference wind field at the central local coordinate and produces a profile figure.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/profiler.py" "${OUT_DIR}/model/meteo.nc" --variable wind_speed ...
```

### Step 5: 3-D reference wind rendering

Creates a three-dimensional surface rendering from the gridded wind field.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render3d.py" "${OUT_DIR}/model/meteo.nc" --variable wind_speed ...
```

## Workflow-Engine Integration

Each step can be mapped to an independent workflow task. Configuration files, NetCDF products, JSON summaries, and PNG figures are declared artifacts that can be cached, inspected, and archived.

## Reproducibility Notes

- The default input is `examples/minimal.json`, which is deterministic.
- No hidden network access is performed.

## References

No external bibliographic references are required for this workflow description. Scientific and numerical assumptions are documented in the Sprtz numerical, particle, firefront, backward, and visualization documentation as applicable.
