#!/bin/bash
#SBATCH --job-name=uc02-particles
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --time=06:00:00
#SBATCH --export=ALL
set -euo pipefail
cd "${SPRTZ_REPO_ROOT:-${SLURM_SUBMIT_DIR}}"
[[ -n "${SPRTZ_VENV:-}" ]] && source "${SPRTZ_VENV}/bin/activate"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
mkdir -p data/output/wildfire_case/model_compare/particles
srun --ntasks="${SLURM_NTASKS}" spritz \
  --config data/output/wildfire_case/wildfire_event.json \
  --meteo data/output/wildfire_case/wrf_100m_wind_mpi.nc \
  --output data/output/wildfire_case/model_compare/particles/concentration.nc \
  --format netcdf --backend particles --output-interval 3600 \
  --parallel mpi --decomposition particles --thread-backend serial
