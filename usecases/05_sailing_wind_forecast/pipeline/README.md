# Sailing Wind Forecast Pipeline

## Scientific Purpose

This pipeline creates a deterministic high-resolution local wind product for sailing forecast demonstrations and renders publication-ready wind figures.

This pipeline uses the use case's documented forecast builder and public Sprtz
validation/visualization programs. It is suitable for workflow engines because
each scientific stage has concrete file inputs and outputs.

## Operational Contract

Run from the repository root, or from any other working directory:

```bash
bash usecases/05_sailing_wind_forecast/pipeline/pipeline.sh
```

Products are written under `data/05_sailing_wind_forecast/` by default. Set `SPRTZ_DATA_ROOT` to change the data root or `SPRTZ_OUTPUT_DIR` to choose the exact output directory. The script sets `MPLCONFIGDIR` and `XDG_CACHE_HOME` under the output directory by default for clean headless rendering.

## Parameters

- `NX` defaults to `25`.
- `NY` defaults to `25`.
- `DX` defaults to `100`.
- `DY` defaults to `100`.
- `WIND_SPEED_M_S` defaults to `6.0`.
- `WIND_FROM_DIRECTION_DEG` defaults to `245.0`.
- `INITIALIZATION_TIME` defaults to `20260601Z0000`.
- Forecast output cadence is fixed at 600 seconds (10 minutes).

All parameters may be overridden as shell environment variables.

## Expected Products

- `sailing_wind_config.json`
- `sailing_wind.json`
- `sailing_wind.nc`
- `figures/sailing_wind_map.png`
- `figures/sailing_wind_profile.png`
- `figures/sailing_wind_3d.png`

## Step-by-Step Method

### Step 1: Runtime environment diagnostic

Records runtime capability.

```bash
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"
```

### Step 2: Configuration synthesis

Writes a deterministic local-grid sailing wind config.

```bash
cat > "${CONFIG_PATH}" <<JSON
```

### Step 3: Configuration validation

Validates the config via public CLI.

```bash
python3 "${SCRIPTS_DIR}/sprtz.py" validate "${CONFIG_PATH}"
```

### Step 4: Ten-minute forecast generation

Creates JSON and NetCDF-CF forecast products with one high-resolution frame
every 10 minutes.

```bash
python3 usecases/05_sailing_wind_forecast/demo/step_01_build_forecast.py \
  --initialization-time 20260601Z0000 --time-resolution-s 600 \
  --output data/05_sailing_wind_forecast/sailing_wind.json
```

### Step 5: 2-D wind rendering

Creates a 600 DPI wind map.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" ...
```

### Step 6: Profile rendering

Creates a vertical wind profile.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" profile ...
```

### Step 7: 3-D rendering

Creates a three-dimensional wind surface.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" render3d ...
```

## Workflow-Engine Integration

Each step can be mapped to an independent workflow task. Configuration files, NetCDF products, JSON summaries, and PNG figures are declared artifacts that can be cached, inspected, and archived.

## Reproducibility Notes

- Defaults are deterministic and offline.

## References

No external bibliographic references are required for this workflow description. Scientific and numerical assumptions are documented in the Sprtz numerical, particle, firefront, backward, and visualization documentation as applicable.
