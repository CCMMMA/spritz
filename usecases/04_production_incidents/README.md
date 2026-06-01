# Use case 04 - Production incident catalog

Goal: run production-style Sprtz screening cases from an auditable incident
catalog. The bundled catalog includes the supplied Acerra and San Marcellino
events:

| Anno | CodGisa | Luogo | lat | long | Data | Ora inizio | Durata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2020 | 2021_44 | Acerra | 40,926506 | 14,380875 | 30/07/2021 | 14 | 3 ore |
| 2023 | 2023_14 | San Marcellino | 40,98472 | 14,18250 | 14/07/2023 | 15 | 3 ore |

## Run the configured incident

```bash
python usecases/04_production_incidents/run.py \
  --code 2021_44 \
  --output-dir output/production_2021_44 \
  --interchange netcdf
```

To run the San Marcellino event, pass `--code 2023_14`.

Expected products:

- `2021_44_config.json` - validated Sprtz configuration with event metadata;
- `model/meteo.nc` - SpritzMet meteorology exchange file;
- `model/concentration.nc` - Spritz concentration output with receptor lat/lon;
- `model/post.json` - SpritzPost statistics;
- `2021_44_concentration_map.png` - geographic concentration map.

## Optional local basemap

For offline production dossiers, pass a prepared high-resolution raster basemap:

```bash
python usecases/04_production_incidents/run.py \
  --code 2021_44 \
  --output-dir output/production_2021_44 \
  --basemap data/basemaps/acerra.png \
  --basemap-extent 14.30,40.87,14.46,40.98
```

The extent is `west,south,east,north` in WGS84 degrees. The repository does not
download map tiles implicitly.

## Scientific caution

This use case is a production-style software workflow, not a certified incident
reconstruction. Wind, emissions, source geometry, and receptors are explicit
inputs and must be replaced with validated project data before operational use.
