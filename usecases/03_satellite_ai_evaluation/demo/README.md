# Use case 03 — Aversa fire and Sentinel-5P NO₂ evaluation

> **Evidence classification:** this Aversa workflow is an incident consistency
> evaluation, not the formal validation of Spritz dispersion physics. Formal
> backend validation uses `step_00_validate_controlled_tracer.py` with paired
> controlled-release observations as documented in the parent README. Satellite
> products cannot replace a known source term and paired receptor measurements.

## Event

- Place: Aversa, Caserta, Campania, Italy.
- Ignition: `20240619Z1000` (19 June 2024, 10:00 UTC).
- Position: 40.9769° N, 14.2168° E.
- Duration: three hours, ending `20240619Z1300`.
- Fuel description: construction-material storage.
- Primary satellite observation: Sentinel-5P/TROPOMI L2 tropospheric NO₂ at
  `20240619Z1205` (reported timestamp 12:05:18 UTC).
- Secondary observation: same-orbit UV Aerosol Index for plume-footprint plots.

The Copernicus catalogue confirms same-day product
`S5P_OFFL_L2__AER_AI_20240619T113407_20240619T131537_34633_03_020600_20240621T012148.nc`,
whose Aversa coverage interval is 11:55:42–12:47:58 UTC and therefore overlaps
the modeled fire. The workflow requests the same orbit as `NO2` with
`minQa=75`. Multi-level Spritz concentration is integrated vertically,
converted from g m⁻² to mol m⁻² using the NO₂ molar mass, and aggregated to
native TROPOMI pixels. Aerosol Index remains a secondary smoke-footprint
diagnostic and is not treated as a concentration measurement.

## Data and credentials

All inputs and outputs live below `data/satellite_ai_evaluation/`.

WRF d03 history is downloaded from the public meteo@uniparthenope archive.
Sentinel-5P is requested from the official Copernicus Data Space Sentinel Hub
Process API. The downloader uses OAuth2 client credentials, not a single API
key. Create them before enabling network mode:

1. Sign in to the Copernicus Data Space Ecosystem Dashboard:
   <https://shapps.dataspace.copernicus.eu/dashboard/>
2. Open `User Settings`.
3. Find the `OAuth clients` section.
4. Click `Create`.
5. Give the client a recognizable name such as `sprtz-usecase03-aversa`.
6. Choose an expiry date. Use a short expiry for shared machines; use
   `Never expire` only if you accept the operational risk.
7. Do not enable the single-page-application/frontend option for this command
   line workflow.
8. Click `Create`.
9. Copy both values immediately:
   - `client ID`
   - `client secret`

The client secret is shown only once. Store it in your shell, password manager,
or local secret manager, never in `config.json`, README files, notebooks, shell
history committed to Git, or logs. Export the credentials for the current
terminal session:

```bash
export CDSE_CLIENT_ID='...'
export CDSE_CLIENT_SECRET='...'
export SPRTZ_RUN_NETWORK=1
```

You can verify the request shape without credentials or network access:

```bash
python tools/copernicus-s5p-download.py \
  --bbox 12.00 39.00 16.50 43.00 \
  --time-start 2024-06-19T11:34:07Z \
  --time-end 2024-06-19T13:15:37Z \
  --band NO2 --min-qa 75 --width 256 --height 256 \
  --output data/output/satellite_ai_evaluation/satellite/sentinel5p_no2_20240619T120518Z_full_orbit.tif \
  --dry-run
```

With credentials exported, remove `--dry-run` to download the GeoTIFF. The
script exchanges `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET` for a short-lived
access token at the Copernicus Data Space token endpoint, then calls the
Sentinel Hub Process API. After download, it validates the GeoTIFF and fails if
the selected bbox, time range, band, and QA filter produced zero finite pixels.
If either environment variable is missing, the satellite download stops with:

```text
CDSE_CLIENT_ID and CDSE_CLIENT_SECRET are required unless --dry-run is used
```

Use `tools/copernicus-s5p-download.py` for all Sentinel-5P bands in this use
case. Its command-line help and error messages are intentionally band-neutral;
`--band NO2` is the canonical evaluation observable. `--band AER_AI_340_380`
is retained for the secondary smoke-footprint figure.

The satellite stage requires the `geo` optional dependencies:

```bash
python -m pip install -e '.[dev,netcdf,viz,geo]'
```

Without `SPRTZ_RUN_NETWORK=1`, the pipeline remains runnable offline using
configured meteorology and a deterministic synthetic observation. Offline
results must not be described as satellite validation.

## Complete workflow

```bash
bash usecases/03_satellite_ai_evaluation/pipeline/pipeline.sh
```

The canonical workflow performs these stages:

1. validate the event configuration;
2. download WRF d03 files for `20240619Z1000`, `20240619Z1100`,
   `20240619Z1200`, and `20240619Z1300`;
3. download a buffered COP30 digital elevation model;
4. download buffered Copernicus LC100 land cover;
5. build the aligned Terrain/GEO product;
6. run SpritzWRF/SpritzMet downscaling onto the 601×351, 100 m Aversa
   domain using DEM and land cover;
7. run Gaussian and particle dispersion with identical forcing;
8. download primary Sentinel-5P L2 NO₂ and secondary Aerosol Index;
9. vertically integrate each Spritz backend and compare native-pixel NO₂ columns;
10. downscale Aerosol Index only for secondary footprint visualization;
11. write comparison plots and auditable JSON/CSV artifacts.

## Manual commands

### 1. Download WRF

```bash
python tools/meteouniparthenope-wrf-download.py 20240619Z1000 \
  --hours 4 --domain d03 \
  --data-root data/03_satellite_ai_evaluation/wrf
```

### 2. Download the high-resolution COP30 terrain

```bash
python tools/copernicus-cop30-dem-download.py \
  --center-lat 40.9769 \
  --center-lon 14.2168 \
  --nx 601 \
  --ny 351 \
  --dx 100 \
  --dy 100 \
  --buffer-m 5000 \
  --output data/output/satellite_ai_evaluation/dem/cop30_aversa.tif
```

The 5 km source-raster buffer keeps bilinear DEM sampling away from dataset
edges. The output is a DEM elevation source, not a DSM or building-height
product.

### 3. Download high-resolution Copernicus LC100 land cover

```bash
python tools/copernicus-lc100-download.py \
  --center-lat 40.9769 \
  --center-lon 14.2168 \
  --nx 601 \
  --ny 351 \
  --dx 100 \
  --dy 100 \
  --buffer-m 5000 \
  --output data/output/satellite_ai_evaluation/landcover/lc100_aversa.tif
```

LC100 is categorical land cover. It is sampled with nearest-neighbor logic;
the workflow never bilinearly interpolates class identifiers.

### 4. Build the matching terrain/GEO product

```bash
python scripts/sprtz_terrain.py fetch \
  --center-lat 40.9769 \
  --center-lon 14.2168 \
  --nx 601 \
  --ny 351 \
  --dx 100 \
  --dy 100 \
  --dem data/output/satellite_ai_evaluation/dem/cop30_aversa.tif \
  --landuse data/output/satellite_ai_evaluation/landcover/lc100_aversa.tif \
  --landuse-mapping copernicus-lc100 \
  --cache-dir data/output/satellite_ai_evaluation/terrain-cache \
  --output data/output/satellite_ai_evaluation/geo.nc
```

This creates the aligned terrain and surface-parameter product used for
provenance and three-dimensional visualization.

### 5. Compute the Aversa high-resolution wind field

This follows the same SpritzWRF → SpritzMet action and option semantics used by
use cases 01 and 02:

```bash
python usecases/03_satellite_ai_evaluation/demo/step_02_prepare_domain.py \
  --date 20240619Z1000 --hours 4 \
  --download-dir data/wrf/d03/ \
  --center-lat 40.9769 --center-lon 14.2168 \
  --nx 601 --ny 351 --dx 100 --dy 100 \
  --dem data/output/satellite_ai_evaluation/dem/cop30_aversa.tif \
  --land-cover data/output/satellite_ai_evaluation/landcover/lc100_aversa.tif \
  --advanced-physics \
  --bulk-richardson-number 0.0 \
  --mass-consistency-iterations 80 \
  --mass-consistency-relaxation 0.8 \
  --output data/output/satellite_ai_evaluation/domain/meteo.nc
```

DEM elevation constrains terrain-relative wind profiles and below-ground
masking. LC100 contributes surface roughness and bounded precipitation
adjustments. The neutral bulk Richardson number avoids inventing a stability
regime without event-specific evidence; advanced physics adds the documented
horizontal divergence-minimization diagnostic.

The shared configuration defines the weather and event window as
`20240619Z1000`–`20240619Z1300`, sets `output_duration_s=10800`, and requests
hourly output. Both dispersion backends therefore write concentration samples
at 11:00, 12:00, and 13:00 UTC. Four WRF states through 13:00 prevent the final
sample from silently reusing the 12:00 meteorology. Each backend writes both
the 11-receptor comparison transect and a genuine 601×351 concentration field
at 400 m above mean sea level for domain maps and satellite-pattern comparison.
The 400 m ASL level remains above the downloaded COP30 maximum of approximately
335.35 m. The separate receptor transect remains at 1.5 m above local ground.
The construction-storage screening source sets wet scavenging to zero because
the four WRF frames report no precipitation; dry deposition remains enabled.
Gaussian and particle outputs are configured for comparable one-hour windows:
`averaging_time_s=3600` and `particle_duration_s=3600`. The Gaussian backend
uses an explicit initial spread of `250 m` horizontally and `80 m` vertically.
The particle backend uses explicit random-walk diffusivities, `Kx=Ky=35 m²/s`
and `Kz=2 m²/s`, with 16 advection steps to make its spread control more
direct and reduce path-integration noise.

Evaluation uses `--time-index 1`, selecting the 12:00 UTC concentration output
as the closest hourly model state to the 12:05:18 Sentinel-5P observation.

### 6. Run both dispersion backends

```bash
python scripts/spritz.py \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --meteo data/output/satellite_ai_evaluation/domain/meteo.nc \
  --output data/output/satellite_ai_evaluation/model/gaussian/concentration.nc \
  --format netcdf --backend gaussian --output-interval 3600

python scripts/spritz.py \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --meteo data/output/satellite_ai_evaluation/domain/meteo.nc \
  --output data/output/satellite_ai_evaluation/model/particles/concentration.nc \
  --format netcdf --backend particles --seed 20240619 \
  --output-interval 3600
```

The canonical particle run uses 100,000 particles. This is intentionally
higher than a quick diagnostic run because the initial field was too sparse
with 5,000 particles for stable satellite-pattern comparison. The fixed seed
keeps repeated runs deterministic; production validation should additionally
check convergence across multiple particle counts and seeds.

The 60 km east-west by 35 km north-south domain replaces the earlier 20 km
square, 30 km east-west, 40×20 km, 40×30 km, and 50×30 km diagnostic domains.
The 50×30 km run cleared the Gaussian plume and the 12:00 particle plume, but
the particle backend still placed a small physical tail on the eastern boundary
at 13:00, with the active plume also approaching the northern boundary.
Extending the downwind/eastern side by another 10 km and the northern side by
5 km gives the east-northeast stochastic particle tail room to remain inside
the computational domain while preserving the established west and south
clearances. Boundary-contact diagnostics must still be reviewed after every
operational run, but they are threshold- and mass-fraction-aware: raw edge
activity is recorded only when a boundary cell exceeds `max(1e-15, 1e-12 ×
timestep_peak)`, and meaningful boundary contact is reported only when the
active edge mass fraction is at least `1e-6`. This keeps physically meaningful
weak plume tails visible while ignoring floating-point ghosts and isolated
stochastic particle crumbs. The Sentinel request bounding box covers the
complete expanded domain. Native-pixel NO₂ evaluation aggregates the model to
the satellite subset; secondary Aerosol Index visualization uses the broader
raster before cropping and terrain-guided downscaling.

### 7. Download primary Sentinel-5P NO₂ and secondary UV Aerosol Index

Use the band-neutral Sentinel-5P downloader. The canonical request keeps the
orbital overlap window fixed to the verified Sentinel-5P product and downloads
a broader same-orbit raster. The alignment step then crops that raster to the
Spritz concentration-field domain, whose current approximate bbox is
`13.9782 40.8417 14.6933 41.1570`. This is more robust than asking Sentinel
Hub for only the small Aversa domain: for this product, the small
domain-matched and regional requests can return syntactically valid but
all-masked GeoTIFFs, while the broader same-orbit request returns valid
Aerosol Index samples.

First write and inspect the request without contacting the network:

```bash
python tools/copernicus-s5p-download.py \
  --bbox 12.00 39.00 16.50 43.00 \
  --time-start 2024-06-19T11:34:07Z \
  --time-end 2024-06-19T13:15:37Z \
  --band NO2 --min-qa 75 --width 256 --height 256 \
  --output data/output/satellite_ai_evaluation/satellite/sentinel5p_no2_20240619T120518Z_full_orbit.tif \
  --dry-run

# Secondary Aerosol Index footprint product
python tools/copernicus-s5p-download.py \
  --bbox 12.00 39.00 16.50 43.00 \
  --time-start 2024-06-19T11:34:07Z \
  --time-end 2024-06-19T13:15:37Z \
  --band AER_AI_340_380 --min-qa 0 --width 256 --height 256 \
  --output data/output/satellite_ai_evaluation/satellite/sentinel5p_aer_ai_20240619T120518Z_full_orbit.tif \
  --dry-run
```

The dry runs write a `.request.json` beside each requested output. Check that
the NO₂ request contains `band: NO2` and `minQa: 75`, while the secondary
Aerosol Index request contains `band: AER_AI_340_380` and `minQa: 0`. Both
requests must contain:

- bbox `12.00 39.00 16.50 43.00`;
- time range `2024-06-19T11:34:07Z`–`2024-06-19T13:15:37Z`;
- output size `256×256`.

With `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET` exported, remove `--dry-run` to
download the GeoTIFF:

```bash
# Primary NO2 column product
python tools/copernicus-s5p-download.py \
  --bbox 12.00 39.00 16.50 43.00 \
  --time-start 2024-06-19T11:34:07Z \
  --time-end 2024-06-19T13:15:37Z \
  --band NO2 --min-qa 75 --width 256 --height 256 \
  --output data/output/satellite_ai_evaluation/satellite/sentinel5p_no2_20240619T120518Z_full_orbit.tif

# Secondary Aerosol Index footprint product
python tools/copernicus-s5p-download.py \
  --bbox 12.00 39.00 16.50 43.00 \
  --time-start 2024-06-19T11:34:07Z \
  --time-end 2024-06-19T13:15:37Z \
  --band AER_AI_340_380 --min-qa 0 --width 256 --height 256 \
  --output data/output/satellite_ai_evaluation/satellite/sentinel5p_aer_ai_20240619T120518Z_full_orbit.tif
```

The request JSON is retained beside the GeoTIFF for provenance. The downloader
already rejects all-empty rasters. You can still verify the finite Aerosol
Index pixel count manually before running the alignment step:

```bash
python - <<'PY'
from pathlib import Path
import numpy as np
import rasterio

path = Path("data/output/satellite_ai_evaluation/satellite/sentinel5p_aer_ai_20240619T120518Z_full_orbit.tif")
with rasterio.open(path) as dataset:
    values = dataset.read(1).astype(float)
    if dataset.nodata is not None:
        values[values == dataset.nodata] = np.nan
    finite = np.isfinite(values)
    print("shape:", values.shape)
    print("finite pixels:", int(finite.sum()))
    if finite.any():
        print("min/max:", float(np.nanmin(values)), float(np.nanmax(values)))
PY
```

If `finite pixels` is `0`, Sentinel Hub returned only `NaN`/`dataMask=0`
samples for the chosen bbox, time range, band, and QA filter. Do not continue
alignment with that file. Current downloader versions report this as a failed
download unless `--allow-empty` is supplied explicitly for negative provenance.
For audit purposes, the smaller domain-sized Aerosol Index request below is a
known negative diagnostic for this event. It may return HTTP 200 with zero
finite pixels. `--allow-empty` preserves that empty response and its request
metadata; the resulting TIFF must not be passed to alignment or evaluation:

```bash
python tools/copernicus-s5p-download.py \
  --bbox 13.97 40.83 14.70 41.17 \
  --time-start 2024-06-19T11:55:42Z \
  --time-end 2024-06-19T12:47:58Z \
  --band AER_AI_340_380 --min-qa 0 --width 32 --height 32 \
  --output data/output/satellite_ai_evaluation/satellite/sentinel5p_aer_ai_20240619T120518Z_domain_diagnostic.tif \
  --allow-empty
```

The regional request is also diagnostic and may be empty. Preserve it only as
negative provenance when needed:

```bash
python tools/copernicus-s5p-download.py \
  --bbox 13.50 40.40 15.00 41.50 \
  --time-start 2024-06-19T11:55:42Z \
  --time-end 2024-06-19T12:47:58Z \
  --band AER_AI_340_380 --min-qa 0 --width 64 --height 64 \
  --output data/output/satellite_ai_evaluation/satellite/sentinel5p_aer_ai_20240619T120518Z_wide.tif \
  --allow-empty
```

If both diagnostics fail but the full-orbit request succeeds, continue with the
full-orbit raster and let `step_03_align_satellite.py` crop it to the Spritz
domain. If the full-orbit request also fails, the shell pipeline stops. To
continue the didactic workflow deliberately with a non-satellite synthetic mask,
set:

```bash
export SPRTZ_ALLOW_SYNTHETIC_SATELLITE_FALLBACK=1
```

### 8. Downscale and align satellite data

```bash
python usecases/03_satellite_ai_evaluation/demo/step_03_align_satellite.py \
  --satellite data/output/satellite_ai_evaluation/satellite/sentinel5p_aer_ai_20240619T120518Z_full_orbit.tif \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --station-observations usecases/03_satellite_ai_evaluation/usecase_03_stations.csv \
  --dem data/output/satellite_ai_evaluation/dem/cop30_aversa.tif \
  --land-cover data/output/satellite_ai_evaluation/landcover/lc100_aversa.tif \
  --satellite-time 2024-06-19T12:05:18Z \
  --event-end 2024-06-19T13:00:00Z \
  --output data/output/satellite_ai_evaluation/satellite/sentinel5p_aer_ai_downscaled.json
```

The clean-room downscaler first crops the Sentinel raster to the approximate
Spritz concentration-field bbox derived from `config.json`, then treats every
remaining coarse satellite pixel as an areal constraint. GeoTIFF rows are
explicitly flipped from north-to-south storage into the south-to-north Spritz
grid orientation. It allocates each coarse pixel with bounded wind, bilinearly
resampled COP30 elevation and slope, and nearest-neighbor LC100 surface-roughness
weights, then uses the in-domain `ID,LAT,LON,NO2` stations to form a bounded
inverse-distance correction of the fine-grid allocation weights. Because NO₂
and Aerosol Index are different quantities, their 5th-to-95th-percentile
spatial anomalies are scaled independently; no physical unit conversion is
claimed. A final finite-aware low-pass blend removes inherited satellite-pixel
seams while preserving the domain mean; this deliberately relaxes exact
per-pixel conservation because projecting every coarse mean exactly recreates
visible footprint boundaries. It writes the full 351×601 field, a receptor
transect, the cropped source window, ancillary provenance, and coarse-mean
errors. This model-assisted allocation
does not imply that TROPOMI observed at Spritz resolution.

### 9. Plot the original and downscaled satellite images

```bash
MPLBACKEND=Agg python usecases/03_satellite_ai_evaluation/demo/step_04_plot_satellite.py \
  --satellite data/output/satellite_ai_evaluation/satellite/sentinel5p_aer_ai_20240619T120518Z_full_orbit.tif \
  --downscaled data/output/satellite_ai_evaluation/satellite/sentinel5p_aer_ai_downscaled.json \
  --gaussian data/output/satellite_ai_evaluation/model/gaussian/concentration.nc \
  --particles data/output/satellite_ai_evaluation/model/particles/concentration.nc \
  --model-time-index 1 \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --output data/output/satellite_ai_evaluation/figures/satellite_downscaling.png
```

The two panels use one shared robust Aerosol Index color scale, so colors are
directly comparable. Both panels mark the configured emission source with a
green star. A solid cyan outline comes from the Spritz Gaussian concentration
field and a dashed green outline comes from the Spritz particles field at the
selected time and vertical level. The default contour is `0.05` of each
backend's own maximum, making the outline a spatial-footprint comparison rather
than a claim that the two model concentrations have identical magnitudes. Use
`--plume-threshold`, `--model-time-index`, and `--model-level-index` to select
other documented slices and relative contours.

### 10. Evaluate primary NO₂ columns and secondary Aerosol Index patterns

Run the native-pixel column comparison for each backend before the normalized
Aerosol Index footprint evaluation:

```bash
python usecases/03_satellite_ai_evaluation/demo/step_05_evaluate_no2.py \
  --concentration data/output/satellite_ai_evaluation/model/gaussian/concentration.nc \
  --satellite-no2 data/output/satellite_ai_evaluation/satellite/sentinel5p_no2_20240619T120518Z_full_orbit.tif \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --time-index 1 \
  --output data/output/satellite_ai_evaluation/model/gaussian/no2_column_evaluation.json
```

This primary report contains raw mol m⁻² statistics and normalized spatial
pattern statistics. It explicitly records that the Sentinel Hub GeoTIFF does
not supply an averaging kernel and that Spritz currently models passive NO₂
without chemistry or a background column.

Run `scripts/sprtz_satellite_evaluate.py` separately for the Gaussian and
particle concentration files, using the freshly aligned
`sentinel5p_aer_ai_downscaled.json` as `--satellite-mask`. The evaluation uses
`--time-index 1`, selecting the 12:00 UTC model output, the closest hourly
state to the 12:05:18 UTC Sentinel-5P observation.

Gaussian backend:

```bash
python scripts/sprtz_satellite_evaluate.py \
  --concentration data/output/satellite_ai_evaluation/model/gaussian/concentration.nc \
  --satellite-mask data/output/satellite_ai_evaluation/satellite/sentinel5p_aer_ai_downscaled.json \
  --output data/output/satellite_ai_evaluation/model/gaussian/evaluation.json \
  --threshold 0.5 \
  --time-index 1 \
  --boundary-threshold-absolute 1e-15 \
  --boundary-threshold-relative 1e-12 \
  --boundary-mass-fraction-threshold 1e-6 \
  --model-unit ug_m3 \
  --satellite-unit normalized_aerosol_index \
  --target-unit normalized_probability \
  --station-observations usecases/03_satellite_ai_evaluation/usecase_03_stations.csv
```

Particle backend:

```bash
python scripts/sprtz_satellite_evaluate.py \
  --concentration data/output/satellite_ai_evaluation/model/particles/concentration.nc \
  --satellite-mask data/output/satellite_ai_evaluation/satellite/sentinel5p_aer_ai_downscaled.json \
  --output data/output/satellite_ai_evaluation/model/particles/evaluation.json \
  --threshold 0.5 \
  --time-index 1 \
  --boundary-threshold-absolute 1e-15 \
  --boundary-threshold-relative 1e-12 \
  --boundary-mass-fraction-threshold 1e-6 \
  --model-unit ug_m3 \
  --satellite-unit normalized_aerosol_index \
  --target-unit normalized_probability \
  --station-observations usecases/03_satellite_ai_evaluation/usecase_03_stations.csv
```

Each evaluation JSON records the satellite provenance, normalized model-to-mask
skill scores, AI-style deterministic calibration, and threshold-aware field
boundary diagnostics. The station CSV adds a colocated station-validation block:
stations inside the Spritz domain are mapped onto the 351×601 model/satellite
grid, their NO₂ values are normalized as an independent spatial-pattern
diagnostic, and the evaluator reports model-vs-station,
satellite-vs-station, and model-vs-satellite-at-station statistics. NO₂ is not
converted to Aerosol Index or Spritz concentration; this is a pattern check,
not a unit-equivalent validation. The evaluator also writes backend-specific
difference, ratio, and statistics sidecar artifacts beside `evaluation.json`.

Then plot each NetCDF file with `scripts/sprtz_plot.py`. The shell pipeline
contains the compact plotting commands and output paths.

### 11. Advanced plotting, profiling, and 3-D rendering

The shell pipeline writes compact concentration plots through
`scripts/sprtz_plot.py`. For publication-style diagnostics, use the shared
visualization tools directly. They require the optional visualization stack:

```bash
python -m pip install -e '.[netcdf,viz]'
```

Use `MPLBACKEND=Agg` for batch/HPC runs without a display. The examples below
render the particle backend; replace `particles` with `gaussian` to produce the
same figures for the Gaussian backend.

#### 10.1 Render a concentration map with `tools/plotter.py`

```bash
MPLBACKEND=Agg python tools/plotter.py \
  data/output/satellite_ai_evaluation/model/particles/concentration.nc \
  --variable concentration_field \
  --time-index 1 \
  --level-index 0 \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --title "Aversa particle concentration at 12:00 UTC, 400 m ASL" \
  --log-scale \
  --dpi 300 \
  --output data/output/satellite_ai_evaluation/figures/particles_concentration_1200_map.png
```

`--time-index 1` selects the 12:00 UTC model output, the closest hourly state
to the Sentinel-5P 12:05:18 UTC observation. `--level-index 0` selects the
single configured concentration-field level, `field_z=400 m ASL`.

To animate every output time with one shared color scale:

```bash
MPLBACKEND=Agg python tools/plotter.py \
  data/output/satellite_ai_evaluation/model/particles/concentration.nc \
  --variable concentration_field \
  --level-index 0 \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --animate \
  --frame-duration-ms 450 \
  --gif-loop 0 \
  --log-scale \
  --output data/output/satellite_ai_evaluation/figures/particles_concentration_animation.gif
```

#### 10.2 Render a vertical profile with `tools/plotter.py profile`

`tools/plotter.py profile` samples one local grid column through time. The example
below samples the Aversa source column (`x=0`, `y=0`):

```bash
MPLBACKEND=Agg python tools/plotter.py profile \
  data/output/satellite_ai_evaluation/model/particles/concentration.nc \
  --variable concentration_field \
  --x 0 --y 0 \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --title "Aversa particle concentration profile at the source column" \
  --dpi 300 \
  --output data/output/satellite_ai_evaluation/figures/particles_concentration_profile_source.png
```

To profile a downwind column near the 13:00 particle peak, use `x=12700`,
`y=4600`:

```bash
MPLBACKEND=Agg python tools/plotter.py profile \
  data/output/satellite_ai_evaluation/model/particles/concentration.nc \
  --variable concentration_field \
  --x 12700 --y 4600 \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --title "Aversa particle concentration profile near the downwind peak" \
  --dpi 300 \
  --output data/output/satellite_ai_evaluation/figures/particles_concentration_profile_downwind.png
```

To animate all profile times:

```bash
MPLBACKEND=Agg python tools/plotter.py profile \
  data/output/satellite_ai_evaluation/model/particles/concentration.nc \
  --variable concentration_field \
  --x 12700 --y 4600 \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --animate \
  --frame-duration-ms 450 \
  --gif-loop 0 \
  --output data/output/satellite_ai_evaluation/figures/particles_concentration_profile_animation.gif
```

#### 10.3 Render 3-D views with `tools/plotter.py render3d`

This use case writes one concentration field level at 400 m ASL. `tools/plotter.py render3d`
still provides useful terrain-aware 3-D context by rendering the gridded plume
above `geo.nc` and overlaying the configured source location.

```bash
MPLBACKEND=Agg python tools/plotter.py render3d \
  data/output/satellite_ai_evaluation/model/particles/concentration.nc \
  --variable concentration_field \
  --time-index 1 \
  --terrain data/output/satellite_ai_evaluation/geo.nc \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --mode surface \
  --ground-color terrain \
  --view northeast \
  --threshold-quantile 0.85 \
  --vertical-exaggeration 5 \
  --log-scale \
  --output data/output/satellite_ai_evaluation/figures/particles_concentration_1200_3d_surface.png
```

For a sparse voxel-style rendering:

```bash
MPLBACKEND=Agg python tools/plotter.py render3d \
  data/output/satellite_ai_evaluation/model/particles/concentration.nc \
  --variable concentration_field \
  --time-index 1 \
  --terrain data/output/satellite_ai_evaluation/geo.nc \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --mode voxel \
  --ground-color land-cover \
  --view northeast \
  --threshold-quantile 0.90 \
  --vertical-exaggeration 5 \
  --log-scale \
  --output data/output/satellite_ai_evaluation/figures/particles_concentration_1200_3d_voxels.png
```

To animate 3-D frames across all three output times:

```bash
MPLBACKEND=Agg python tools/plotter.py render3d \
  data/output/satellite_ai_evaluation/model/particles/concentration.nc \
  --variable concentration_field \
  --terrain data/output/satellite_ai_evaluation/geo.nc \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --mode voxel \
  --ground-color terrain \
  --view northeast \
  --threshold-quantile 0.85 \
  --vertical-exaggeration 5 \
  --animate \
  --frame-duration-ms 450 \
  --gif-loop 0 \
  --output data/output/satellite_ai_evaluation/figures/particles_concentration_3d_animation.gif
```

## Outputs

Each backend directory contains concentration NetCDF, evaluation JSON,
difference and ratio JSON grids, and a statistics CSV. For NetCDF
concentration fields, the evaluation JSON also contains threshold-aware
`field_boundary_diagnostics` with timestep peaks, active-cell margins, raw edge
activity, edge mass fractions, and meaningful boundary contact after the
numerical-noise and mass-fraction floors are applied. `figures/` contains
Gaussian and particle concentration plots, and may also contain publication
maps, vertical-profile figures, and 3-D renders generated with `tools/plotter.py`,
`tools/plotter.py profile`, and `tools/plotter.py render3d`. Satellite provenance includes the
Process API request, acquisition time, event-end time, sampling method, and
valid-sample count, weighting rule, smoothing count, and conservation errors.

## Assumptions and limitations

- The event source strength and material representation are screening
  assumptions, not measured emissions.
- The WRF archive may no longer retain the requested historical cycles.
- Copernicus download requires user-managed credentials and service quota.
- Aerosol Index and modeled near-surface concentration are not directly
  commensurate; evaluation uses normalized spatial patterns.
- Temporal overlap improves comparability but cannot by itself establish event
  attribution.
- Exact receptor/sample alignment is required; index resampling is disabled in
  the canonical workflow.

## References

Veefkind, J. P., Aben, I., McMullan, K., Förster, H., de Vries, J., Otter, G.,
Claes, J., Eskes, H. J., de Haan, J. F., Kleipool, Q., van Weele, M.,
Hasekamp, O., Hoogeveen, R., Landgraf, J., Snel, R., Tol, P., Ingmann, P.,
Voors, R., Kruizinga, B., Vink, R., Visser, H., & Levelt, P. F. (2012).
TROPOMI on the ESA Sentinel-5 Precursor: A GMES mission for global observations
of the atmospheric composition for climate, air quality and ozone layer
applications. *Remote Sensing of Environment, 120*, 70–83.
