# SpritzFire

SpritzFire is a clean-room stochastic cellular-automaton wildfire spread module for Sprtz. It uses PROPAGATOR-inspired fuel classes, Moore-neighborhood spread, named wind/slope/moisture modifiers, ensemble realizations, and JSON/NetCDF output.

## Configuration

Add a `fire` block with ignitions, realizations, moisture fallback, runtime, seed, and optional spotting, FIRMS, buoyancy, GPU, or MPI settings. Use `sprtzfire --config examples/wildfire_minimal.json --output-dir output_fire`.

## Outputs

`firefront.nc` or JSON fallback stores fire probability, mean arrival time, intensity, and snapshots. `fire_perimeter.geojson` stores thresholded perimeter envelopes.

## Advanced Features

RandomFront spotting, FIRMS ignition ingestion, semi-coupled buoyancy correction, and GPU detection are optional. CPU serial execution remains the baseline.
