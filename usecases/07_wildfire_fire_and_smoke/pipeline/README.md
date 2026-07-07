# Wildfire Fire And Smoke Pipeline

## Scientific Purpose

This pipeline runs the `fire+puff` wildfire workflow through public Sprtz wrappers and renders publication-ready diagnostics from the NetCDF product.

This pipeline uses public command-line programs from `scripts/` for Sprtz model execution and avoids use-case-specific demonstration scripts. It is suitable for workflow engines because each scientific stage is an explicit process with concrete file inputs and outputs.

## Operational Contract

Run from the repository root, or from any other working directory:

```bash
bash usecases/07_wildfire_fire_and_smoke/pipeline/pipeline.sh
```

Products are written under `data/07_wildfire_fire_and_smoke/` by default. Set `SPRTZ_DATA_ROOT` to change the data root or `SPRTZ_OUTPUT_DIR` to choose the exact output directory. The script sets `MPLCONFIGDIR` and `XDG_CACHE_HOME` under the output directory by default for clean headless rendering.

## Parameters

- This pipeline has no use-case-specific environment overrides beyond `SPRTZ_DATA_ROOT`, `SPRTZ_OUTPUT_DIR`, `MPLCONFIGDIR`, and `XDG_CACHE_HOME`.

All parameters may be overridden as shell environment variables.

## Expected Products

- `model/meteo.nc`
- `model/concentration.nc` and `meteo_context.nc`
- `model/post.json`
- `figures/meteo_context_map.png`
- `figures/meteo_context_profile.png`
- `figures/meteo_context_3d.png`

## Step-by-Step Method

### Step 1: Runtime environment diagnostic

Records runtime capability.

```bash
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"
```

### Step 2: Configuration validation

Validates the wildfire example config.

```bash
python3 "${SCRIPTS_DIR}/sprtz.py" validate ...
```

### Step 3: Meteorological Context Generation

Creates a companion SpritzMet NetCDF file from the wildfire configuration. The context file is used for publication-ready rendering because it has regular gridded meteorological variables with stable coordinates.

```bash
python3 "${SCRIPTS_DIR}/spritzmet.py" --config "${REPO_ROOT}/examples/wildfire_minimal.json" --output "${CONC_PATH}" --format netcdf
```

### Step 4: Model execution

Runs the selected fire workflow through the public wrapper.

```bash
script command in pipeline.sh
```

### Step 5: 2-D meteorological context rendering

Renders a publication map from `wind_speed` in the companion meteorological context file.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render.py" ...
```

### Step 6: Meteorological context profile rendering

Renders a `wind_speed` profile figure from the companion meteorological context file.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/profiler.py" ...
```

### Step 7: 3-D meteorological context rendering

Renders a three-dimensional `wind_speed` figure from the companion meteorological context file.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render3d.py" ...
```

## Workflow-Engine Integration

Each step can be mapped to an independent workflow task. Configuration files, NetCDF products, JSON summaries, and PNG figures are declared artifacts that can be cached, inspected, and archived.

## Reproducibility Notes

- Defaults are deterministic except where optional acceleration changes performance only.
- FIRMS credentials are not embedded or logged.

## References

No external bibliographic references are required for this workflow description. Scientific and numerical assumptions are documented in the Sprtz numerical, particle, firefront, backward, and visualization documentation as applicable.
