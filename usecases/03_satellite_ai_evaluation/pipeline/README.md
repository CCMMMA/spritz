# Aversa satellite-evaluation pipeline

The canonical shell pipeline implements the procedure in
[`../demo/README.md`](../demo/README.md):

```bash
bash usecases/03_satellite_ai_evaluation/pipeline/pipeline.sh
```

By default it runs offline with deterministic fallback meteorology and
satellite-like evidence. The real Sentinel-5P download uses Copernicus Data
Space Sentinel Hub OAuth2 client credentials, not a single API key. Create the
credentials in the Dashboard before enabling network mode:

1. Sign in at <https://shapps.dataspace.copernicus.eu/dashboard/>.
2. Open `User Settings`.
3. In `OAuth clients`, click `Create`.
4. Name the client, choose an expiry, and leave the frontend/SPA option off for
   this command-line workflow.
5. Copy the displayed `client ID` and `client secret` immediately; the secret
   is not shown again.

Export the credentials only in your local shell or secret manager, not in files
committed to the repository:

```bash
export CDSE_CLIENT_ID='...'
export CDSE_CLIENT_SECRET='...'
export SPRTZ_RUN_NETWORK=1
bash usecases/03_satellite_ai_evaluation/pipeline/pipeline.sh
```

To check the Sentinel-5P request without credentials, run the downloader with
`--dry-run`; it writes the `.request.json` provenance file and does not contact
the network. The canonical downloader command is
`tools/copernicus-s5p-download.py`; its help and error messages are
band-neutral even though `AER_AI_340_380` is the canonical use-case band and
`NO2` remains available as a secondary diagnostic option.

The network pipeline downloads a broad same-orbit Aerosol Index raster and lets
the alignment step crop it to the Spritz concentration-field domain. Smaller
domain-sized Sentinel Hub requests can return valid but all-masked GeoTIFFs for
this product. If even the broad same-orbit request returns zero finite Aerosol
Index pixels, the downloader and pipeline fail intentionally. Archive the
`.request.json` as negative provenance, or continue the didactic workflow with
the deterministic non-satellite mask by explicitly setting:

```bash
export SPRTZ_ALLOW_SYNTHETIC_SATELLITE_FALLBACK=1
```

`SPRTZ_DATA_ROOT`, `SPRTZ_OUTPUT_DIR`, `PYTHON`, `MPLCONFIGDIR`, and
`XDG_CACHE_HOME` may be overridden. Products default to
`data/03_satellite_ai_evaluation/`.

The eleven stages are runtime/configuration validation, WRF download, COP30
download, LC100 download, Terrain/GEO generation, 601×351 100 m SpritzWRF/SpritzMet
downscaling, Gaussian and particle runs, Sentinel-5P download, conservative
satellite downscaling, backend-specific evaluation, and plotting. The
evaluation stage also reads `usecase_03_stations.csv` and writes a colocated
NO₂ station spatial-pattern diagnostic into each backend `evaluation.json`.
NO₂ is normalized only for pattern comparison; it is not converted to Aerosol
Index or Spritz concentration. Network access is explicit; credentials are read
only from the environment and are never logged.

Expected products include WRF and satellite source data when network mode is
enabled, `dem/cop30_aversa.tif`, `landcover/lc100_aversa.tif`, `geo.nc`,
`domain/meteo.nc`, Gaussian and particle concentration NetCDF files,
backend-specific evaluation/difference/ratio/statistics artifacts, and two
concentration plots.

The pipeline is deterministic in offline mode. Network mode records the
Sentinel Hub request and satellite-alignment provenance. The same-day
Sentinel-5P orbit overlaps the event, but its UV Aerosol Index is not a direct
measurement of three-dimensional near-surface concentration.

## References

Veefkind, J. P., et al. (2012). TROPOMI on the ESA Sentinel-5 Precursor: A GMES
mission for global observations of the atmospheric composition for climate,
air quality and ozone layer applications. *Remote Sensing of Environment,
120*, 70–83.
