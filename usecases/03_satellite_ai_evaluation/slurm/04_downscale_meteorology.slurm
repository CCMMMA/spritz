#!/bin/bash
#SBATCH --job-name=uc03-met
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --time=08:00:00
#SBATCH --export=ALL
set -euo pipefail
cd "${SPRTZ_REPO_ROOT:-${SLURM_SUBMIT_DIR}}"
[[ -n "${SPRTZ_VENV:-}" ]] && source "${SPRTZ_VENV}/bin/activate"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
srun --ntasks="${SLURM_NTASKS}" "${PYTHON:-python}" \
  usecases/03_satellite_ai_evaluation/demo/step_02_prepare_domain.py \
  --date 20240619Z1000 --hours 4 --download-dir data/wrf/d03 \
  --center-lat 40.9769 --center-lon 14.2168 \
  --nx 601 --ny 351 --dx 100 --dy 100 \
  --dem data/output/satellite_ai_evaluation/dem/cop30_aversa.tif \
  --land-cover data/output/satellite_ai_evaluation/landcover/lc100_aversa.tif \
  --advanced-physics --bulk-richardson-number 0.0 \
  --mass-consistency-iterations 80 --mass-consistency-relaxation 0.8 \
  --output data/output/satellite_ai_evaluation/domain/meteo_mpi.nc \
  --parallel mpi --decomposition rows --thread-backend serial
