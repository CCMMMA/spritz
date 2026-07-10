# Production Incidents Pipeline

## Scientific Purpose

This pipeline implements Industrial point-source release near a production area. It synthesizes a public Sprtz configuration, runs the model through command-line wrappers, and renders publication-ready figures.

This pipeline uses public command-line programs from `scripts/` for Sprtz model execution and avoids use-case-specific demonstration scripts. It is suitable for workflow engines because each scientific stage is an explicit process with concrete file inputs and outputs.

## Operational Contract

Run from the repository root, or from any other working directory:

```bash
bash usecases/04_production_incidents/pipeline/pipeline.sh
```

Products are written under `data/04_production_incidents/` by default. Set `SPRTZ_DATA_ROOT` to change the data root or `SPRTZ_OUTPUT_DIR` to choose the exact output directory. The script sets `MPLCONFIGDIR` and `XDG_CACHE_HOME` under the output directory by default for clean headless rendering.

## Parameters

- `NX` defaults to `25`.
- `NY` defaults to `25`.
- `DX` defaults to `100`.
- `DY` defaults to `100`.
- `EMISSION_RATE_G_S` defaults to `20.0`.
- `WIND_SPEED_M_S` defaults to `3.0`.
- `SOURCE_X_M` defaults to `1000.0`.
- `SOURCE_Y_M` defaults to `1000.0`.

All parameters may be overridden as shell environment variables.

## Expected Products

- `production_incident_config.json`
- `model/meteo.nc`
- `model/concentration.nc`
- `model/post.json`
- `figures/concentration_map.png`
- `figures/concentration_profile.png`
- `figures/concentration_3d.png`

## Step-by-Step Method

### Step 1: Runtime environment diagnostic

Records runtime and optional dependency availability.

```bash
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"
```

### Step 2: Scenario configuration synthesis

Writes a normal Sprtz JSON scenario in the output directory.

```bash
cat > "${CONFIG_PATH}" <<JSON
```

### Step 3: Configuration validation

Validates the generated configuration through the public CLI.

```bash
python3 "${SCRIPTS_DIR}/sprtz.py" validate "${CONFIG_PATH}"
```

### Step 4: Integrated workflow execution

Runs SpritzMet, dispersion, and SpritzPost through `scripts/sprtz.py`.

```bash
python3 "${SCRIPTS_DIR}/sprtz.py" run "${CONFIG_PATH}" ...
```

### Step 5: 2-D map rendering

Renders a 600 DPI concentration map.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" ...
```

### Step 6: Vertical profile rendering

Renders a source-column vertical profile.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" profile ...
```

### Step 7: 3-D surface rendering

Renders a three-dimensional concentration surface.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" render3d ...
```

## Workflow-Engine Integration

Each step can be mapped to an independent workflow task. Configuration files, NetCDF products, JSON summaries, and PNG figures are declared artifacts that can be cached, inspected, and archived.

## Reproducibility Notes

- Default scenario parameters are deterministic.
- No hidden network access is performed.

## References

No external bibliographic references are required for this workflow description. Scientific and numerical assumptions are documented in the Sprtz numerical, particle, firefront, backward, and visualization documentation as applicable.
