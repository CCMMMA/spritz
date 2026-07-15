# Use case 01 — High-resolution wind field

## Narrative

This use case demonstrates how Sprtz turns regional WRF meteorology into a
terrain-aware local wind product suitable for coastal analysis,
visualization, and downstream dispersion workflows. Its documented scenario
is Velalonga 2026 in the Bay of Naples: a 24-hour period beginning at
`20260621Z0000`, downscaled from WRF5 d03 forcing to a local grid with 100 m
spacing.

The workflow has a deliberately clear scientific boundary. SpritzWRF reads
WRF and CF metadata, including physical valid times. SpritzMet then samples the
regional fields onto a shared local grid and applies bounded, documented
terrain and land-cover adjustments. The result is a deterministic diagnostic
downscaling product, not a new 100 m numerical weather prediction
integration.

The principal output is a NetCDF-CF meteorological file containing
time-dependent three-dimensional wind components and derived wind diagnostics.
When present in the WRF source, it also preserves diagnostic 10 m wind,
precipitation, 2 m temperature, and 2 m relative humidity. The accompanying
visualization workflow produces horizontal maps, vertical profiles, and
terrain-aware 3-D views.

The fixed Velalonga domain covers:

```text
south: 40.78
north: 40.85
west:  14.18
east:  14.33
```

At 100 m spacing, the bounding-box workflow derives a centered, snapped
`129 × 79` local grid. Its vertical levels are altitudes above mean sea level.
Diagnostic `U10M` and `V10M`, however, remain wind at 10 m above local ground;
the two references must not be treated as interchangeable over land.

All use-case inputs and generated products live under the repository-level
`data/` directory unless an explicit alternative data or output path is
provided.

## Available setup scenarios

### 1. Guided manual demo

Use [`demo/README.md`](demo/README.md) when learning, inspecting, or modifying
individual stages. It provides commands for:

1. downloading the 24 hourly WRF files;
2. acquiring buffered COP30 DEM and Copernicus LC100 land cover;
3. building the aligned terrain/GEO product;
4. running SpritzWRF → SpritzMet downscaling;
5. rendering maps, profiles, vector fields, and 3-D products.

The computation driver is:

```bash
python usecases/01_high_resolution_wind_field/demo/step_01_downscale_wind.py \
  --date 20260621Z0000 \
  --hours 24 \
  --download-dir data/wrf/d03 \
  --output data/output/high_resolution_wind_field/wrf_100m_wind_bbox.nc \
  --south 40.78 --north 40.85 --west 14.18 --east 14.33 \
  --dx 100 --dy 100 \
  --config usecases/01_high_resolution_wind_field/demo/config.json \
  --dem data/output/high_resolution_wind_field/dem/cop30_naples.tif \
  --land-cover data/output/high_resolution_wind_field/landcover/lc100_naples.tif
```

The driver can also consume explicitly supplied local WRF input instead of
downloading it. Synthetic input is available only through the explicit
`--allow-synthetic` option and is intended for development or fallback
testing, not scientific interpretation.

### 2. End-to-end shell pipeline

Use [`pipeline/pipeline.sh`](pipeline/pipeline.sh) for a repeatable,
shell-oriented run of the complete Velalonga scenario:

```bash
bash usecases/01_high_resolution_wind_field/pipeline/pipeline.sh
```

The pipeline downloads forcing and geospatial inputs, builds terrain, computes
the wind field, and renders the documented products. Environment variables can
override the date, duration, bounding box, spacing, input/output paths, terrain
buffer, coastline settings, and rendering parameters. See
[`pipeline/README.md`](pipeline/README.md) for the full operational contract.

This setup requires network access for missing WRF, COP30, LC100, and optional
Cartopy coastline data. On HPC systems with a shared outbound IP, cache the
global LC100 source once and crop it locally as documented in
[`demo/README.md`](demo/README.md); direct GDAL range reads can exhaust Zenodo's
per-IP request limit.

### 3. CWL workflow

Use [`workflow/workflow.cwl`](workflow/workflow.cwl) to run the shell pipeline
through a Common Workflow Language v1.2 runner. The CWL wrapper exposes the
main scenario, path, terrain, and visualization controls as typed inputs and
declares the principal output artifacts.

The required `repo_root` input points to the Sprtz checkout:

```yaml
repo_root:
  class: Directory
  path: ../../..
date_utc: "20260621Z0000"
hours: 24
```

See [`workflow/README.md`](workflow/README.md) for execution and output
details.

### 4. Dagonstar-oriented orchestration

[`dagonstar/workflow.py`](dagonstar/workflow.py) is an integration sketch for
Dagonstar environments. It is useful when adapting the use case to an external
task scheduler with site-specific storage, resource, retry, and provenance
policies. Dagonstar is not installed or configured by Sprtz; consult
[`dagonstar/README.md`](dagonstar/README.md) before using this setup.

### 5. Serial, hybrid, or MPI computation

Serial execution is the portability baseline and requires no `mpi4py`.
SpritzMet can also use automatic, threaded, process-based, or MPI execution
where supported. MPI is optional and must preserve serial-equivalent
scientific output; only rank 0 writes shared products.

Use parallel execution only after validating it against the serial result for
the same inputs and configuration. Install the optional MPI dependencies and
use the command-line parallel controls documented by the demo driver.

## Environment

Python 3.10 or newer is required. For the complete real-data workflow, install
the development, NetCDF, geospatial, and visualization extras:

```bash
python -m pip install -e '.[dev,netcdf,geo,viz]'
```

MPI support remains optional:

```bash
python -m pip install -e '.[mpi]'
```

Local raster and already-downloaded WRF workflows can avoid network access,
but the corresponding optional readers must still be installed.

## Main products

The standard output directory is
`data/output/high_resolution_wind_field/`. The complete scenario produces:

- `wrf_100m_wind_bbox.nc`, the 24-frame NetCDF-CF wind product;
- `geo.nc`, the aligned terrain and land-cover product;
- buffered DEM and land-cover source rasters plus provenance/cache metadata;
- six 10 m wind maps from `20260621Z0900` through `20260621Z1400`;
- an animated center-column vertical wind profile;
- an animated terrain-aware 3-D wind field;
- 3-D vector and voxel diagnostic frames.

## Assumptions and limitations

- WRF forcing and derived fields are modeled values, not observations.
- Downscaling does not create the resolved atmospheric dynamics of a native
  100 m model integration.
- DEM and categorical land-cover products must cover and align with the target
  grid; land cover is never bilinearly interpolated.
- Terrain vertical exaggeration affects visualization only.
- Production use requires input provenance, timestamp and coordinate checks,
  comparison with geographically distributed observations, and independent
  validation.
- This clean-room use case is not an official Velalonga forecast and makes no
  regulatory-equivalence claim.

## References

No additional bibliographic references are required for this overview.
Scientific assumptions and peer-reviewed references are maintained in
[`../../docs/numerical_model.md`](../../docs/numerical_model.md) and
[`../../docs/spritzwrf_spritzmet.md`](../../docs/spritzwrf_spritzmet.md).
