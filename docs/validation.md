# Validation plan

This implementation is deterministic and production-hardened as software, but scientific equivalence requires a validation campaign.

Required validation levels:

1. unit tests with analytic expectations for grids, wind components, plume kernels, particle determinism, and statistics;
2. input-deck tests for representative Fortran-style SpritzMet/Spritz/SpritzPost controls;
3. NetCDF-CF metadata and variable checks for module interoperability,
   including receptor-table variables and gridded
   `concentration_field(time, field_z, field_y, field_x)` outputs;
4. component parity tests against redistributable reference outputs;
5. WRF precipitation extraction checks for direct rate variables and accumulated
   `RAINC`/`RAINNC`/`RAINSH` increments;
6. source-window, firefighter-window, and precipitation-washout limiting cases;
7. mass-conservation and monotonicity checks for plume and particle kernels;
8. end-to-end workflow regression tests pinned by versioned input data;
9. figure-regression smoke tests for visualization outputs.

Operational or regulatory use requires a documented numerical acceptance
envelope for each component and input-data pathway, including WRF precipitation
handling, chimney release heights, material/emission assumptions, and any
suppression-action emission factors.


## Production acceptance gate

A deployment should not be accepted only because the software tests pass. For operational studies, define acceptance cases with fixed input meteorology, emission parameters, receptors, and post-processing metrics. Archive the Spritz version, git commit, command line, configuration file, NetCDF-CF interchange files, and generated figures. Use `sprtz doctor` to capture the runtime environment in the run dossier.
