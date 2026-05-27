# PyPuff operational use cases

This folder contains runnable, GitHub-ready operational templates built on the public PyPuff API.  They are designed for reproducible case directories: raw data, derived meteorology, model configuration, concentration products, figures, and evaluation reports should stay together.

PyPuff is a clean-room project.  In these use cases the former CALWRF and CALMET roles are represented by the Python modules **PyWRF** and **PyMET**:

- **PyWRF** (`pypuff.models.pywrf`) reads WRF/WRF-like NetCDF files, extracts latitude/longitude and near-surface wind, and downloads WRF5 d03 files from the meteo@uniparthenope archive when requested.
- **PyMET** (`pypuff.models.pymet`) creates a local projected grid, interpolates the PyWRF wind field, and writes a NetCDF-CF meteorological product for module interoperability.

All workflows prefer NetCDF-CF for interoperability and provide JSON/CSV fallbacks for lightweight tests.

## WRF 1 km data source

The use cases can download WRF5 d03 history files using this archive pattern:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

Example for 2026-05-27 cycle 00:

```bash
pypuff-usecase-wind \
  --download-date 2026-05-27 \
  --download-cycle-hour 0 \
  --download-dir data/wrf \
  --output output/wrf_100m_wind.nc \
  --center-lat 40.85 \
  --center-lon 14.27
```

The downloader reuses an existing local file unless `--force-download` is passed.  Use `--print-download-url` to verify the URL before downloading.

## Use cases

1. `01_high_resolution_wind_field` - PyWRF → PyMET downscaling from WRF 1 km to a 100 m local wind product centered on a supplied latitude/longitude.
2. `02_wildfire_arson_effects` - wildfire/arson dispersion scenario using a WRF-derived wind field, source heat/emission parameterization, and Gaussian or particle backends.
3. `03_satellite_ai_evaluation` - evaluation of wildfire/arson model output against satellite-derived masks with deterministic AI-style calibration metrics.

## Production notes

- Use real WRF NetCDF files for operational runs; synthetic mode exists only for smoke tests, CI, and tutorials.
- Validate fuel load, emission factors, fire radiative power, satellite retrieval uncertainty, and model configuration before supporting decisions.
- Record the WRF file name, archive URL, cycle hour, event coordinates, timestamps, and PyPuff version in each case directory.
- Prefer NetCDF-CF outputs for traceability; JSON fallback is useful for code review and tests but less complete for large gridded products.
