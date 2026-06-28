# Use case 04 - Production incident catalog

Goal: run production-style Spritz screening cases from an auditable incident
catalog. The bundled catalog includes the supplied Acerra and San Marcellino
events:

| Anno | CodGisa | Luogo | lat | long | Data | Ora inizio | Durata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2020 | 2021_44 | Acerra | 40,926506 | 14,380875 | 30/07/2021 | 14 | 3 ore |
| 2023 | 2023_14 | San Marcellino | 40,98472 | 14,18250 | 14/07/2023 | 15 | 3 ore |

## Data preparation

For incident dossiers, archive the exact meteorology and terrain inputs used by
the run:

```bash
tools/meteouniparthenope-wrf-download.py 20210730Z1400 \
  --hours 3 \
  --domain d03 \
  --data-root data
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.85 --north 41.05 \
  --west 14.25 --east 14.45 \
  --output data/dem/cop30_acerra.tif
python3 tools/copernicus-lc100-download.py \
  --south 40.85 --north 41.05 \
  --west 14.25 --east 14.45 \
  --output data/landcover/lc100_acerra.tif
```

Use `tools/meteouniparthenope-wrf-download.py` with the event start hour and
duration. Use the COP30 GeoTIFF as the local DEM and the LC100 GeoTIFF as the
local land-cover source for `sprtz-terrain fetch` when terrain/GEO products are
part of the incident package.

## Step 1: Build the configured incident

```bash
python usecases/04_production_incidents/step_01_build_config.py \
  --code 2021_44 \
  --output output/production_2021_44/2021_44_config.json
```

## Step 2: Run the model

```bash
python usecases/04_production_incidents/step_02_run_model.py \
  --config output/production_2021_44/2021_44_config.json \
  --output-dir output/production_2021_44/model \
  --interchange netcdf
```

To run the San Marcellino event, pass `--code 2023_14`.

## Step 3: Plot intermediate and final NetCDF maps

The model step calls `tools/plotter.py` automatically for NetCDF products. To
regenerate maps explicitly for a dossier, run:

```bash
python tools/plotter.py output/production_2021_44/model/meteo.nc \
  --variable wind_speed \
  --output output/production_2021_44/model/meteo_map.png

python tools/plotter.py output/production_2021_44/model/concentration.nc \
  --variable concentration \
  --output output/production_2021_44/model/concentration_map.png
```

Expected products:

- `2021_44_config.json` - validated Spritz configuration with event metadata;
- `model/meteo.nc` - SpritzMet meteorology exchange file;
- `model/concentration.nc` - Spritz concentration output with receptor lat/lon;
- `model/post.json` - SpritzPost statistics;
- `model/meteo_map.png` and `model/concentration_map.png` - plotter maps for
  NetCDF intermediate and final products when plotting dependencies are
  available.

## Plotter notes

The repository does not download map tiles implicitly. Cartopy coastlines are
drawn only when local Natural Earth data are available, unless the user
explicitly enables Cartopy downloads in `tools/plotter.py`.

## Scientific caution

This use case is a production-style software workflow, not a certified incident
reconstruction. Wind, emissions, source geometry, and receptors are explicit
inputs and must be replaced with validated project data before operational use.
