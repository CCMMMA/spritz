# Wildfire Arson Effects Pipeline

## Scientific Purpose

This pipeline implements a deterministic wildfire/arson smoke-dispersion scenario using only externally invocable Sprtz wrappers from the repository-level `scripts/` directory plus publication rendering tools from `tools/`. The workflow synthesizes a normal Sprtz JSON configuration, validates it, generates meteorology, runs Gaussian and particle dispersion backends, postprocesses both concentration products, and renders publication-ready figures from the Gaussian concentration field.

The use case is intentionally clean-room and didactic. It demonstrates how a workflow engine can decompose a scenario into explicit command-line tasks without importing package internals.

## Operational Contract

Run from the repository root, or from any other working directory:

```bash
bash usecases/02_wildfire_arson_effects/pipeline/pipeline.sh
```

The script resolves the repository root from its own location. Products are written under `data/02_wildfire_arson_effects/` by default. Set `SPRTZ_DATA_ROOT` to change the data root, or set `SPRTZ_OUTPUT_DIR` to choose the exact output directory.

The script sets `MPLCONFIGDIR` to `${SPRTZ_OUTPUT_DIR}/.matplotlib` and `XDG_CACHE_HOME` to `${SPRTZ_OUTPUT_DIR}/.cache` by default so rendering tasks can build font and style caches in workflow-writable locations. Override these variables when the workflow engine provides shared rendering caches.

## Parameters

- `NX` defaults to `31`, the number of local-grid cells in the x direction.
- `NY` defaults to `31`, the number of local-grid cells in the y direction.
- `DX` defaults to `100`, the grid spacing in metres in the x direction.
- `DY` defaults to `100`, the grid spacing in metres in the y direction.
- `WIND_SPEED_M_S` defaults to `4.0`, the synthetic station wind speed.
- `WIND_FROM_DIRECTION_DEG` defaults to `270.0`, the meteorological wind-from direction.
- `TEMPERATURE_K` defaults to `298.0`, the station air temperature.
- `MIXING_HEIGHT_M` defaults to `1000.0`, the diagnostic mixing height.
- `PRECIPITATION_RATE_MM_H` defaults to `0.2`, the precipitation rate used by the meteorological field.
- `EMISSION_RATE_G_S` defaults to `35.0`, the smoke emission rate.
- `SOURCE_X_M` defaults to `1500.0`, the local x coordinate of the source.
- `SOURCE_Y_M` defaults to `1500.0`, the local y coordinate of the source.
- `SOURCE_HEIGHT_M` defaults to `10.0`, the release height above local ground.
- `PARTICLE_SEED` defaults to `1234`, the deterministic particle-backend seed.

All parameters may be overridden as shell environment variables.

## Expected Products

- `wildfire_arson_effects_config.json`: the generated scenario configuration.
- `meteo.nc`: the SpritzMet meteorological field.
- `gaussian/concentration.nc`: the Gaussian concentration product.
- `particles/concentration.nc`: the particle concentration product.
- `gaussian/post.json`: the Gaussian SpritzPost summary.
- `particles/post.json`: the particle SpritzPost summary.
- `figures/gaussian_concentration_map.png`: a publication-ready 2-D concentration map.
- `figures/gaussian_concentration_profile.png`: a publication-ready vertical concentration profile.
- `figures/gaussian_concentration_3d.png`: a publication-ready 3-D concentration surface.

## Step-by-Step Method

### Step 1: Runtime Environment Diagnostic

The pipeline starts with `scripts/sprtz_doctor.py` to record the Python runtime, required numerical dependencies, and optional feature availability. This is a provenance step: later workflow analysis can distinguish scientific failures from missing optional rendering or NetCDF dependencies.

```bash
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"
```

### Step 2: Wildfire/Arson Configuration Synthesis

The bash script writes a self-contained Sprtz JSON file into the output directory. The file defines a local grid, a deterministic upwind meteorological station, one smoke source, three receptors, field concentration output levels, Gaussian defaults, and particle-backend controls. This is scenario orchestration, not a private model API.

### Step 3: Public Configuration Validation

The generated scenario is validated through `scripts/sprtz.py validate`. This check ensures that the configuration is a valid public Sprtz input before the workflow spends time on meteorology, dispersion, and rendering.

```bash
python3 "${SCRIPTS_DIR}/sprtz.py" validate "${CONFIG_PATH}"
```

### Step 4: SpritzMet Meteorological Interpolation

`scripts/spritzmet.py` converts the station meteorology into a gridded NetCDF-CF meteorological product. The meteorology file is made explicit so workflow engines can cache it, inspect it, or rerun only downstream tasks if dispersion settings change.

```bash
python3 "${SCRIPTS_DIR}/spritzmet.py" --config "${CONFIG_PATH}" --output "${METEO_PATH}" --format netcdf
```

### Step 5: Gaussian Dispersion Simulation

`scripts/spritz.py` runs the Gaussian backend with the prepared configuration and meteorology. The output is a gridded and receptor concentration product suitable for deterministic reporting and figure generation.

```bash
python3 "${SCRIPTS_DIR}/spritz.py" --config "${CONFIG_PATH}" --meteo "${METEO_PATH}" --output "${GAUSSIAN_CONC}" --format netcdf --backend gaussian --output-interval 3600
```

### Step 6: Particle Dispersion Simulation

The particle backend is run as a separate command with an explicit seed. This keeps stochastic-style transport diagnostics reproducible while allowing the workflow to compare particle and Gaussian results under identical scenario and meteorological assumptions.

```bash
python3 "${SCRIPTS_DIR}/spritz.py" --config "${CONFIG_PATH}" --meteo "${METEO_PATH}" --output "${PARTICLE_CONC}" --format netcdf --backend particles --seed "${PARTICLE_SEED}" --output-interval 3600
```

### Step 7: Gaussian SpritzPost Summary

The Gaussian concentration product is reduced to a structured postprocessing report. The postprocessor is intentionally separate from the dispersion kernel so thresholds, maxima, and ranked summaries remain auditable workflow artifacts.

```bash
python3 "${SCRIPTS_DIR}/spritzpost.py" --input "${GAUSSIAN_CONC}" --output "${OUT_DIR}/gaussian/post.json"
```

### Step 8: Particle SpritzPost Summary

The particle concentration product receives the same explicit postprocessing treatment, allowing downstream analyses to compare summary statistics between backends.

```bash
python3 "${SCRIPTS_DIR}/spritzpost.py" --input "${PARTICLE_CONC}" --output "${OUT_DIR}/particles/post.json"
```

### Step 9: Publication-Ready 2-D Concentration Map

`tools/render.py` renders a 600 DPI horizontal concentration map from the Gaussian concentration field. The non-interactive `Agg` backend and workflow-local Matplotlib cache make the step suitable for headless execution on batch or CI systems.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render.py" "${GAUSSIAN_CONC}" --output "${FIGURE_DIR}/gaussian_concentration_map.png" --variable concentration_field --title "Wildfire/Arson Gaussian Concentration" --dpi 600 --level-index 1 --vector-density 18
```

### Step 10: Publication-Ready Vertical Concentration Profile

`tools/profiler.py` samples the concentration field at the source column and plots the vertical profile. The configuration is supplied so release-height annotations can be overlaid when supported by the renderer.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/profiler.py" "${GAUSSIAN_CONC}" --output "${FIGURE_DIR}/gaussian_concentration_profile.png" --variable concentration_field --x "${SOURCE_X_M}" --y "${SOURCE_Y_M}" --title "Wildfire/Arson Concentration Profile" --config "${CONFIG_PATH}" --dpi 600
```

### Step 11: Publication-Ready 3-D Concentration Surface

`tools/render3d.py` renders the Gaussian concentration field as a three-dimensional surface. The northeast camera preset and moderate vertical exaggeration are chosen for legibility while preserving deterministic workflow behavior.

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render3d.py" "${GAUSSIAN_CONC}" --output "${FIGURE_DIR}/gaussian_concentration_3d.png" --variable concentration_field --title "Wildfire/Arson Concentration Field" --config "${CONFIG_PATH}" --dpi 600 --mode surface --view northeast --vertical-exaggeration 3
```

## Workflow-Engine Integration

Every executable stage is a process-level command. A workflow engine can represent diagnostic, validation, meteorology, Gaussian dispersion, particle dispersion, postprocessing, and rendering as separate tasks with explicit inputs and outputs. The pipeline uses public command-line boundaries throughout, which makes retry, caching, resource assignment, and provenance capture straightforward.

## Reproducibility Notes

- The default meteorology, source, receptors, and particle seed are deterministic.
- The script performs no hidden network access.
- NetCDF is requested explicitly because it is the preferred Sprtz interchange format for gridded meteorology and concentration fields.
- Operational data acquisition, incident-specific emissions estimation, or WRF ingestion must be added as explicit upstream workflow steps when needed.

## References

No external bibliographic references are required for this workflow description. Scientific and numerical assumptions are documented in the Sprtz numerical-model, particle-model, and visualization documentation.
