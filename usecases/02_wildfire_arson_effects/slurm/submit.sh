#!/bin/bash
set -euo pipefail
cd "${SPRTZ_REPO_ROOT:-$(git rev-parse --show-toplevel)}"
SLURM_DIR=usecases/02_wildfire_arson_effects/slurm
OUT=data/output/wildfire_case
CONFIG="${OUT}/wildfire_event.json"
[[ -f "${CONFIG}" ]] || { printf 'Missing %s; run demo Step 2 before submission.\n' "${CONFIG}" >&2; exit 2; }
mkdir -p "${OUT}/slurm"
weather_job=$(sbatch --parsable --output="${OUT}/slurm/weather-%j.out" "${SLURM_DIR}/01_download_weather.slurm")
dem_job=$(sbatch --parsable --output="${OUT}/slurm/dem-%j.out" "${SLURM_DIR}/02_download_dem.slurm")
landuse_job=$(sbatch --parsable --output="${OUT}/slurm/landuse-%j.out" "${SLURM_DIR}/03_download_landuse.slurm")
meteo_job=$(sbatch --parsable --dependency="afterok:${weather_job}:${dem_job}:${landuse_job}" --output="${OUT}/slurm/meteo-%j.out" "${SLURM_DIR}/04_downscale_meteorology.slurm")
particles_job=$(sbatch --parsable --dependency="afterok:${meteo_job}" --output="${OUT}/slurm/particles-%j.out" "${SLURM_DIR}/05_run_particles.slurm")
gaussian_job=$(sbatch --parsable --dependency="afterok:${meteo_job}" --output="${OUT}/slurm/gaussian-%j.out" "${SLURM_DIR}/06_run_gaussian.slurm")
plot_job=$(sbatch --parsable --dependency="afterok:${particles_job}:${gaussian_job}" --output="${OUT}/slurm/plot-%j.out" "${SLURM_DIR}/07_plot.slurm")
printf 'Submitted use case 02 jobs: weather=%s dem=%s landuse=%s meteo=%s particles=%s gaussian=%s plot=%s\n' \
  "${weather_job}" "${dem_job}" "${landuse_job}" "${meteo_job}" "${particles_job}" "${gaussian_job}" "${plot_job}"
