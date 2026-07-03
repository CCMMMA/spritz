# SpritzFire Numerical Methods

## Scientific Scope

This document records the numerical assumptions behind SpritzFire. It is intended to make empirical coefficients, conservation choices, monotonicity expectations, and stability limits visible to reviewers.

## Cellular Automaton

Spread uses a Moore neighborhood. Transition probability is the nominal 7-class fuel probability multiplied by named wind, slope, and fine-fuel-moisture factors, then clamped to `[0, 1]`.

## Rate Of Spread

Nominal ROS is adjusted by the same modifiers. Transition time is cell distance divided by ROS, with diagonal moves using `sqrt(2) * dx`.

## Byram Intensity

Byram fireline intensity is computed from available fuel load, heat of combustion, moisture, and ROS.

## RandomFront Spotting

Firebrand landing distance follows a lognormal distribution. The location parameter derives from intensity, wind speed at ABL top, ABL height, firebrand radius, and settling velocity. The 99.5th percentile defines the characteristic maximum spotting distance.

## Buoyancy Correction

Semi-coupled buoyancy uses Byram convective number. Wind-driven fires below `N_c=2` are unchanged; plume-dominated fires above `N_c=10` receive full core updraft reduction and perimeter inflow enhancement.

## References

- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 1: Physical and quasi-physical models. International Journal of Wildland Fire, 18(4), 349-368.
- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 2: Empirical and quasi-empirical models. International Journal of Wildland Fire, 18(4), 369-386.
- Mandel, J., Beezley, J. D., and Kochanski, A. K. (2011). Coupled atmosphere-wildland fire modeling with WRF-Fire. Geoscientific Model Development, 4, 591-610. https://doi.org/10.5194/gmd-4-591-2011
- Courant, R., Friedrichs, K., and Lewy, H. (1928). Uber die partiellen Differenzengleichungen der mathematischen Physik. Mathematische Annalen, 100, 32-74.
- LeVeque, R. J. (1997). Wave propagation algorithms for multidimensional hyperbolic systems. Journal of Computational Physics, 131(2), 327-353.
- Weil, J. C., Sykes, R. I., and Venkatram, A. (1992). Evaluating air-quality models: review and outlook. Journal of Applied Meteorology, 31(10), 1121-1145.
