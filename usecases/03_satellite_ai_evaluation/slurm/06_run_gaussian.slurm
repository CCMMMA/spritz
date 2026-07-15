#!/bin/bash
#SBATCH --job-name=uc03-gaussian
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --time=08:00:00
#SBATCH --export=ALL
set -euo pipefail
cd "${SPRTZ_REPO_ROOT:-${SLURM_SUBMIT_DIR}}"
[[ -n "${SPRTZ_VENV:-}" ]] && source "${SPRTZ_VENV}/bin/activate"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
mkdir -p data/output/satellite_ai_evaluation/model/gaussian
srun --ntasks="${SLURM_NTASKS}" spritz \
  --config usecases/03_satellite_ai_evaluation/demo/config.json \
  --meteo data/output/satellite_ai_evaluation/domain/meteo_mpi.nc \
  --output data/output/satellite_ai_evaluation/model/gaussian/concentration.nc \
  --format netcdf --backend gaussian --output-interval 3600 \
  --parallel mpi --decomposition receptors --thread-backend serial
