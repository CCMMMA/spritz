# Getting started: from WRF download to visualization

This guide walks through a complete, reproducible Sprtz workflow starting with a WRF 1 km file from the meteo@uniparthenope archive and ending with a publication-ready concentration figure.

The guide is intentionally didactic. Each step produces an inspectable file that can be reused by the next step.

## 0. What the workflow does

The end-to-end path is:

```text
WRF 1 km NetCDF
  -> SpritzWRF extraction
  -> SpritzMet 100 m local wind field
  -> Sprtz wildfire/arson scenario
  -> Gaussian or particle dispersion
  -> SpritzPost-style statistics
  -> publishing-quality figure
```

Use case 01 demonstrates the SpritzWRF -> SpritzMet meteorological downscaling step. Use case 02 adds a wildfire/arson source and runs Sprtz. The visualization CLI then renders the model concentration output.

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

Run the production diagnostics:

```bash
sprtz doctor --require-netcdf --require-viz
```

Expected result:

```text
Sprtz 0.4.4 production diagnostics: OK
```

## 2. Choose a WRF cycle and build the download URL

Sprtz use cases use the meteo@uniparthenope WRF5 d03 history pattern:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

For example, the 00 UTC cycle for 2026-05-27 is:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/2026/05/27/wrf5_d03_20260527Z0000.nc
```

To ask Sprtz to print the exact URL without downloading:

```bash
python usecases/01_high_resolution_wind_field/run.py \
  --download-date 2026-05-27 \
  --download-cycle-hour 0 \
  --output ignored.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --print-download-url
```

## 3. Download WRF and create a 100 m SpritzMet wind product

This command downloads the WRF file when it is not already present in `data/wrf/`, extracts near-surface wind with SpritzWRF, and interpolates it onto a 100 m local SpritzMet grid centered on the requested coordinate:

```bash
mkdir -p data/wrf output

python usecases/01_high_resolution_wind_field/run.py \
  --download-date 2026-05-27 \
  --download-cycle-hour 0 \
  --download-dir data/wrf \
  --output output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100
```

Main output:

```text
output/wrf_100m_wind.nc
```

Expected NetCDF-CF fields include:

- `latitude`, `longitude`
- `eastward_wind`, `northward_wind`
- `wind_speed`, `wind_from_direction`

To rerun from a WRF file already downloaded:

```bash
python usecases/01_high_resolution_wind_field/run.py \
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
python usecases/01_high_resolution_wind_field/run.py \
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

Use case 02 creates a Sprtz scenario for a burning place at a known latitude and longitude. It uses the same WRF download mechanism, then generates:

- a local wind product;
- a Sprtz scenario configuration;
- a model output directory containing meteorology, concentration, and postprocessing files.

Example with the particle backend:

```bash
python usecases/02_wildfire_arson_effects/run.py \
  --download-date 2026-05-27 \
  --download-cycle-hour 0 \
  --download-dir data/wrf \
  --output-dir output/wildfire_case \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --temperature-k 1100 \
  --duration-s 3600 \
  --area-m2 2500 \
  --backend particles \
  --interchange netcdf
```

Example with an already downloaded WRF file and the Gaussian backend:

```bash
python usecases/02_wildfire_arson_effects/run.py \
  --wrf data/wrf/wrf5_d03_20260527Z0000.nc \
  --output-dir output/wildfire_case \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --temperature-k 1100 \
  --duration-s 3600 \
  --area-m2 2500 \
  --backend gaussian \
  --interchange netcdf
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

Use case 02 writes a standard Sprtz configuration. You can rerun the suite directly from that file:

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
  --title "Sprtz wildfire screening concentration" \
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
python usecases/03_satellite_ai_evaluation/make_demo_mask.py \
  output/demo_mask.json
```

Run evaluation:

```bash
python usecases/03_satellite_ai_evaluation/run.py \
  --concentration output/wildfire_case/model/concentration.nc \
  --satellite-mask output/demo_mask.json \
  --output output/wildfire_case/evaluation.json \
  --threshold 0.5
```

The report includes confusion-matrix counts, accuracy, precision, recall/probability of detection, F1, critical success index, false-alarm ratio, and deterministic logistic calibration diagnostics.

## 9. Recommended directory layout for a real case

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

## 10. Production checklist

Before sharing results, confirm:

1. `sprtz doctor --require-netcdf --require-viz` passes in the execution environment.
2. The WRF file name, cycle time, and download URL are recorded.
3. The center latitude/longitude, grid spacing, and grid size are documented.
4. The generated Sprtz configuration is archived with the outputs.
5. The backend is stated clearly: `gaussian` or `particles`.
6. The figure was generated from the archived concentration file.
7. Any satellite mask or AI product is stored with its provenance, threshold, and preprocessing notes.
8. Scientific/regulatory conclusions are limited to the validation level achieved for the specific case.

## 11. Troubleshooting

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
python usecases/01_high_resolution_wind_field/run.py \
  --download-date 2026-05-27 \
  --download-cycle-hour 0 \
  --output ignored.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --print-download-url
```

Then verify that the requested date and cycle exist in the archive. The downloader intentionally does not silently substitute another meteorological cycle.

### The use cases are not importable as `sprtz.usecases`

That is intentional. The use cases are educational workflows under the repository root. Reusable production code stays in `src/sprtz/`.
