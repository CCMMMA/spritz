# SpritzFire

## Scientific Scope

This document introduces SpritzFire as a clean-room cellular fire-front component coupled to Sprtz meteorology and dispersion products. It frames the model as a deterministic research and screening workflow rather than a certified operational fire simulator.

SpritzFire is a clean-room stochastic cellular-automaton wildfire spread module for Sprtz. It uses PROPAGATOR-inspired fuel classes, Moore-neighborhood spread, named wind/slope/moisture modifiers, ensemble realizations, and JSON/NetCDF output.

## Configuration

Add a `fire` block with ignitions, realizations, moisture fallback, runtime, seed, and optional spotting, FIRMS, buoyancy, GPU, or MPI settings. Use `sprtzfire --config examples/wildfire_minimal.json --output-dir output_fire`.

## Outputs

`firefront.nc` or JSON fallback stores fire probability, mean arrival time, intensity, and snapshots. `fire_perimeter.geojson` stores thresholded perimeter envelopes.

## Advanced Features

RandomFront spotting, FIRMS ignition ingestion, semi-coupled buoyancy correction, and GPU detection are optional. CPU serial execution remains the baseline.

## Parallel Execution

SpritzFire uses realization splitting for MPI. Optional CUDA is selected per rank with `--gpu-backend auto` or `--gpu-backend cupy`; NumPy CPU execution remains the default.

## References

- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 1: Physical and quasi-physical models. International Journal of Wildland Fire, 18(4), 349-368.
- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 2: Empirical and quasi-empirical models. International Journal of Wildland Fire, 18(4), 369-386.
- Mandel, J., Beezley, J. D., and Kochanski, A. K. (2011). Coupled atmosphere-wildland fire modeling with WRF-Fire. Geoscientific Model Development, 4, 591-610. https://doi.org/10.5194/gmd-4-591-2011
- Courant, R., Friedrichs, K., and Lewy, H. (1928). Uber die partiellen Differenzengleichungen der mathematischen Physik. Mathematische Annalen, 100, 32-74.
- LeVeque, R. J. (1997). Wave propagation algorithms for multidimensional hyperbolic systems. Journal of Computational Physics, 131(2), 327-353.
