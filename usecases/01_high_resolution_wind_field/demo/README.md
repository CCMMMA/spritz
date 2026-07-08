# Bay of Naples, Velalonga 2026

This demo produces a 24-hour, 100 m-resolution wind field for the Bay of
Naples during Velalonga 2026. The simulation starts at `20260621Z0000` and
covers the following domain:

```json
[
  [14.18, 40.78],
  [14.18, 40.85],
  [14.33, 40.85],
  [14.33, 40.78],
  [14.18, 40.78]
]
```

All commands are run from the repository root. Inputs and generated products
remain under the repository-level `data/` directory.

## Scientific scope

The workflow routes hourly WRF5 d03 data through SpritzWRF and SpritzMet:

1. SpritzWRF downloads and reads the 24 hourly WRF files from
   `20260621Z0000` through `20260621Z2300`.
2. SpritzMet performs deterministic terrain-aware downscaling on a local 100 m
   grid that conservatively covers the Velalonga bounding box.
3. SpritzMet writes the accumulated NetCDF-CF output after every completed
   hourly frame. If a later frame fails, the output still contains the
   successfully completed frames.
4. Separate visualization tools render maps, profiles, and 3-D products after
   the numerical computation.

The workflow is a clean-room didactic implementation. It is not presented as a
regulatory-equivalent forecast or an official Velalonga weather product.

## Environment

Python 3.10 or newer is required. Install the NetCDF, geospatial, and
visualization extras:

```bash
python -m pip install -e '.[dev,netcdf,geo,viz]'
```

MPI remains optional. Install `sprtz[mpi]` only when running with an MPI
launcher.

## 1. Download the 24 hourly WRF files

The downscaling command can download missing files automatically. To prepare
them explicitly:

```bash
python tools/meteouniparthenope-wrf-download.py 20260621Z0000 \
  --hours 24 \
  --domain d03 \
  --data-root data/wrf/d03
```

The downloader uses the meteo@uniparthenope history convention:

```text
https://data.meteo.uniparthenope.it/files/wrf5/d03/history/YYYY/MM/DD/wrf5_d03_YYYYMMDDZhh00.nc
```

WRF valid times are read from WRF/CF metadata. Sprtz does not infer scientific
times from filenames.

## 2. Prepare terrain and land cover

Download buffered COP30 elevation and Copernicus LC100 land cover for the same
domain:

```bash
python tools/copernicus-cop30-dem-download.py \
  --south 40.78 --north 40.85 --west 14.18 --east 14.33 \
  --dx 100 \
  --dy 100 \
  --buffer-m 5000 \
  --output data/output/high_resolution_wind_field/dem/cop30_naples.tif

python tools/copernicus-lc100-download.py \
  --south 40.78 --north 40.85 --west 14.18 --east 14.33 \
  --dx 100 \
  --dy 100 \
  --buffer-m 5000 \
  --output data/output/high_resolution_wind_field/landcover/lc100_naples.tif
```

The bounding-box downscaler determines its exact node count from the projected
corners. The buffered rasters need to cover that resulting grid; the node
counts above are acquisition extents, not a replacement for the bounding-box
request. Because `--center-lat` and `--center-lon` are omitted, both downloaders
derive the grid center from the geographic bounding-box midpoint:
`(40.815, 14.255)`. They then calculate the projected 129 by 79 grid footprint
and expand its source AOI by `--buffer-m 5000`.

Build the matching terrain/GEO product used by 3-D rendering:

```bash
sprtz-terrain fetch \
  --south 40.78 --north 40.85 --west 14.18 --east 14.33 \
  --dx 100 \
  --dy 100 \
  --dem data/output/high_resolution_wind_field/dem/cop30_naples.tif \
  --landuse data/output/high_resolution_wind_field/landcover/lc100_naples.tif \
  --landuse-mapping copernicus-lc100 \
  --cache-dir data/output/high_resolution_wind_field/terrain-cache \
  --output data/output/high_resolution_wind_field/geo.nc
```

DEM elevation constrains the wind profile and masks above-sea-level model
levels below terrain. LC100 classes provide bounded surface-roughness and
precipitation adjustments. Diagnostic `U10M` and `V10M` remain wind at 10 m
above local ground. In bounding-box mode, `sprtz-terrain fetch` derives the
same snapped `129 x 79` grid automatically from the bbox midpoint and the
`100 m` spacing, so `--nx` and `--ny` can be omitted here.

## 3. Compute the Velalonga wind field

This command performs computation only; it does not plot:

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

The principal output is:

```text
data/output/high_resolution_wind_field/wrf_100m_wind_bbox.nc
```

It contains the CF time coordinate and, when supplied by WRF, the following
fields:

- `eastward_wind(time,z,y,x)` and `northward_wind(time,z,y,x)`;
- `wind_speed(time,z,y,x)` and `wind_from_direction(time,z,y,x)`;
- diagnostic `U10M(time,y,x)`, `V10M(time,y,x)`,
  `wind_speed_10m(time,y,x)`, and
  `wind_from_direction_10m(time,y,x)`;
- `precipitation_rate(time,y,x)`;
- optional 2 m temperature and relative humidity.

The configured vertical levels are altitudes above mean sea level. The 10 m
diagnostic fields are instead referenced to local ground and must not be
interpreted as wind at 10 m above sea level over land.

## 4. Render the six Velalonga 10 m maps

The requested UTC frames correspond to time indexes 9 through 14:

| UTC valid time | Time index |
|---|---:|
| `20260621Z0900` | 9 |
| `20260621Z1000` | 10 |
| `20260621Z1100` | 11 |
| `20260621Z1200` | 12 |
| `20260621Z1300` | 13 |
| `20260621Z1400` | 14 |

Render shaded 10 m wind speed with automatic `U10M`/`V10M` vector overlays:

```bash
for hour in 09 10 11 12 13 14; do
  index=$((10#$hour))
  python tools/plotter.py \
    data/output/high_resolution_wind_field/wrf_100m_wind_bbox.nc \
    --variable wind_speed_10m \
    --time-index "$index" \
    --vector-density 50 \
    --coastline-source gshhs \
    --coastline-resolution 10m \
    --allow-cartopy-download \
    --title "Velalonga 2026 — 20260621Z${hour}00 — wind at 10 m AGL" \
    --output "data/output/high_resolution_wind_field/velalonga_wind_10m_20260621Z${hour}00.png"
done
```

GSHHS `full` (`10m`) is the finest coastline supported by the plotter.
`--allow-cartopy-download` permits retrieval when it is not already installed;
if GSHHS is unavailable, the plotter reports its Natural Earth fallback. Wind
speed uses the Sprtz discrete knots palette and arrows show direction. When the
NetCDF contains both longitude/latitude and local `x/y`, the map uses
geographic primary axes plus local-metre secondary axes; after the plotter fix,
the displayed `x=0` and `y=0` references align with the true centered model
grid rather than drifting on Cartopy geographic figures.

## 5. Render the vertical-profile animation

Render the time-varying vertical wind-speed profile at the local grid center
(`x=0`, `y=0`):

```bash
python tools/profiler.py \
  data/output/high_resolution_wind_field/wrf_100m_wind_bbox.nc \
  --variable wind_speed \
  --x 0 \
  --y 0 \
  --animate \
  --frame-duration-ms 400 \
  --gif-loop 0 \
  --title "Velalonga 2026 — central Bay of Naples vertical wind profile" \
  --output data/output/high_resolution_wind_field/velalonga_vertical_profile.gif
```

The profile uses all 24 frames and all configured vertical levels. Values below
the local DEM are masked. Wind speed uses the same discrete knots palette as
the 2-D maps. The GIF options match `tools/render3d.py`: `--animate`,
`--frame-duration-ms`, `--gif-loop`, and a `.gif` output path.

## 6. Render the terrain-aware 3-D animation

Render all 24 wind-speed volumes over the GEO terrain with a vertical display
exaggeration of five:

```bash
python tools/render3d.py \
  data/output/high_resolution_wind_field/wrf_100m_wind_bbox.nc \
  --variable wind_speed \
  --terrain data/output/high_resolution_wind_field/geo.nc \
  --mode surface \
  --ground-color terrain \
  --vertical-exaggeration 5 \
  --animate \
  --frame-duration-ms 400 \
  --gif-loop 0 \
  --title "Velalonga 2026 — 3-D wind speed, terrain ×5" \
  --output data/output/high_resolution_wind_field/velalonga_wind_3d_terrain_x5.gif
```

The factor of five affects display geometry only. It does not alter terrain
elevation or wind-level values in the NetCDF file. Every frame title includes
its NetCDF time reference, and wind speed uses the same discrete knots palette
as the 2-D maps.

## 7. Render the 3-D vector field

Render the horizontal wind vectors at every sampled model height for
`20260621Z1200`. Arrow direction comes from
`eastward_wind(time,z,y,x)` and `northward_wind(time,z,y,x)`; arrow color
shows wind speed:

```bash
python tools/render3d.py \
  data/output/high_resolution_wind_field/wrf_100m_wind_bbox.nc \
  --variable wind_speed \
  --time-index 12 \
  --terrain data/output/high_resolution_wind_field/geo.nc \
  --mode quiver \
  --max-points 18 \
  --ground-color terrain \
  --vertical-exaggeration 5 \
  --title "Velalonga 2026 — 3-D wind vectors — 20260621Z1200" \
  --output data/output/high_resolution_wind_field/velalonga_wind_vectors_3d_20260621Z1200.png
```

The arrows are horizontal because SpritzMet currently provides eastward and
northward wind components, not vertical velocity. Model levels below the DEM
are omitted. `--max-points 18` limits horizontal and vertical arrow density so
the field remains legible. The title includes the selected NetCDF time
reference and arrow colors use the same wind-speed palette as the 2-D maps.

## 8. Render 10 m wind speed as voxels

`wind_speed_10m` has dimensions `time,y,x`, whereas voxel rendering requires a
vertical dimension. Therefore the scientifically meaningful voxel product uses
the full `wind_speed(time,z,y,x)` volume and selects occupied cells with the
renderer threshold:

```bash
python tools/render3d.py \
  data/output/high_resolution_wind_field/wrf_100m_wind_bbox.nc \
  --variable wind_speed \
  --time-index 12 \
  --terrain data/output/high_resolution_wind_field/geo.nc \
  --mode voxel \
  --threshold-quantile 0.85 \
  --ground-color terrain \
  --vertical-exaggeration 5 \
  --title "Velalonga 2026 — wind-speed voxels — 20260621Z1200" \
  --output data/output/high_resolution_wind_field/velalonga_wind_voxels_20260621Z1200.png
```

A literal `wind_speed_10m` voxel volume would repeat a two-dimensional
diagnostic field through artificial vertical cells and is intentionally not
claimed here. Use the 2-D maps for the actual 10 m-above-ground diagnostic.

## Expected products

- `wrf_100m_wind_bbox.nc` — 24-frame SpritzMet NetCDF-CF product;
- six `velalonga_wind_10m_*.png` maps for `Z0900` through `Z1400`;
- `velalonga_vertical_profile.gif`;
- `velalonga_wind_3d_terrain_x5.gif`;
- `velalonga_wind_vectors_3d_20260621Z1200.png`;
- `velalonga_wind_voxels_20260621Z1200.png`;
- `geo.nc` and its terrain cache.

## Assumptions and limitations

- The WRF input and derived fields are model results, not observations.
- The 100 m grid is a downscaled diagnostic product; it does not add resolved
  atmospheric information equivalent to running a native 100 m dynamical
  model.
- Terrain vertical exaggeration is visualization-only.
- Station residual observations are not used in this fixed demo.
- Online downloads require explicit network access and the optional
  geospatial dependencies.
- Cartographic coastlines may require a locally available Cartopy dataset.
- No claim of regulatory or operational forecast equivalence is made.

## Production checklist

- Confirm all 24 WRF files contain valid CF/WRF timestamps.
- Audit DEM and LC100 provenance and coverage.
- Inspect the NetCDF `time`, `z`, units, and SpritzMet metadata.
- Check every hourly frame for missing or masked values.
- Compare modeled wind with geographically distributed observations.
- Record software version, configuration, input checksums, and retrieval dates.
- Validate MPI and serial equivalence when MPI is used.

## References

No external bibliographic references are required for this procedural demo.
