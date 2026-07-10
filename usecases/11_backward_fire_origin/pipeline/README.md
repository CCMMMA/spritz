# Backward Fire Origin Pipeline

## Scientific Purpose

This pipeline runs firefront backward ignition attribution and a companion firefront context simulation used for publication-ready visual diagnostics.

This pipeline uses public command-line programs from `scripts/` for Sprtz model execution and avoids use-case-specific demonstration scripts. It is suitable for workflow engines because each scientific stage is an explicit process with concrete file inputs and outputs.

## Operational Contract

Run from the repository root, or from any other working directory:

```bash
bash usecases/11_backward_fire_origin/pipeline/pipeline.sh
```

Products are written under `data/11_backward_fire_origin/` by default. Set `SPRTZ_DATA_ROOT` to change the data root or `SPRTZ_OUTPUT_DIR` to choose the exact output directory. The script sets `MPLCONFIGDIR` and `XDG_CACHE_HOME` under the output directory by default for clean headless rendering.

## Parameters

- This pipeline has no use-case-specific environment overrides beyond `SPRTZ_DATA_ROOT`, `SPRTZ_OUTPUT_DIR`, `MPLCONFIGDIR`, and `XDG_CACHE_HOME`.

All parameters may be overridden as shell environment variables.

## Expected Products

- `ignition_likelihood.json`
- `meteo_context.nc`
- `fire_context/firefront.nc`
- `figures/fire_context_map.png`
- `figures/fire_context_profile.png`
- `figures/fire_context_3d.png`

## Step-by-Step Method

### Step 1: Runtime environment diagnostic

Records runtime capability.

```bash
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"
```

### Step 2: Configuration validation

Validates the backward firefront config.

```bash
python3 "${SCRIPTS_DIR}/sprtz.py" validate ...
```

### Step 3: Backward attribution

Runs firefront ignition likelihood.

```bash
python3 "${SCRIPTS_DIR}/sprtz_backward.py" ...
```

### Step 4: Meteorological Context Generation

Creates a companion SpritzMet NetCDF file from the wildfire configuration. The context file is used for publication-ready rendering because it has regular gridded meteorological variables with stable coordinates.

```bash
python3 "${SCRIPTS_DIR}/spritzmet.py" --config "${REPO_ROOT}/examples/wildfire_minimal.json" --output "${CONC_PATH}" --format netcdf
```

### Step 5: Firefront context simulation

Creates a NetCDF fire context product for rendering.

```bash
python3 "${SCRIPTS_DIR}/sprtzfire.py" ...
```

### Step 6: 2-D meteorological context rendering

Renders a wind-speed context map.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" ...
```

### Step 7: Meteorological context profile rendering

Renders a wind-speed context profile.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" profile ...
```

### Step 8: 3-D meteorological context rendering

Renders a three-dimensional wind-speed context surface.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" render3d ...
```

## Workflow-Engine Integration

Each step can be mapped to an independent workflow task. Configuration files, NetCDF products, JSON summaries, and PNG figures are declared artifacts that can be cached, inspected, and archived.

## Reproducibility Notes

- The primary attribution product remains `ignition_likelihood.json`.
- The context simulation is deterministic and intended for visualization.

## References

No external bibliographic references are required for this workflow description. Scientific and numerical assumptions are documented in the Sprtz numerical, particle, firefront, backward, and visualization documentation as applicable.
