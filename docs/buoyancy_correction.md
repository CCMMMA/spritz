# SpritzFire Semi-coupled Buoyancy Wind Correction

## Scientific Scope

This document defines the semi-coupled fire-to-wind buoyancy correction used by SpritzFire. It treats buoyancy as a one-way diagnostic perturbation and documents numerical limits needed for reproducible sensitivity analysis.

## Physical Basis

Large fires can create pyroconvective updraft and near-surface inflow. Sprtz applies this as one-way fire-to-wind post-processing.

## Algorithm

Cells above the fire probability threshold receive wind-speed reduction in the core. Nearby perimeter cells receive wind-speed enhancement. Wind direction is unchanged.

## Configuration

Use `BuoyancyConfig` under `fire.buoyancy`.

## References

- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 1: Physical and quasi-physical models. International Journal of Wildland Fire, 18(4), 349-368.
- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 2: Empirical and quasi-empirical models. International Journal of Wildland Fire, 18(4), 369-386.
- Mandel, J., Beezley, J. D., and Kochanski, A. K. (2011). Coupled atmosphere-wildland fire modeling with WRF-Fire. Geoscientific Model Development, 4, 591-610. https://doi.org/10.5194/gmd-4-591-2011
- Courant, R., Friedrichs, K., and Lewy, H. (1928). Uber die partiellen Differenzengleichungen der mathematischen Physik. Mathematische Annalen, 100, 32-74.
- LeVeque, R. J. (1997). Wave propagation algorithms for multidimensional hyperbolic systems. Journal of Computational Physics, 131(2), 327-353.
