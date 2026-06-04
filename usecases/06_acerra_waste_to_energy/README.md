# Use case 06 - Acerra waste-to-energy chimney screening

Goal: simulate a didactic 12-hour emission from the waste-to-energy plant in
Acerra, starting on 2026-06-01, using a clean-room Spritz point-source chimney
scenario.

The source is centered at `40.978473 N, 14.384058 E`. The chimney release height
is 110 m above local ground level.

## Run

```bash
python usecases/06_acerra_waste_to_energy/run.py \
  --output-dir output/acerra_wte \
  --interchange netcdf
```

For a configuration-only run:

```bash
python usecases/06_acerra_waste_to_energy/run.py \
  --output-dir output/acerra_wte \
  --config-only
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

## Scientific Caution

This is a screening and documentation use case. The emission rate, stack
diameter, exit velocity, exit temperature, wind, and washout coefficient are
transparent placeholder values for exercising the workflow. Operational or
regulatory interpretation requires plant-specific emissions, stack parameters,
meteorology, chemistry/deposition assumptions, and independent validation.
