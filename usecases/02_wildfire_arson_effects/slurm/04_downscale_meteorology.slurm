#!/bin/bash
#SBATCH --job-name=uc02-met
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --time=06:00:00
#SBATCH --export=ALL
set -euo pipefail
cd "${SPRTZ_REPO_ROOT:-${SLURM_SUBMIT_DIR}}"
[[ -n "${SPRTZ_VENV:-}" ]] && source "${SPRTZ_VENV}/bin/activate"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
srun --ntasks="${SLURM_NTASKS}" "${PYTHON:-python}" \
  usecases/02_wildfire_arson_effects/demo/step_01_downscale_wind.py \
  --date 20240731Z1000 --hours 24 --download-dir data/wrf/d03 \
  --output data/output/wildfire_case/wrf_100m_wind_mpi.nc \
  --center-lat 40.827 --center-lon 14.518 --nx 201 --ny 201 \
  --dx 100 --dy 100 \
  --dem data/output/wildfire_case/dem/cop30_wildfire_case.tif \
  --land-cover data/output/wildfire_case/landcover/lc100_wildfire_case.tif \
  --advanced-physics --bulk-richardson-number 0.0 \
  --mass-consistency-iterations 80 --mass-consistency-relaxation 0.8 \
  --parallel mpi --decomposition rows --thread-backend serial
