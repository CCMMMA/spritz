# Use Case 11: Backward Fire Origin

Estimate likely ignition locations from observed burned/fire points and wind direction.

NetCDF/time convention: backward fire-origin sidecars follow strict CF
coordinate metadata. Any physical meteorology time must come from upstream
SpritzWRF/SpritzMet WRF/CF metadata, not from filenames.

## Data Preparation

Prepare meteorology and terrain for the fire-origin analysis area:

```bash
tools/meteouniparthenope-wrf-download.py 20260601Z0000 --hours 6 --domain d03 --data-root data/wrf/d03
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_backward_fire_area.tif
python3 tools/copernicus-lc100-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/landcover/lc100_backward_fire_area.tif
```

Use the COP30 and LC100 GeoTIFFs as SpritzMet `--dem`/`--land-cover` inputs
when preparing WRF-derived wind and precipitation, and through
`sprtz-terrain fetch` with matching domain settings when terrain or land cover
affects ignition plausibility or spread interpretation.

Create the backward-fire GEO product before 3-D ignition-likelihood rendering:

```bash
sprtz-terrain fetch \
  --center-lat 40.75 \
  --center-lon 14.30 \
  --nx 101 \
  --ny 101 \
  --dx 100 \
  --dy 100 \
  --dem data/dem/cop30_backward_fire_area.tif \
  --landuse data/landcover/lc100_backward_fire_area.tif \
  --landuse-mapping copernicus-lc100 \
  --cache-dir output/terrain-cache \
  --output output_backward_fire/geo.nc
```

```bash
python usecases/11_backward_fire_origin/step_01_estimate_ignition.py
```

## Plot the final NetCDF map

The step script writes a NetCDF sidecar and calls `tools/plotter.py`. To
regenerate the final ignition-likelihood map explicitly, run:

```bash
python tools/plotter.py output_backward_fire/ignition_likelihood.nc \
  --variable ignition_likelihood \
  --output output_backward_fire/ignition_likelihood_map.png
```

With a matching terrain/GEO NetCDF, render the ignition-likelihood surface over
DEM-shaped, terrain-colored ground:

```bash
python tools/render3d.py output_backward_fire/ignition_likelihood.nc \
  --variable ignition_likelihood \
  --terrain output_backward_fire/geo.nc \
  --mode surface \
  --ground-color terrain \
  --output output_backward_fire/ignition_likelihood_3d.png
```

SLURM sketch:

```bash
#!/bin/bash
#SBATCH --job-name=sprtz_backward_fire
#SBATCH --ntasks=1
#SBATCH --time=00:05:00
module load python/3.11
source .venv/bin/activate
python usecases/11_backward_fire_origin/step_01_estimate_ignition.py
```
