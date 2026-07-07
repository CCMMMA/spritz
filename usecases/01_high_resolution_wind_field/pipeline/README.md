# High-Resolution Wind Field Pipeline

## Scientific Purpose

This pipeline builds a deterministic local 100 m meteorological grid using only command-line wrappers from the repository-level `scripts/` directory. It is an operational decomposition of the high-resolution wind-field use case: the script prepares a minimal local-grid configuration, validates it through the public Sprtz CLI, and runs SpritzMet to produce a NetCDF-CF wind product.

The pipeline is intentionally constrained to externally invocable suite wrappers suitable for workflow engines.

## Operational Contract

Run from the repository root, or from any other working directory:

```bash
bash usecases/01_high_resolution_wind_field/pipeline/pipeline.sh
```

The script resolves the repository root from its own location and invokes only:

- `scripts/sprtz_doctor.py`
- `scripts/sprtz.py`
- `scripts/spritzmet.py`

Products are written under `data/01_high_resolution_wind_field/` by default. Set `SPRTZ_DATA_ROOT` to change the data root, or set `SPRTZ_OUTPUT_DIR` to choose the exact output directory.

The script also sets `MPLCONFIGDIR` to `${SPRTZ_OUTPUT_DIR}/.matplotlib` by default so Matplotlib can build font and style caches in a workflow-writable location. Override `MPLCONFIGDIR` explicitly when the workflow engine provides a shared rendering cache.

## Parameters

- `NX` defaults to `21`, the number of local-grid cells in the x direction.
- `NY` defaults to `21`, the number of local-grid cells in the y direction.
- `DX` defaults to `100`, the grid spacing in metres in the x direction.
- `DY` defaults to `100`, the grid spacing in metres in the y direction.
- `WIND_SPEED_M_S` defaults to `5.0`, the synthetic station wind speed.
- `WIND_FROM_DIRECTION_DEG` defaults to `270.0`, the meteorological wind-from direction.
- `TEMPERATURE_K` defaults to `294.0`, the station air temperature.
- `MIXING_HEIGHT_M` defaults to `900.0`, the diagnostic mixing height.
- `PRECIPITATION_RATE_MM_H` defaults to `0.0`, the precipitation rate.

All parameters may be overridden as shell environment variables.

## Expected Products

- `high_resolution_wind_config.json`: the generated local-grid Sprtz configuration.
- `spritzmet_100m_wind.nc`: the NetCDF-CF SpritzMet meteorological product.
- `figures/wind_speed_map.png`: a publication-ready 2-D wind-speed map with vector overlay.
- `figures/wind_speed_profile.png`: a publication-ready vertical wind-speed profile.
- `figures/wind_speed_3d.png`: a publication-ready three-dimensional wind-field surface.

## Step-by-Step Method

### Step 1: Runtime Environment Diagnostic

The pipeline first runs `scripts/sprtz_doctor.py`. This records whether the local environment has the optional features needed for preferred outputs, especially NetCDF support. In operational provenance, this step explains why a run produced NetCDF products or would need a fallback format.

Executable command:

```bash
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"
```

### Step 2: Local-Grid Configuration Synthesis

The bash script writes a self-contained JSON configuration into the output directory. The configuration defines a regular local grid, one synthetic meteorological station, and minimal source/receptor records required by the shared Sprtz configuration schema. This keeps the pipeline independent from demo-only Python helpers while still producing a normal public Sprtz input file.

The synthetic station is deterministic and intended for workflow validation, teaching, and smoke testing. A production workflow that starts from WRF data should add an explicit upstream WRF ingestion/downscaling task and pass the resulting public SpritzMet-compatible product to later stages.

### Step 3: Public Configuration Validation

The generated JSON is validated with `scripts/sprtz.py validate`. This is an important boundary check: it demonstrates that the generated configuration is accepted through the installed command-line interface and is not coupled to internal test code or use-case-only imports.

Executable command:

```bash
python3 "${SCRIPTS_DIR}/sprtz.py" validate "${CONFIG_PATH}"
```

### Step 4: SpritzMet High-Resolution Wind Generation

The final scientific stage invokes `scripts/spritzmet.py` to interpolate the station meteorology onto the configured 100 m grid and write a NetCDF-CF product. The output file is the workflow artifact consumed by downstream dispersion, visualization, or verification stages.

Executable command:

```bash
python3 "${SCRIPTS_DIR}/spritzmet.py" --config "${CONFIG_PATH}" --output "${METEO_PATH}" --format netcdf
```

### Step 5: Publication-Ready 2-D Wind Map

The pipeline renders a high-resolution horizontal map from the SpritzMet NetCDF product using `tools/render.py`. This step is configured for non-interactive batch execution with `MPLBACKEND=Agg`, a 600 DPI raster output, and wind-vector density control so the resulting figure is suitable for reports, manuscripts, and workflow artifacts.

Executable command:

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render.py" "${METEO_PATH}" --output "${FIGURE_DIR}/wind_speed_map.png" --variable wind_speed --title "SpritzMet 100 m Wind Speed" --dpi 600 --vector-density 18
```

### Step 6: Publication-Ready Vertical Profile

The profile figure is generated with `tools/profiler.py` at the central local-grid column (`x=0`, `y=0`). The plot summarizes the vertical structure of the selected wind-speed variable and is useful for checking whether downstream dispersion simulations are being driven by physically interpretable meteorological structure.

Executable command:

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/profiler.py" "${METEO_PATH}" --output "${FIGURE_DIR}/wind_speed_profile.png" --variable wind_speed --x 0 --y 0 --title "SpritzMet 100 m Wind Profile" --dpi 600
```

### Step 7: Publication-Ready 3-D Wind Surface

The final rendering stage uses `tools/render3d.py` to produce a three-dimensional view of the wind field. The `surface` mode, northeast camera preset, and moderate vertical exaggeration are chosen to make spatial structure legible while preserving the deterministic nature of the pipeline output.

Executable command:

```bash
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render3d.py" "${METEO_PATH}" --output "${FIGURE_DIR}/wind_speed_3d.png" --variable wind_speed --title "SpritzMet 100 m Wind Field" --dpi 600 --mode surface --view northeast --vertical-exaggeration 3
```

## Workflow-Engine Integration

Each executable stage is a process-level command. A workflow engine can model the diagnostic, validation, SpritzMet generation, and rendering stages as separate tasks, with `high_resolution_wind_config.json`, `spritzmet_100m_wind.nc`, and the `figures/` products declared as concrete outputs. The script avoids use-case demo scripts so it can be treated as external operational software rather than a notebook-like demonstration.

## Reproducibility Notes

- The default station field is deterministic.
- The script performs no hidden network access.
- NetCDF is requested explicitly because it is the preferred Sprtz interchange format for gridded meteorology.
- WRF acquisition or real-data downscaling must be added as an explicit upstream workflow step when needed.

## References

No external bibliographic references are required for this workflow description. Scientific and numerical assumptions for SpritzMet are documented in the repository numerical-model and SpritzWRF/SpritzMet documentation.
