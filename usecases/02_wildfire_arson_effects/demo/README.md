# Use case 02 — Arson or wildfire effects

Goal: create a reproducible screening simulation for an arson/wildfire event at a known latitude and longitude, using WRF 1 km meteorology as wind forcing.

The workflow is intentionally step-by-step:

1. **Choose the event location.** Provide the burning latitude and longitude through `--center-lat` and `--center-lon`.
2. **Acquire meteorology.** Use a local WRF file or download WRF5 d03 from meteo@uniparthenope.
3. **Downscale wind.** Reuse use case 01 logic: SpritzWRF extracts WRF wind and
   SpritzMet downscales it to 100 m. The documented command opts into the
   advanced horizontal wind-consistency operators.
4. **Build source terms.** Convert burning material, optional burning temperature, duration, source height, and area into a documented screening heat-release and PM emission estimate.
5. **Generate receptors.** Create a circular receptor set around the fire location.
6. **Run dispersion.** Execute both the particle and Gaussian backends against
   the same high-resolution SpritzMet meteorology, or select one backend for a
   shorter diagnostic run.
7. **Review outputs.** Inspect time-dependent gridded concentration fields,
   postprocessing summaries, backend-comparison metrics, horizontal maps, and
   time-varying vertical wind-profile plots.

NetCDF/time convention: WRF valid time is read only by SpritzWRF from WRF/CF
metadata (`Times`, CF `time`, or explicit global time attributes). The workflow
does not infer datetimes from WRF filenames; NetCDF meteorology and dispersion
products follow strict CF time coordinates.

Meteorology convention: Step 1 writes SpritzMet wind as
`eastward_wind(time,z,y,x)` and `northward_wind(time,z,y,x)`, with the `z`
coordinate in metres and a SpritzMet metadata attribute describing whether the
levels are height above local ground or height above mean sea level. Step 3
reuses this prepared file instead of rebuilding a one-time diagnostic
meteorology grid. When `U10M`/`V10M` diagnostic wind is available and the first
physical `z` level is above the surface, the Gaussian and particle samplers use
that diagnostic 10 m above-ground wind as the lower-boundary layer for
near-ground plume transport.

## MPI execution on a SLURM cluster

Install `mpi4py` against the cluster's MPI module and pre-stage the WRF, DEM,
and LC100 inputs on shared storage. Before submission, run Step 2 below once on
the login node to create
`data/output/wildfire_case/wildfire_event.json`; do not have multiple MPI ranks
create or modify the shared configuration concurrently.

```bash
module load python
module load openmpi
source .venv/bin/activate
python -m pip install -e '.[netcdf,geo,mpi]'
python -m sprtz doctor
```

Save the following as `usecase02_mpi.slurm` in the repository root. Module and
partition names are site-specific.

```bash
#!/bin/bash
#SBATCH --job-name=sprtz-uc02
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --time=06:00:00
#SBATCH --partition=compute
#SBATCH --output=data/output/wildfire_case/slurm-%j.out
#SBATCH --error=data/output/wildfire_case/slurm-%j.err

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
module load python
module load openmpi
source .venv/bin/activate

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

OUT=data/output/wildfire_case
METEO="${OUT}/wrf_100m_wind_mpi.nc"
CONFIG="${OUT}/wildfire_event.json"
mkdir -p "${OUT}/model_compare/particles" "${OUT}/model_compare/gaussian"

srun --ntasks="${SLURM_NTASKS}" \
  python usecases/02_wildfire_arson_effects/demo/step_01_downscale_wind.py \
    --date 20240731Z1000 --hours 24 \
    --download-dir data/wrf/d03 \
    --output "${METEO}" \
    --center-lat 40.827 --center-lon 14.518 \
    --nx 201 --ny 201 --dx 100 --dy 100 \
    --dem "${OUT}/dem/cop30_wildfire_case.tif" \
    --land-cover "${OUT}/landcover/lc100_wildfire_case.tif" \
    --advanced-physics --bulk-richardson-number 0.0 \
    --mass-consistency-iterations 80 \
    --mass-consistency-relaxation 0.8 \
    --parallel mpi --decomposition rows --thread-backend serial

srun --ntasks="${SLURM_NTASKS}" \
  spritz --config "${CONFIG}" --meteo "${METEO}" \
    --output "${OUT}/model_compare/particles/concentration.nc" \
    --format netcdf --backend particles --parallel mpi \
    --decomposition particles --thread-backend serial \
    --output-interval 3600

srun --ntasks="${SLURM_NTASKS}" \
  spritz --config "${CONFIG}" --meteo "${METEO}" \
    --output "${OUT}/model_compare/gaussian/concentration.nc" \
    --format netcdf --backend gaussian --parallel mpi \
    --decomposition receptors --thread-backend serial \
    --output-interval 3600
```

Create the log directory before submission, then submit and monitor the job:

```bash
mkdir -p data/output/wildfire_case
sbatch usecase02_mpi.slurm
squeue -u "${USER}"
```

Only rank 0 writes each shared NetCDF product. Particle work and Gaussian
receptors are partitioned deterministically; allocating more ranks than useful
particle/source or receptor work adds overhead. Compare both MPI outputs with
otherwise identical `--parallel serial` runs before scientific use. Increase
`--nodes` and `--ntasks` for a multi-node run, retaining `srun` and explicit
`--parallel mpi` so MPI setup failures cannot silently fall back to serial.

## Data preparation

Prepare WRF forcing before the run:

```bash
tools/meteouniparthenope-wrf-download.py 20240731Z1000 \
  --hours 24 \
  --domain d03 \
  --data-root data/wrf/d03
```

Prepare the optional COP30 terrain source for ground elevation and terrain/GEO
products:

```bash
python3 tools/copernicus-cop30-dem-download.py \
  --center-lat 40.827 \
  --center-lon 14.518 \
  --nx 201 \
  --ny 201 \
  --dx 100 \
  --dy 100 \
  --buffer-m 5000 \
  --output data/output/wildfire_case/dem/cop30_wildfire_case.tif

python3 tools/copernicus-lc100-download.py \
  --center-lat 40.827 \
  --center-lon 14.518 \
  --nx 201 \
  --ny 201 \
  --dx 100 \
  --dy 100 \
  --buffer-m 5000 \
  --output data/output/wildfire_case/landcover/lc100_wildfire_case.tif
```

On HPC systems with a shared outbound IP, cache the 1.7 GB global LC100 source
once to avoid exhausting Zenodo's per-IP limit with GDAL range requests:

```bash
mkdir -p data/cache/copernicus-lc100
curl -fL --retry 10 --continue-at - \
  --output data/cache/copernicus-lc100/PROBAV_LC100_2019_discrete.tif \
  "https://zenodo.org/api/records/3939050/files/PROBAV_LC100_global_v3.0.1_2019-nrt_Discrete-Classification-map_EPSG-4326.tif/content"

python3 tools/copernicus-lc100-download.py \
  --center-lat 40.827 --center-lon 14.518 \
  --nx 201 --ny 201 --dx 100 --dy 100 --buffer-m 5000 \
  --source-url data/cache/copernicus-lc100/PROBAV_LC100_2019_discrete.tif \
  --output data/output/wildfire_case/landcover/lc100_wildfire_case.tif
```

The download is resumable and reusable by other use cases. Keep the global
raster out of Git and release archives.

These commands compute the WGS84 download bounds from the exact `201 x 201`,
`100 m` terrain domain and add a `5000 m` source-raster buffer. The buffer keeps
bilinear DEM sampling away from the source raster edge and gives nearest-neighbor
land-cover sampling full coverage for the standalone `geo.nc` product.

Use the downloaded DEM and LC100 land-cover rasters through `sprtz-terrain
fetch` with the same domain settings used by the wildfire run. The wind
downscaling step can also read the same rasters directly with `--dem` and
`--land-cover` so SpritzMet adjusts both wind and precipitation on the local
grid.

```bash
sprtz-terrain fetch \
  --center-lat 40.827 \
  --center-lon 14.518 \
  --nx 201 \
  --ny 201 \
  --dx 100 \
  --dy 100 \
  --dem data/output/wildfire_case/dem/cop30_wildfire_case.tif \
  --landuse data/output/wildfire_case/landcover/lc100_wildfire_case.tif \
  --landuse-mapping copernicus-lc100 \
  --cache-dir data/output/wildfire_case/terrain-cache \
  --output data/output/wildfire_case/geo.nc
```

## Step 1: Prepare wind with WRF download

```bash
python usecases/02_wildfire_arson_effects/demo/step_01_downscale_wind.py \
  --date 20240731Z1000 \
  --hours 24 \
  --download-dir data/wrf/d03 \
  --output data/output/wildfire_case/wrf_100m_wind.nc \
  --center-lat 40.827 \
  --center-lon 14.518 \
  --nx 201 \
  --ny 201 \
  --dx 100 \
  --dy 100 \
  --dem data/output/wildfire_case/dem/cop30_wildfire_case.tif \
  --land-cover data/output/wildfire_case/landcover/lc100_wildfire_case.tif \
  --advanced-physics \
  --bulk-richardson-number 0.0 \
  --mass-consistency-iterations 80 \
  --mass-consistency-relaxation 0.8
```

The neutral Richardson-number value avoids assuming stable or unstable
conditions without event-specific boundary-layer evidence. Advanced physics
then applies horizontal divergence minimization and stores divergence RMS
before and after correction in SpritzMet metadata. This can improve the
consistency of the wind forcing used by both dispersion backends, but it is not
a full three-dimensional anelastic wind solver and does not replace validation
against observations.

Use `--no-advanced-physics` for the backward-compatible terrain-aware baseline.
Only set a nonzero `--bulk-richardson-number` when it is supported by WRF
diagnostics or observations for the modeled period. For production studies,
run both settings and retain the advanced product only when divergence
diagnostics and independent wind comparisons improve.

## Step 2: Build the fire configuration

```bash
python usecases/02_wildfire_arson_effects/demo/step_02_build_config.py \
  --output data/output/wildfire_case/wildfire_event.json \
  --center-lat 40.827 \
  --center-lon 14.518 \
  --nx 201 \
  --ny 201 \
  --dx 100 \
  --dy 100 \
  --material plastic \
  --start 20240731Z1000 \
  --end 20240801Z1000 \
  --duration-s 86400 \
  --area-m2 2500 \
  --field-z-levels 2.5,5,10,15,20,25,30,35,40,45,50,60,70,80,90,100,125,150,175,200,250,300,350,400,450,500,600,700,800,900,1000,1250,1500,1750,2000
```

For the default single-fire case, `--center-lat 40.827 --center-lon 14.518`
defines both the local projection origin and the fire location. With
`--nx 101 --ny 101 --dx 100 --dy 100`, the local grid is
`x=-5000..5000 m`, `y=-5000..5000 m`, and field cell `G50_50` is the center at
`x=0, y=0`, mapping back to `40.827 N, 14.518 E`. The particle and Gaussian
gridded concentration outputs both use this same center and coordinate contract.
Use `--field-z-levels` to write one or more concentration-field altitudes in
metres above mean sea level; multiple levels enable vertical concentration
profile plots for both Gaussian and particle outputs. Source and receptor
release heights remain heights above local ground.

## Step 3: Run the model

By default, step 3 looks for `wrf_100m_wind.nc` beside the configuration file,
copies it into each backend output directory as `meteo.nc`, derives the
concentration output interval from the NetCDF `time` axis, and enables gridded
plume output with plume-aware vertical field levels. Computation is decoupled
from visualization: this command writes model products only. Add `--plot` only
when you also want the step script to generate convenience figures in the same
run.

```bash
python usecases/02_wildfire_arson_effects/demo/step_03_run_model.py \
  --config data/output/wildfire_case/wildfire_event.json \
  --output-dir data/output/wildfire_case/model_compare/particles \
  --backend particles \
  --interchange netcdf

python usecases/02_wildfire_arson_effects/demo/step_03_run_model.py \
  --config data/output/wildfire_case/wildfire_event.json \
  --output-dir data/output/wildfire_case/model_compare/gaussian \
  --backend gaussian \
  --interchange netcdf
```

This writes separate backend products under:

- `data/output/wildfire_case/model_compare/particles/`
- `data/output/wildfire_case/model_compare/gaussian/`
- `data/output/wildfire_case/model_compare/particle_gaussian_comparison.json`

Use `--backend particles` or `--backend gaussian` to run only one backend. Use
`--meteo path/to/wrf_100m_wind.nc` when the prepared SpritzMet product is not
stored beside the configuration JSON. Use `--output-interval-s` to override the
interval inferred from the meteo file. Use `--calpuff-binary` to write a
clean-room CALPUFF-style concentration binary sidecar,
`concentration_calpuff.dat`, for each backend. NetCDF-CF remains the canonical
Sprtz interchange; the binary sidecar is for external comparison workflows.

## Step 4: Plot intermediate and final NetCDF maps

The step scripts call `tools/plotter.py` automatically for NetCDF products. To
regenerate the maps explicitly for a report, run:

```bash
python tools/plotter.py data/output/wildfire_case/wrf_100m_wind.nc \
  --variable wind_speed \
  --center-lat 40.825 \
  --center-lon 14.52 \
  --output data/output/wildfire_case/wrf_100m_wind_map.png

python tools/plotter.py data/output/wildfire_case/model_compare/particles/meteo.nc \
  --variable wind_speed_10m \
  --center-lat 40.825 \
  --center-lon 14.52 \
  --output data/output/wildfire_case/model_compare/particles/particles_meteo_map.png

python tools/plotter.py data/output/wildfire_case/model_compare/gaussian/meteo.nc \
  --variable wind_speed_10m \
  --center-lat 40.825 \
  --center-lon 14.52 \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_meteo_map.png

python tools/plotter.py data/output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --center-lat 40.825 \
  --center-lon 14.52 \
  --time-index 12 \
  --level-index 15 \
  --output data/output/wildfire_case/model_compare/particles/particles_concentration_map.png
  
python tools/plotter.py data/output/wildfire_case/model_compare/gaussian/concentration.nc \
  --variable concentration_field \
  --center-lat 40.825 \
  --center-lon 14.52 \
  --time-index 12 \
  --level-index 15 \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_concentration_map.png
```

To create animated GIFs with all plume simulation time frames, add
`--animate`. For example:

```bash
python tools/plotter.py data/output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --center-lat 40.825 \
  --center-lon 14.52 \
  --level-index 15 \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --output data/output/wildfire_case/model_compare/particles/particles_concentration_animation.gif

python tools/plotter.py data/output/wildfire_case/model_compare/gaussian/concentration.nc \
  --variable concentration_field \
  --center-lat 40.825 \
  --center-lon 14.52 \
  --level-index 15 \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_concentration_animation.gif
```

When `--plot` is supplied, step 3 writes backend-named plume profile and 3-D
plume figures for each backend. To regenerate vertical profile figures
explicitly after any compute-only run, use the standalone profiler:

```bash
python tools/plotter.py profile data/output/wildfire_case/model_compare/particles/meteo.nc \
  --variable wind_speed \
  --output data/output/wildfire_case/model_compare/particles/particles_meteo_vertical_profiles.png

python tools/plotter.py profile data/output/wildfire_case/model_compare/gaussian/meteo.nc \
  --variable wind_speed \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_meteo_vertical_profiles.png

python tools/plotter.py profile data/output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --output data/output/wildfire_case/model_compare/particles/particles_concentration_vertical_profiles.png

python tools/plotter.py profile data/output/wildfire_case/model_compare/gaussian/concentration.nc \
  --variable concentration_field \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_concentration_vertical_profiles.png
```

To animate the simulation-long plume vertical profile evolution, add
`--animate`:

```bash
python tools/plotter.py profile data/output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --output data/output/wildfire_case/model_compare/particles/particles_concentration_profiles_animation.gif

python tools/plotter.py profile data/output/wildfire_case/model_compare/gaussian/concentration.nc \
  --variable concentration_field \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_concentration_profiles_animation.gif
```

The meteo profile figure contains a center-cell time-height wind-speed panel
and sampled vertical profile curves through the WRF/SpritzMet time axis. When
the prepared meteo file contains diagnostic `U10M`/`V10M`, the plotted profile
prepends the diagnostic 10 m above-ground layer before the aloft model levels.
The plume profile figure shows the time-varying vertical
`concentration_field` at the selected center grid column for both the particle
and Gaussian backends. Its vertical axis is altitude above mean sea level for
the WRF/SpritzMet workflow. When `surface_altitude` is available in the
concentration NetCDF, `tools/plotter.py profile` masks ASL bins below the local DEM and
draws the local ground altitude, so the profile view does not reinterpret ASL
levels as height above ground.

To regenerate the 3-D plume-over-ground renders explicitly, pass a terrain/GEO
NetCDF built from the same DEM and land-cover rasters. `tools/plotter.py render3d`
draws the DEM as the ground surface, colors it by terrain elevation or
land-cover class, and renders the concentration plume above that ground
surface. Concentration `field_z` levels remain altitudes above mean sea level,
consistent with the WRF/SpritzMet forcing. The dispersion backends convert
source `height_agl_m` to ASL with the DEM at the source, and gridded
concentration cells whose ASL level is below the local DEM are written as zero.
The renderer then uses the configured `field_z` values as z-axis ticks and
draws DEM blue only where `surface_altitude <= 0`.

```bash
python tools/plotter.py render3d data/output/wildfire_case/model_compare/particles/concentration.nc \
  --variable concentration_field \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --terrain data/output/wildfire_case/geo.nc \
  --mode voxel \
  --ground-color terrain \
  --vertical-exaggeration 3 \
  --output data/output/wildfire_case/model_compare/particles/particles_concentration_3d_animation.gif

python tools/plotter.py render3d data/output/wildfire_case/model_compare/gaussian/concentration.nc \
  --variable concentration_field \
  --animate \
  --frame-duration-ms 300 \
  --gif-loop 0 \
  --terrain data/output/wildfire_case/geo.nc \
  --mode voxel \
  --ground-color terrain \
  --vertical-exaggeration 3 \
  --output data/output/wildfire_case/model_compare/gaussian/gaussian_concentration_3d_animation.gif
```

## Event timing, materials, and source height

Use these options to express the run timing requested in the generated JSON:

- `--weather-start` and `--weather-end`: weather simulation start/end datetimes as `YYYYMMDDZhhmm`.
- `--start` and `--end`: fire/arson event start/end datetimes as `YYYYMMDDZhhmm`.
- `--firefighters-start`, `--firefighters-end`, and
  `--firefighters-emission-factor`: suppression period and emission multiplier.
- `--height-agl-m`: optional release height above local ground level, useful
  for small stacks or chimney-style sources. The default is `0 m`, so the fire
  source is on the ground. When the suite is run with a terrain/GEO input, this
  value is added to the DEM elevation at the source before Gaussian or particle
  dispersion is evaluated on ASL SpritzMet levels.
- `--material`: one of `generic`, `paper`, or `plastic`.
- `--temperature-k`: optional override for the selected material preset.
- `--precipitation-washout`: use WRF/SpritzMet `precipitation_rate` as an
  additional wet-removal term.

The generated source records include `material`, `height_agl_m`,
`start_datetime`, and `end_datetime`. Run-level weather, event, firefighter, and
washout settings are written under `run`. The WRF-derived center-cell
`precipitation_rate` is preserved in the generated station record and in
`run.default_precipitation_rate` so the suite run can apply washout without
requiring a separate meteorology file.

Step 2 also writes time-dependent plume defaults under `run`:

- `output_interval_s`: hourly output by default, overridden in step 3 when a
  different interval is inferred or supplied;
- `concentration_output`: `both`, so receptor values and gridded plume fields
  are written together;
- `field_z_levels`: plume-field altitudes above mean sea level from 1.5 m
  through 2000 m by default, or explicit ASL levels from `--field-z-levels`;
- particle defaults: `particles=10000`, `particle_sigma_h=175 m`,
  `particle_sigma_z=150 m`, and `particle_advection_steps=12`.
- Gaussian puff initialization reuses the configured horizontal and vertical
  spread values when `gaussian_initial_sigma_h`/`gaussian_initial_sigma_z` are
  not supplied, keeping side-by-side backend screening on comparable initial
  plume widths.

## Multi-fire event JSON

For multiple fires, pass a JSON list to `--fire-events-json`. Each event can
set `id`, `latitude`, `longitude`, `height_agl_m`, `start_datetime`,
`end_datetime`, `material`, `area_m2`, `temperature_k`, and
`emission_factor_g_m2`. Date-time values in this script parameter use
`YYYYMMDDZhhmm`.

```bash
python usecases/02_wildfire_arson_effects/demo/step_02_build_config.py \
  --output data/output/multi_fire/wildfire_event.json \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --weather-start 20260601Z0000 \
  --weather-end 20260601Z0400 \
  --firefighters-start 20260601Z0200 \
  --firefighters-end 20260601Z0300 \
  --firefighters-emission-factor 0.4 \
  --fire-events-json '[{"id":"F1","latitude":40.8500,"longitude":14.2700,"material":"paper","start_datetime":"20260601Z0000","end_datetime":"20260601Z0300"},{"id":"F2","latitude":40.8550,"longitude":14.2750,"height_agl_m":2.0,"material":"plastic","start_datetime":"20260601Z0100","end_datetime":"20260601Z0400"}]'
```

## Expected products

- `wrf_100m_wind.nc` or `.json` — the local meteorological forcing product.
- `CALMET.DAT` — CALMET.DAT-compatible binary SpritzMet export for
  model-evaluation workflows.
- `wildfire_event.json` — the generated Spritz configuration.
- `model_compare/particles/meteo.nc` — the particle backend copy of the
  high-resolution SpritzMet forcing.
- `model_compare/particles/concentration.nc` — particle receptor and
  `concentration_field(time,field_z,field_y,field_x)` output. The center field
  receptor `G50_50` is `x=0, y=0` and carries latitude/longitude
  `40.827, 14.518` for the default case.
- `model_compare/particles/concentration_calpuff.dat` — clean-room
  CALPUFF-style binary export of the same particle gridded concentration,
  dry-flux, and wet-flux fields when `--calpuff-binary` is used.
- `model_compare/particles/post.json` — particle postprocessed statistics.
- `model_compare/gaussian/meteo.nc` — the Gaussian backend copy of the same
  SpritzMet forcing.
- `model_compare/gaussian/concentration.nc` — Gaussian receptor and
  `concentration_field(time,field_z,field_y,field_x)` output on the same
  centered grid and geographic field-receptor coordinates as the particle
  backend.
- `model_compare/gaussian/concentration_calpuff.dat` — clean-room
  CALPUFF-style binary export of the same Gaussian gridded concentration,
  dry-flux, and wet-flux fields when `--calpuff-binary` is used.
- `model_compare/gaussian/post.json` — Gaussian postprocessed statistics.
- `model_compare/particle_gaussian_comparison.json` — common-grid comparison
  metrics, including min/max, mean absolute difference, RMS difference, and max
  absolute difference.
- `wrf_100m_wind_map.png` — horizontal wind map for the prepared forcing.
- `model_compare/*/*_concentration_vertical_profiles.png` — explicit
  backend-named time-varying plume concentration profile figure, written for
  both particles and Gaussian outputs.
- `model_compare/*/*_concentration_profiles_animation.gif` — animated vertical
  plume concentration profile across every concentration output time frame.

The particle backend now advects particles through the full
`time,z,y,x` SpritzMet wind cube. The Gaussian backend samples the same
time-varying wind field along each source/receptor path and treats the active
wildfire as a continuous output-window source. Both backends keep gridded
`field_z` levels in the SpritzMet vertical reference, ASL for this WRF
workflow, while applying terrain-aware ASL source release heights computed as
`DEM(source) + height_agl_m`. The default `height_agl_m=0` means the emission
starts on the local ground, not at sea level. The two backends are screening
models with different numerical assumptions, so compare their spatial patterns
and timing as well as the summary metrics. Step 3 checks that particle and
Gaussian `time`, `field_z`, `field_y`, and `field_x` coordinates match before
writing the comparison report, so horizontal and vertical output grids stay
consistent across both modes.

## Scientific caution

This is a screening and teaching workflow, not a certified fire-emission inventory. Operational use requires validated fuel loading, combustion phase, plume-injection height, satellite constraints, and independent model evaluation.
