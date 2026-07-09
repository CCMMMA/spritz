# Validation plan

SpritzMet validation helpers cover scalar RMSE, MAE, and bias, wind vector RMSE
and direction error, and divergence diagnostics. See
[`spritzmet_physics.md`](spritzmet_physics.md).

## Scientific Scope

This document defines the Sprtz validation strategy. It combines unit tests, numerical invariants, inter-model comparisons, and literature-aligned performance diagnostics without claiming regulatory equivalence.

This implementation is deterministic and production-hardened as software, but scientific equivalence requires a validation campaign.

Required validation levels:

1. unit tests with analytic expectations for grids, wind components, plume kernels, particle determinism, and statistics;
2. input-deck tests for representative Fortran-style SpritzMet/Spritz/SpritzPost controls;
3. NetCDF-CF metadata and variable checks for module interoperability,
   including receptor-table variables and gridded
   `concentration_field(time, field_z, field_y, field_x)` outputs;
4. grid-axis consistency checks for particle/Gaussian comparison products,
   including identical `time`, `field_z`, `field_y`, and `field_x`
   coordinates before metrics are computed, plus centered-grid checks that the
   middle field cell maps back to configured `center_lat`/`center_lon` metadata;
5. clean-room CALPUFF-style binary export checks against the canonical
   NetCDF-CF gridded concentration, dry-flux, and wet-flux fields;
6. component parity tests against redistributable reference outputs;
7. WRF precipitation extraction checks for direct rate variables and accumulated
   `RAINC`/`RAINNC`/`RAINSH` increments;
8. source-window, firefighter-window, and precipitation-washout limiting cases;
9. mass-conservation and monotonicity checks for plume and particle kernels;
10. end-to-end workflow regression tests pinned by versioned input data;
11. figure-regression smoke tests for visualization outputs.

Operational or regulatory use requires a documented numerical acceptance
envelope for each component and input-data pathway, including WRF precipitation
handling, chimney release heights, material/emission assumptions, and any
suppression-action emission factors.


## Production acceptance gate

A deployment should not be accepted only because the software tests pass. For operational studies, define acceptance cases with fixed input meteorology, emission parameters, receptors, and post-processing metrics. Archive the Spritz version, git commit, command line, configuration file, NetCDF-CF interchange files, and generated figures. Use `sprtz doctor` to capture the runtime environment in the run dossier.

## References

- Wilson, G., Aruliah, D. A., Brown, C. T., Hong, N. P. C., Davis, M., Guy, R. T., Haddock, S. H. D., Huff, K. D., Mitchell, I. M., Plumbley, M. D., Waugh, B., White, E. P., and Wilson, P. (2014). Best practices for scientific computing. PLOS Biology, 12(1), e1001745. https://doi.org/10.1371/journal.pbio.1001745
- Sandve, G. K., Nekrutenko, A., Taylor, J., and Hovig, E. (2013). Ten simple rules for reproducible computational research. PLOS Computational Biology, 9(10), e1003285. https://doi.org/10.1371/journal.pcbi.1003285
- Hanna, S. R. (1989). Confidence limits for air quality model evaluations, as estimated by bootstrap and jackknife resampling methods. Journal of the Air and Waste Management Association, 39(9), 1170-1175.
- Chang, J. C., and Hanna, S. R. (2004). Air quality model performance evaluation. Meteorology and Atmospheric Physics, 87, 167-196.
