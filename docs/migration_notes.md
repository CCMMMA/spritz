# Migration notes

## Scientific Scope

This document records migration guidance for users moving between Sprtz versions and workflows. It preserves public behavior where possible and explains scientific or interoperability changes when behavior must evolve.

The legacy suite archives were used only to identify component names and public file roles. The Python package uses independent source code, synthetic examples, and a clean-room implementation boundary.

Terrain and MakeGeo are style references for packaging, CLI-first operation, JSON configuration, tolerant legacy parsing, tests, and documentation.

Recommended migration path:

1. validate legacy `.inp` files with `sprtz validate`;
2. run SpritzMet to NetCDF-CF with `spritzmet --format netcdf`;
3. compare Gaussian and particle backends with the same config and `meteo.nc`
   by changing JSON `run.backend` or passing `spritz --backend`;
4. postprocess with SpritzPost summaries;
5. publish plots with `sprtz-plot`;
6. add project-specific parser extensions for unsupported legacy keys while preserving unknown values in `run` / `raw`.

## References

- Wilson, G., Aruliah, D. A., Brown, C. T., Hong, N. P. C., Davis, M., Guy, R. T., Haddock, S. H. D., Huff, K. D., Mitchell, I. M., Plumbley, M. D., Waugh, B., White, E. P., and Wilson, P. (2014). Best practices for scientific computing. PLOS Biology, 12(1), e1001745. https://doi.org/10.1371/journal.pbio.1001745
- Sandve, G. K., Nekrutenko, A., Taylor, J., and Hovig, E. (2013). Ten simple rules for reproducible computational research. PLOS Computational Biology, 9(10), e1003285. https://doi.org/10.1371/journal.pcbi.1003285
- Hanna, S. R. (1989). Confidence limits for air quality model evaluations, as estimated by bootstrap and jackknife resampling methods. Journal of the Air and Waste Management Association, 39(9), 1170-1175.
- Chang, J. C., and Hanna, S. R. (2004). Air quality model performance evaluation. Meteorology and Atmospheric Physics, 87, 167-196.
