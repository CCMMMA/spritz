#!/bin/bash
set -euo pipefail

cd "${SPRTZ_REPO_ROOT:-$(git rev-parse --show-toplevel)}"
SLURM_DIR=usecases/01_high_resolution_wind_field/slurm
mkdir -p data/output/high_resolution_wind_field/slurm

weather_job=$(sbatch --parsable --output=data/output/high_resolution_wind_field/slurm/weather-%j.out "${SLURM_DIR}/01_download_weather.slurm")
dem_job=$(sbatch --parsable --output=data/output/high_resolution_wind_field/slurm/dem-%j.out "${SLURM_DIR}/02_download_dem.slurm")
landuse_job=$(sbatch --parsable --output=data/output/high_resolution_wind_field/slurm/landuse-%j.out "${SLURM_DIR}/03_download_landuse.slurm")
meteo_job=$(sbatch --parsable --dependency="afterok:${weather_job}:${dem_job}:${landuse_job}" --output=data/output/high_resolution_wind_field/slurm/meteo-%j.out "${SLURM_DIR}/04_downscale_meteorology.slurm")
plot_job=$(sbatch --parsable --dependency="afterok:${meteo_job}" --output=data/output/high_resolution_wind_field/slurm/plot-%j.out "${SLURM_DIR}/05_plot.slurm")

printf 'Submitted use case 01 jobs: weather=%s dem=%s landuse=%s meteo=%s plot=%s\n' \
  "${weather_job}" "${dem_job}" "${landuse_job}" "${meteo_job}" "${plot_job}"
