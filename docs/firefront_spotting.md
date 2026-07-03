# SpritzFire Fire Spotting - RandomFront 2.3

## Scientific Scope

This document describes the RandomFront spotting extension as a stochastic post-step process. It emphasizes reproducible random seeds, separation from nominal transition rules, and scientifically bounded ember-transport assumptions.

## Overview

RandomFront spotting is implemented as a post-processing step after each cellular-automaton timestep.

## Physical Model

Firebrand landing distance is sampled from a lognormal distribution. Azimuth is biased toward the wind direction.

## Parameterization

The lognormal location parameter is derived from Byram intensity, ABL height, wind speed, firebrand radius, and terminal settling velocity.

## Configuration

Use `SpottingConfig` under `fire.spotting_config` and set `fire.spotting=true`.

## Limitations

The current implementation uses uniform shape parameter sigma and does not model full vertical wind profiles.

## References

- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 1: Physical and quasi-physical models. International Journal of Wildland Fire, 18(4), 349-368.
- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 2: Empirical and quasi-empirical models. International Journal of Wildland Fire, 18(4), 369-386.
- Mandel, J., Beezley, J. D., and Kochanski, A. K. (2011). Coupled atmosphere-wildland fire modeling with WRF-Fire. Geoscientific Model Development, 4, 591-610. https://doi.org/10.5194/gmd-4-591-2011
- Courant, R., Friedrichs, K., and Lewy, H. (1928). Uber die partiellen Differenzengleichungen der mathematischen Physik. Mathematische Annalen, 100, 32-74.
- LeVeque, R. J. (1997). Wave propagation algorithms for multidimensional hyperbolic systems. Journal of Computational Physics, 131(2), 327-353.
- Koo, E., Pagni, P. J., Weise, D. R., and Woycheese, J. P. (2010). Firebrands and spotting ignition in large-scale fires. International Journal of Wildland Fire, 19(7), 818-843.
