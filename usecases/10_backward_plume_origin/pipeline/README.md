# Backward Plume Origin Pipeline

## Scientific Purpose

This pipeline prepares meteorology, runs Gaussian backward source attribution, and renders wind-field diagnostics for the meteorological evidence used by the attribution stage.

This pipeline uses public command-line programs from `scripts/` for Sprtz model execution and avoids use-case-specific demonstration scripts. It is suitable for workflow engines because each scientific stage is an explicit process with concrete file inputs and outputs.

## Operational Contract

Run from the repository root, or from any other working directory:

```bash
bash usecases/10_backward_plume_origin/pipeline/pipeline.sh
```

Products are written under `data/10_backward_plume_origin/` by default. Set `SPRTZ_DATA_ROOT` to change the data root or `SPRTZ_OUTPUT_DIR` to choose the exact output directory. The script sets `MPLCONFIGDIR` and `XDG_CACHE_HOME` under the output directory by default for clean headless rendering.

## Parameters

- This pipeline has no use-case-specific environment overrides beyond `SPRTZ_DATA_ROOT`, `SPRTZ_OUTPUT_DIR`, `MPLCONFIGDIR`, and `XDG_CACHE_HOME`.

All parameters may be overridden as shell environment variables.

## Expected Products

- `meteo.nc`
- `source_likelihood.json`
- `figures/backward_meteo_map.png`
- `figures/backward_meteo_profile.png`
- `figures/backward_meteo_3d.png`

## Step-by-Step Method

### Step 1: Runtime environment diagnostic

Records runtime capability.

```bash
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"
```

### Step 2: Configuration validation

Validates the backward plume example.

```bash
python3 "${SCRIPTS_DIR}/sprtz.py" validate ...
```

### Step 3: Meteorology generation

Creates explicit meteorology.

```bash
python3 "${SCRIPTS_DIR}/spritzmet.py" ...
```

### Step 4: Backward attribution

Runs backward plume source likelihood.

```bash
python3 "${SCRIPTS_DIR}/sprtz_backward.py" ...
```

### Step 5: 2-D wind rendering

Renders wind map.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" ...
```

### Step 6: Profile rendering

Renders wind profile.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" profile ...
```

### Step 7: 3-D rendering

Renders wind surface.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" render3d ...
```

## Workflow-Engine Integration

Each step can be mapped to an independent workflow task. Configuration files, NetCDF products, JSON summaries, and PNG figures are declared artifacts that can be cached, inspected, and archived.

## Reproducibility Notes

- The meteorology and attribution products are deterministic.
- The backward likelihood JSON is preserved as the primary attribution artifact.

## References

No external bibliographic references are required for this workflow description. Scientific and numerical assumptions are documented in the Sprtz numerical, particle, firefront, backward, and visualization documentation as applicable.
