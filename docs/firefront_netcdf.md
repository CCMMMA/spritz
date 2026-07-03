# SpritzFire NetCDF-CF Output

## Scientific Scope

This document defines the NetCDF-CF representation of SpritzFire outputs. It focuses on coordinate metadata, units, time axes, and interoperability with the wider Sprtz analysis pipeline.

`firefront.nc` follows a compact CF-1.8 layout with `time`, `x`, `y`, optional `lat`/`lon`, `fire_probability(time,y,x)`, `arrival_time(y,x)`, and `intensity(time,y,x)`.

When `netCDF4` is not installed, Sprtz writes a JSON fallback with the same logical fields.

## References

- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 1: Physical and quasi-physical models. International Journal of Wildland Fire, 18(4), 349-368.
- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 2: Empirical and quasi-empirical models. International Journal of Wildland Fire, 18(4), 369-386.
- Mandel, J., Beezley, J. D., and Kochanski, A. K. (2011). Coupled atmosphere-wildland fire modeling with WRF-Fire. Geoscientific Model Development, 4, 591-610. https://doi.org/10.5194/gmd-4-591-2011
- Courant, R., Friedrichs, K., and Lewy, H. (1928). Uber die partiellen Differenzengleichungen der mathematischen Physik. Mathematische Annalen, 100, 32-74.
- LeVeque, R. J. (1997). Wave propagation algorithms for multidimensional hyperbolic systems. Journal of Computational Physics, 131(2), 327-353.
- Rew, R., and Davis, G. (1990). NetCDF: an interface for scientific data access. IEEE Computer Graphics and Applications, 10(4), 76-82. https://doi.org/10.1109/38.56302
