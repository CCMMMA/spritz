# Migration notes

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
