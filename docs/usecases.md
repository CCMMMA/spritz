# Operational use cases

The root-level `usecases/` directory contains documented operational templates. They are meant to be copied into project-specific case folders and version-controlled with event metadata. Each folder exposes explicit `step_*.py` scripts rather than one script that runs the whole case.

## Data Preparation

Operational use cases should prepare meteorology and terrain explicitly under
the repository `data/` tree:

```bash
tools/meteouniparthenope-wrf-download.py 20260601Z0000 \
  --hours 24 \
  --domain d03 \
  --data-root data

python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_naples.tif

python3 tools/copernicus-lc100-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/landcover/lc100_naples.tif
```

The WRF files feed SpritzWRF/SpritzMet. The COP30 GeoTIFF feeds
`sprtz-terrain fetch` as a local DEM input, and the LC100 GeoTIFF feeds the
local land-cover input with `target_categories: "copernicus-lc100"`. See
`docs/meteouniparthenope-wrf-download.md`,
`docs/copernicus-cop30-dem-download.md`, and
`docs/copernicus-lc100-download.md`.

All date-time values passed as script arguments or script parameters use compact
UTC `YYYYMMDDZhhmm` format, such as `20260601Z0000`.

Use-case scripts call `tools/plotter.py` for NetCDF intermediate and final
products when a map can be derived locally. The generated PNG maps are written
beside the use-case outputs; see `docs/plotter.md` for direct commands and
Cartopy coastline options.

## 01 - High-resolution wind and precipitation interpolation

This use case implements the meteorological preprocessing chain:

```text
meteo@uniparthenope WRF5 d03 or local WRF NetCDF -> SpritzWRF -> SpritzMet -> 100 m NetCDF-CF wind and precipitation-rate field
```

It supports direct downloads from:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

The default grid is 101 x 101 points at 100 m spacing, centered on the requested coordinate.

## 02 - Arson or wildfire effects

This use case consumes the same WRF/SpritzWRF/SpritzMet path as use case 01, then builds a Spritz scenario from event location, burning material, source height above ground, start/end datetimes, area, firefighter-action windows, and emission assumptions. It accepts `generic`, `paper`, and `plastic` material presets and can expand a JSON list of multiple fire events into multiple Spritz source records. It can run the configured Gaussian or particle backend and writes the ordinary Spritz model outputs.

## 03 - Satellite and AI-supported model evaluation

This use case evaluates Spritz concentration/deposition output against a satellite-derived mask and reports confusion-matrix metrics, CSI/threat score, false-alarm ratio, probability of detection, and deterministic AI-style calibration output.

## 04 - Production incident catalog

This use case reads a semicolon-delimited incident catalog and builds validated
Spritz configurations with event metadata, local receptors, WGS84 receptor
coordinates, and optional geographic concentration maps. The bundled rows cover
the supplied Acerra `2021_44` incident on 30/07/2021 at 14:00 for 3 hours and
the San Marcellino `2023_14` incident on 14/07/2023 at 15:00 for 3 hours.

## 05 - High-resolution sailing wind forecast

This use case creates a forecast-ready wind product over a latitude/longitude
bounding box, with explicit initialization date at Z00, outlook in hours,
horizontal resolution, vertical resolution, and time resolution. The default
example targets a Bay of Naples race area for precision top class professional
sailing: current UTC day at Z00, 24 hour outlook, bounding box
`14.18,40.78,14.33,40.85`, 100 m horizontal resolution, 10 m vertical
resolution, and 10 minute temporal resolution. The bundled implementation is deterministic and
offline so downstream race-planning tooling can validate the full
space-height-time schema before authoritative forecast data are connected.

## 06 - Acerra waste-to-energy chimney screening

This use case creates a 12-hour point-source chimney scenario for the
waste-to-energy plant in Acerra, starting on 2026-06-01. The source location is
`40.978473 N, 14.384058 E`, the chimney release height is 110 m above local
ground level, hourly outputs are enabled, and precipitation washout is enabled
in the JSON configuration. The scenario uses transparent placeholder emissions
and stack parameters for workflow testing; operational interpretation requires
plant-specific data and validation.

## Documentation standard

Each use case README contains purpose, workflow, inputs, commands, outputs, assumptions, and validation checks. Commands use the same coordinate examples and WRF archive pattern so the use cases remain consistent.
# Use Cases

Use cases are runnable teaching and production templates under `usecases/`.

For SLURM, wrap each command in a batch file with environment setup:

```bash
#!/bin/bash
#SBATCH --job-name=sprtz_usecase
#SBATCH --ntasks=4
#SBATCH --time=00:20:00
module load python/3.11 openmpi/4.1
source .venv/bin/activate
python usecases/10_backward_plume_origin/step_01_prepare_meteorology.py
mpiexec -n $SLURM_NTASKS python usecases/10_backward_plume_origin/step_02_estimate_source.py
```

See `docs/hpc.md` for full SLURM templates.
