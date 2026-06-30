# Use case 06 - Acerra waste-to-energy chimney screening

Goal: simulate a didactic 12-hour emission from the waste-to-energy plant in
Acerra, starting on 2026-06-01, using a clean-room Spritz point-source chimney
scenario.

The source is centered at `40.978473 N, 14.384058 E`. The chimney release height
is 110 m above local ground level.

NetCDF/time convention: generated meteorology and concentration NetCDF products
follow strict CF metadata. Scenario start/end datetimes are encoded in the
configuration and propagated to model outputs; no use-case step infers
scientific datetimes from filenames.

## Data preparation

Prepare WRF and COP30 terrain files for production-style reruns:

```bash
tools/meteouniparthenope-wrf-download.py 20260601Z0000 \
  --hours 12 \
  --domain d03 \
  --data-root data
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.90 --north 41.03 \
  --west 14.30 --east 14.45 \
  --output data/dem/cop30_acerra_wte.tif
python3 tools/copernicus-lc100-download.py \
  --south 40.90 --north 41.03 \
  --west 14.30 --east 14.45 \
  --output data/landcover/lc100_acerra_wte.tif
```

The default use case remains self-contained. Replace the placeholder
meteorology with WRF-derived SpritzMet products prepared with both `--dem` and
`--land-cover`, and use the same DEM/LC100 pair through `sprtz-terrain fetch`
when standalone operational terrain/GEO products are required.

## Step 1: Build the configuration

```bash
python usecases/06_acerra_waste_to_energy/step_01_build_config.py \
  --output output/acerra_wte/acerra_waste_to_energy.json
```

## Step 2: Run the model

```bash
python usecases/06_acerra_waste_to_energy/step_02_run_model.py \
  --config output/acerra_wte/acerra_waste_to_energy.json \
  --output-dir output/acerra_wte/model \
  --interchange netcdf
```

## Step 3: Plot intermediate and final NetCDF maps

The model step calls `tools/plotter.py` automatically for NetCDF products. To
regenerate maps explicitly, run:

```bash
python tools/plotter.py output/acerra_wte/model/meteo.nc \
  --variable wind_speed \
  --output output/acerra_wte/model/meteo_map.png

python tools/plotter.py output/acerra_wte/model/concentration.nc \
  --variable concentration \
  --output output/acerra_wte/model/concentration_map.png
```

## Scenario

- Weather simulation start: `2026-06-01T00:00:00+00:00`.
- Weather simulation end: `2026-06-01T12:00:00+00:00`.
- Emission event start: `2026-06-01T00:00:00+00:00`.
- Emission event end: `2026-06-01T12:00:00+00:00`.
- Source type: point chimney.
- Chimney height above ground level: 110 m.
- Output interval: 1 hour.
- Precipitation washout: enabled in the JSON configuration; it has no effect
  unless the meteorology contains nonzero `precipitation_rate`.

## Outputs

- `acerra_waste_to_energy.json` - validated Spritz scenario configuration.
- `model/meteo.*` - SpritzMet meteorology exchange file.
- `model/concentration.*` - concentration/deposition output.
- `model/post.json` - SpritzPost statistics.
- `meteo_map.png` and `concentration_map.png` - plotter maps for NetCDF
  intermediate and final products when plotting dependencies are available.

## Scientific Caution

This is a screening and documentation use case. The emission rate, stack
diameter, exit velocity, exit temperature, wind, and washout coefficient are
transparent placeholder values for exercising the workflow. Operational or
regulatory interpretation requires plant-specific emissions, stack parameters,
meteorology, chemistry/deposition assumptions, and independent validation.
