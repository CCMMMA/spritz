#!/bin/bash
#SBATCH --job-name=uc01-met
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --time=04:00:00
#SBATCH --export=ALL

set -euo pipefail
cd "${SPRTZ_REPO_ROOT:-${SLURM_SUBMIT_DIR}}"
[[ -n "${SPRTZ_VENV:-}" ]] && source "${SPRTZ_VENV}/bin/activate"
PYTHON="${PYTHON:-python}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

srun --ntasks="${SLURM_NTASKS}" "${PYTHON}" \
  usecases/01_high_resolution_wind_field/demo/step_01_downscale_wind.py \
  --date 20260621Z0000 --hours 24 --download-dir data/wrf/d03 \
  --output data/output/high_resolution_wind_field/wrf_100m_wind_bbox_mpi.nc \
  --south 40.78 --north 40.85 --west 14.18 --east 14.33 \
  --dx 100 --dy 100 \
  --config usecases/01_high_resolution_wind_field/demo/config.json \
  --dem data/output/high_resolution_wind_field/dem/cop30_naples.tif \
  --land-cover data/output/high_resolution_wind_field/landcover/lc100_naples.tif \
  --parallel mpi --decomposition rows --thread-backend serial
