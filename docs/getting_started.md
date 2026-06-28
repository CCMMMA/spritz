# Getting started: from WRF download to visualization

This guide walks through a complete, reproducible Spritz workflow starting with a WRF 1 km file from the meteo@uniparthenope archive and ending with a publication-ready concentration figure.

The guide is intentionally didactic. Each step produces an inspectable file that can be reused by the next step.

## 0. What the workflow does

The end-to-end path is:

```text
WRF 1 km NetCDF
  -> SpritzWRF extraction
  -> SpritzMet 100 m local wind and precipitation-rate field
  -> Spritz wildfire/arson scenario
  -> unified Gaussian or particle dispersion
  -> SpritzPost-style statistics
  -> publishing-quality figure
```

Use case 01 demonstrates the SpritzWRF -> SpritzMet meteorological downscaling step. Use case 02 adds a wildfire/arson source and runs Spritz. The visualization CLI then renders the model concentration output. The offline Terrain example can be run independently with `sprtz-terrain fetch --config examples/highres_terrain_local.json --json`.

## 1. Create and check the Python environment

From the repository root:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -e .[netcdf,viz]
```

For MPI/HPC runs, install the MPI extra as well:

```bash
python -m pip install -e .[netcdf,viz,mpi]
```

For Terrain acquisition from GeoTIFF/COG or online provider adapters, install:

```bash
python -m pip install -e .[geo,netcdf,viz]
```

Run the production diagnostics:

```bash
sprtz doctor --require-netcdf --require-viz
```

Expected result:

```text
Spritz 0.4.4 production diagnostics: OK
```

## 2. Choose a WRF cycle and build the download URL

Spritz use cases use the meteo@uniparthenope WRF5 d03 history pattern:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

For example, the 00 UTC cycle for 2026-05-27 is:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/2026/05/27/wrf5_d03_20260527Z0000.nc
```

To ask Spritz to print the exact URL without downloading:

```bash
python usecases/01_high_resolution_wind_field/step_01_interpolate_wind.py \
  --download-time 20260527Z0000 \
  --output ignored.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --print-download-url
```

## 3. Download WRF and create a 100 m SpritzMet wind product

This command downloads the WRF file when it is not already present in `data/wrf/`, extracts near-surface wind with SpritzWRF, and interpolates it onto a 100 m local SpritzMet grid centered on the requested coordinate:

```bash
mkdir -p data/wrf output

python usecases/01_high_resolution_wind_field/step_01_interpolate_wind.py \
  --download-time 20260527Z0000 \
  --download-dir data/wrf \
  --output output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100
```

You can also request a geographic bounding box instead of a center plus node
count. In this mode, `--dx` and `--dy` remain hard constraints; Spritz expands
the actual covered area outward to the nearest exact 100 m grid multiple:

```bash
python usecases/01_high_resolution_wind_field/step_01_interpolate_wind.py \
  --download-time 20260527Z0000 \
  --download-dir data/wrf \
  --output output/wrf_100m_wind_bbox.nc \
  --south 40.40 \
  --north 41.10 \
  --west 13.80 \
  --east 14.80 \
  --dx 100 \
  --dy 100
```

Main output:

```text
output/wrf_100m_wind.nc
```

Expected NetCDF-CF fields include:

- `time` with strict CF absolute UTC units when the WRF file provides valid-time metadata
- `z` height coordinate for wind levels
- `latitude`, `longitude`
- `eastward_wind(time,z,y,x)`, `northward_wind(time,z,y,x)`
- `wind_speed(time,z,y,x)`, `wind_from_direction(time,z,y,x)`
- `precipitation_rate(time,y,x)` when WRF precipitation is available, otherwise zeros

SpritzWRF reads valid time from WRF/CF metadata such as `Times`, CF `time`
units, or explicit global time attributes. It does not infer datetimes from the
WRF filename.

To rerun from a WRF file already downloaded:

```bash
python usecases/01_high_resolution_wind_field/step_01_interpolate_wind.py \
  --wrf data/wrf/wrf5_d03_20260527Z0000.nc \
  --output output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100
```

## 4. Run a smoke test without external data

For training, CI, or offline classroom sessions, the same workflow can use a deterministic synthetic WRF-like field:

```bash
python usecases/01_high_resolution_wind_field/step_01_interpolate_wind.py \
  --allow-synthetic \
  --json \
  --output output/demo_wind.json \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 21 \
  --ny 21 \
  --dx 100 \
  --dy 100
```

This does not replace real meteorological data. It is only for checking the installation and explaining the workflow.

## 5. Build and run a wildfire/arson scenario

Use case 02 creates a Spritz scenario for a burning place at a known latitude and longitude. It is intentionally split into explicit steps that generate:

- a local wind product;
- a Spritz scenario configuration;
- a model output directory containing meteorology, concentration, and postprocessing files.

Prepare the local wind product:

```bash
python usecases/02_wildfire_arson_effects/step_01_interpolate_wind.py \
  --download-time 20260527Z0000 \
  --download-dir data/wrf \
  --output output/wildfire_case/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 \
  --ny 101
```

Build the fire configuration:

```bash
python usecases/02_wildfire_arson_effects/step_02_build_config.py \
  --output output/wildfire_case/wildfire_event.json \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --material plastic \
  --duration-s 3600 \
  --area-m2 2500 \
  --start 20260527Z0000 \
  --end 20260527Z0100 \
  --precipitation-washout
```

Run the model:

```bash
python usecases/02_wildfire_arson_effects/step_03_run_model.py \
  --config output/wildfire_case/wildfire_event.json \
  --output-dir output/wildfire_case/model \
  --backend particles \
  --interchange netcdf
```

Use `--material generic`, `--material paper`, or `--material plastic` to choose
the documented screening material preset. Pass `--height-agl-m` for an
above-ground source or chimney release height. Add `--firefighters-start`,
`--firefighters-end`, and `--firefighters-emission-factor` when suppression
actions should reduce emissions during part of the run.

For multiple simultaneous or staggered fires, pass `--fire-events-json` with a
JSON list. Each entry can define `latitude`, `longitude`, `height_agl_m`,
`start_datetime`, `end_datetime`, `material`, `area_m2`, and optional
temperature or emission overrides. Date-time values passed through scripts use
compact UTC `YYYYMMDDZhhmm`:

```bash
python usecases/02_wildfire_arson_effects/step_02_build_config.py \
  --output output/multi_fire/wildfire_event.json \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --fire-events-json '[{"id":"F1","latitude":40.85,"longitude":14.27,"material":"paper","start_datetime":"20260601Z0000","end_datetime":"20260601Z0300"},{"id":"F2","latitude":40.855,"longitude":14.275,"height_agl_m":2.0,"material":"plastic","start_datetime":"20260601Z0100","end_datetime":"20260601Z0400"}]' \
  --weather-start 20260601Z0000 \
  --weather-end 20260601Z0400
```

Expected products:

```text
output/wildfire_case/wrf_100m_wind.nc
output/wildfire_case/wildfire_event.json
output/wildfire_case/model/meteo.nc
output/wildfire_case/model/concentration.nc
output/wildfire_case/model/post.json
```

## 6. Run the core suite directly from a configuration file

Use case 02 writes a standard Spritz configuration. You can rerun the suite directly from that file:

```bash
sprtz validate output/wildfire_case/wildfire_event.json

sprtz run output/wildfire_case/wildfire_event.json \
  --output-dir output/wildfire_case/model_gaussian \
  --backend gaussian \
  --interchange netcdf

sprtz run output/wildfire_case/wildfire_event.json \
  --output-dir output/wildfire_case/model_particles \
  --backend particles \
  --interchange netcdf
```

The backend can also be selected in the JSON file:

```json
{
  "run": {
    "backend": "particles"
  }
}
```

For a gridded 3D concentration field, request model-grid output and vertical
levels in the same `run` block:

```json
{
  "run": {
    "backend": "gaussian",
    "concentration_output": "grid",
    "field_z_levels": [0.0, 25.0, 50.0]
  }
}
```

NetCDF-CF output then includes `concentration_field(time, field_z, field_y,
field_x)` in addition to the receptor table.

To enable precipitation washout in a WRF-driven run:

```json
{
  "run": {
    "precipitation_washout": true,
    "precipitation_washout_coefficient_s_per_mm_h": 0.00001
  }
}
```

The option uses `precipitation_rate` from the SpritzMet meteorology product.

For MPI execution, use:

```bash
mpiexec -n 4 sprtz run output/wildfire_case/wildfire_event.json \
  --output-dir output/wildfire_case/model_mpi \
  --backend particles \
  --interchange netcdf \
  --parallel auto
```

## 7. Create a publication-quality concentration figure

Render a concentration scatter plot from the NetCDF-CF output:

```bash
sprtz-plot \
  --input output/wildfire_case/model/concentration.nc \
  --output output/wildfire_case/concentration.png \
  --title "Spritz wildfire screening concentration" \
  --dpi 300
```

The figure is written to:

```text
output/wildfire_case/concentration.png
```

For manuscripts or reports, keep the NetCDF-CF file together with the figure so the plot remains traceable to the model output.

## 8. Evaluate against a satellite or AI-derived mask

Use case 03 compares the model concentration field with a satellite-derived smoke, fire, or burned-area mask. The mask can be JSON, NPY, CSV, TXT, or numeric ASCII.

Create a tiny deterministic demo mask:

```bash
python usecases/03_satellite_ai_evaluation/step_01_make_demo_mask.py \
  output/demo_mask.json
```

Run evaluation:

```bash
python usecases/03_satellite_ai_evaluation/step_02_evaluate.py \
  --concentration output/wildfire_case/model/concentration.nc \
  --satellite-mask output/demo_mask.json \
  --output output/wildfire_case/evaluation.json \
  --threshold 0.5
```

The report includes confusion-matrix counts, accuracy, precision, recall/probability of detection, F1, critical success index, false-alarm ratio, and deterministic logistic calibration diagnostics.

## 9. Run the Acerra waste-to-energy chimney case

Use case 06 builds a 12-hour screening scenario for the waste-to-energy plant in
Acerra at `40.978473 N, 14.384058 E`, with a 110 m chimney release height and a
start datetime of `2026-06-01T00:00:00+00:00`.

```bash
python usecases/06_acerra_waste_to_energy/step_01_build_config.py \
  --output output/acerra_wte/acerra_waste_to_energy.json
python usecases/06_acerra_waste_to_energy/step_02_run_model.py \
  --config output/acerra_wte/acerra_waste_to_energy.json \
  --output-dir output/acerra_wte/model \
  --interchange netcdf
```

For configuration review only:

```bash
python usecases/06_acerra_waste_to_energy/step_01_build_config.py \
  --output output/acerra_wte/acerra_waste_to_energy.json
```

The generated `acerra_waste_to_energy.json` uses source-level
`height_agl_m: 110.0`, weather/event start and end datetimes, hourly output, and
precipitation washout enabled.

## 10. Recommended directory layout for a real case

A clear case directory helps later audit and publication:

```text
case_YYYYMMDD_hh/
├── data/
│   └── wrf/
│       └── wrf5_d03_YYYYMMDDZhh00.nc
├── met/
│   └── wrf_100m_wind.nc
├── model/
│   ├── meteo.nc
│   ├── concentration.nc
│   └── post.json
├── figures/
│   └── concentration.png
├── evaluation/
│   └── satellite_evaluation.json
└── config/
    └── wildfire_event.json
```

The bundled use cases write to `output/` by default, but operational projects should use case-specific folders like the one above.

## 11. Production checklist

Before sharing results, confirm:

1. `sprtz doctor --require-netcdf --require-viz` passes in the execution environment.
2. The WRF file name, cycle time, and download URL are recorded.
3. The center latitude/longitude or requested/actual bounding box, grid spacing, and grid size are documented.
4. The generated Spritz configuration is archived with the outputs.
5. The backend is stated clearly: `gaussian` or `particles`.
6. The figure was generated from the archived concentration file.
7. Any satellite mask or AI product is stored with its provenance, threshold, and preprocessing notes.
8. Scientific/regulatory conclusions are limited to the validation level achieved for the specific case.

## 12. Troubleshooting

### `netCDF4 is required to read WRF NetCDF files`

Install the NetCDF extra:

```bash
python -m pip install -e .[netcdf]
```

### `matplotlib is required for visualization`

Install the visualization extra:

```bash
python -m pip install -e .[viz]
```

### The WRF download fails

Check the URL first:

```bash
python usecases/01_high_resolution_wind_field/step_01_interpolate_wind.py \
  --download-time 20260527Z0000 \
  --output ignored.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --print-download-url
```

Then verify that the requested date and cycle exist in the archive. The downloader intentionally does not silently substitute another meteorological cycle.

### The use cases are not importable as `sprtz.usecases`

That is intentional. The use cases are educational workflows under the repository root. Reusable production code stays in `src/sprtz/`.
