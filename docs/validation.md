# Validation plan

This implementation is deterministic and production-hardened as software, but scientific equivalence requires a validation campaign.

Required validation levels:

1. unit tests with analytic expectations for grids, wind components, plume kernels, particle determinism, and statistics;
2. input-deck tests for representative Fortran-style SpritzMet/Spritz/SpritzPost controls;
3. NetCDF-CF metadata and variable checks for module interoperability;
4. component parity tests against redistributable reference outputs;
5. mass-conservation and monotonicity checks for plume and particle kernels;
6. end-to-end workflow regression tests pinned by versioned input data;
7. figure-regression smoke tests for visualization outputs.

Operational or regulatory use requires a documented numerical acceptance envelope for each component and input-data pathway.


## Production acceptance gate

A deployment should not be accepted only because the software tests pass. For operational studies, define acceptance cases with fixed input meteorology, emission parameters, receptors, and post-processing metrics. Archive the Sprtz version, git commit, command line, configuration file, NetCDF-CF interchange files, and generated figures. Use `sprtz doctor` to capture the runtime environment in the run dossier.
