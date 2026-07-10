# High-Resolution Wind Field Pipeline

## Scientific purpose

This pipeline now follows the same real-data Velalonga 2026 workflow as
`usecases/01_high_resolution_wind_field/demo/`. It downloads 24 hourly WRF d03
files for `20260621Z0000`, prepares buffered COP30 and LC100 rasters for the
Bay of Naples bounding box, builds the matching GEO terrain product, runs the
SpritzWRF -> SpritzMet downscaling chain, and renders the same 2-D, profile,
and 3-D products.

The pipeline remains a shell-oriented operational wrapper, but it is no longer
the old synthetic single-station SpritzMet smoke path. It is aligned with the
didactic demo and uses the same clean-room scientific assumptions, NetCDF-CF
outputs, and visualization conventions.

## Operational contract

Run from the repository root, or from any other working directory:

```bash
bash usecases/01_high_resolution_wind_field/pipeline/pipeline.sh
```

The script resolves the repository root from its own location and writes under
the repository-level `data/` tree by default:

- WRF downloads go to `data/wrf/d03/`;
- terrain and wind-field products go to `data/output/high_resolution_wind_field/`.

Override paths with:

- `SPRTZ_DATA_ROOT` to relocate the repository data root;
- `SPRTZ_OUTPUT_DIR` to choose the exact output directory for terrain, NetCDF,
  and rendered products;
- `WRF_DIR`, `DEM_PATH`, `LANDUSE_PATH`, `GEO_PATH`, and `METEO_PATH` for
  finer-grained path control.

The script also sets `MPLCONFIGDIR` and `XDG_CACHE_HOME` under
`${SPRTZ_OUTPUT_DIR}` by default so Matplotlib and font caches remain
workflow-writable.

## Fixed scenario

The aligned pipeline is intentionally pinned to the Velalonga 2026 scenario:

- start time: `20260621Z0000`;
- duration: `24` hours;
- bounding box:

```json
[
  [14.18, 40.78],
  [14.18, 40.85],
  [14.33, 40.85],
  [14.33, 40.78],
  [14.18, 40.78]
]
```

- local spacing: `100 m`;
- terrain buffer for source rasters: `5000 m`.

By default, the pipeline omits `--nx` and `--ny` for the Copernicus downloaders
and for `sprtz-terrain fetch`. They are derived automatically from the bbox
midpoint and spacing, yielding the same snapped `129 x 79` grid used by the
demo.

## Parameters

The main environment overrides are:

- `DATE_UTC`, default `20260621Z0000`;
- `HOURS`, default `24`;
- `SOUTH`, `NORTH`, `WEST`, `EAST`, defaulting to the Velalonga bbox;
- `DX`, `DY`, default `100`;
- `BUFFER_M`, default `5000`;
- `VECTOR_DENSITY`, default `50` for 2-D wind maps;
- `PROFILE_DURATION_MS`, default `400`;
- `RENDER3D_DURATION_MS`, default `400`;
- `VERTICAL_EXAGGERATION`, default `5`;
- `COASTLINE_SOURCE`, default `gshhs`;
- `COASTLINE_RESOLUTION`, default `10m`;
- `ALLOW_CARTOPY_DOWNLOAD`, default `1`.

All parameters may be overridden as shell environment variables.

## Step-by-step method

### Step 1: Download the WRF forcing

The pipeline downloads the 24 hourly WRF5 d03 files from `20260621Z0000`
through `20260621Z2300`:

```bash
python tools/meteouniparthenope-wrf-download.py 20260621Z0000 \
  --hours 24 \
  --domain d03 \
  --data-root data/wrf/d03
```

WRF valid times are read from WRF or CF metadata, not inferred from filenames.

### Step 2: Download buffered DEM and land cover

The pipeline downloads:

- buffered COP30 terrain with `tools/copernicus-cop30-dem-download.py`;
- buffered Copernicus LC100 land cover with `tools/copernicus-lc100-download.py`.

Both commands use bbox plus `--dx/--dy/--buffer-m`, letting the tools derive
the centered snapped grid automatically.

### Step 3: Build the matching GEO terrain product

The script calls:

```bash
sprtz-terrain fetch \
  --south 40.78 --north 40.85 --west 14.18 --east 14.33 \
  --dx 100 \
  --dy 100 \
  --dem .../cop30_naples.tif \
  --landuse .../lc100_naples.tif \
  --landuse-mapping copernicus-lc100 \
  --cache-dir .../terrain-cache \
  --output .../geo.nc
```

This keeps the terrain product aligned with the downscaling grid and the 3-D
rendering inputs.

### Step 4: Run SpritzWRF -> SpritzMet downscaling

The meteorological computation is delegated to the same demo driver used by the
didactic workflow:

```bash
python usecases/01_high_resolution_wind_field/demo/step_01_downscale_wind.py \
  --date 20260621Z0000 \
  --hours 24 \
  --download-dir data/wrf/d03/ \
  --output data/output/high_resolution_wind_field/wrf_100m_wind_bbox.nc \
  --south 40.78 --north 40.85 --west 14.18 --east 14.33 \
  --dx 100 --dy 100 \
  --config usecases/01_high_resolution_wind_field/demo/config.json \
  --dem data/output/high_resolution_wind_field/dem/cop30_naples.tif \
  --land-cover data/output/high_resolution_wind_field/landcover/lc100_naples.tif \
  --parallel auto
```

SpritzMet writes the accumulated NetCDF-CF output after each completed time
frame, so a partial scientific product remains available if a later frame
fails.

### Step 5: Render the same products as the demo

The aligned pipeline renders:

- six 10 m wind maps for `Z0900` through `Z1400`;
- one animated center-column vertical profile GIF;
- one animated terrain-aware 3-D wind-speed GIF;
- one 3-D quiver frame for `20260621Z1200`;
- one voxel frame for `20260621Z1200`.

The 2-D maps use:

- `tools/plotter.py`;
- GSHHS `10m` coastlines by default;
- the Sprtz discrete knots palette for wind speed;
- automatic `U10M` / `V10M` vector overlays;
- corrected local-metre secondary axes, so displayed `x=0` and `y=0` align
  with the true domain center on Cartopy geographic plots.

The profile and 3-D animations use the same GIF-style interface as the demo:

- `--animate`;
- `--frame-duration-ms`;
- `--gif-loop`;
- a `.gif` output path.

## Expected products

The pipeline writes the same major artifacts as the aligned demo:

- `wrf_100m_wind_bbox.nc` — 24-frame SpritzMet NetCDF-CF product;
- `geo.nc` and `terrain-cache/`;
- `dem/cop30_naples.tif`;
- `landcover/lc100_naples.tif`;
- six `velalonga_wind_10m_20260621Z*.png` maps for `Z0900` through `Z1400`;
- `velalonga_vertical_profile.gif`;
- `velalonga_wind_3d_terrain_x5.gif`;
- `velalonga_wind_vectors_3d_20260621Z1200.png`;
- `velalonga_wind_voxels_20260621Z1200.png`.

## Reproducibility and limitations

- The workflow is driven by WRF model data, not direct observations.
- The 100 m product is a terrain-aware deterministic downscaling diagnostic, not
  a native 100 m atmospheric model integration.
- `U10M` and `V10M` remain wind at 10 m above local ground, not 10 m above sea
  level over generic terrain.
- Terrain vertical exaggeration in 3-D views is visualization-only.
- The pipeline requires explicit network access for WRF, COP30, LC100, and any
  missing Cartopy coastline downloads.
- No claim of regulatory equivalence or official operational forecast status is
  made.

## Relationship to the demo

`pipeline.sh` is now the shell-first operational wrapper of the same scenario
documented in `usecases/01_high_resolution_wind_field/demo/README.md`. The
demo remains the canonical narrative explanation, while the pipeline provides a
repeatable end-to-end command chain suitable for workflow engines and batch
execution.
