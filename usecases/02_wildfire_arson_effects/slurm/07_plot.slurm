#!/bin/bash
#SBATCH --job-name=uc02-plot
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --time=01:00:00
#SBATCH --export=ALL
set -euo pipefail
cd "${SPRTZ_REPO_ROOT:-${SLURM_SUBMIT_DIR}}"
[[ -n "${SPRTZ_VENV:-}" ]] && source "${SPRTZ_VENV}/bin/activate"
PYTHON="${PYTHON:-python}"
OUT=data/output/wildfire_case
export MPLBACKEND=Agg
"${PYTHON}" tools/plotter.py "${OUT}/wrf_100m_wind_mpi.nc" \
  --variable wind_speed_10m --time-index 12 --output "${OUT}/wrf_100m_wind_mpi.png"
for backend in particles gaussian; do
  "${PYTHON}" tools/plotter.py "${OUT}/model_compare/${backend}/concentration.nc" \
    --variable concentration_field --time-index 12 --level-index 15 \
    --output "${OUT}/model_compare/${backend}/${backend}_concentration_mpi.png"
done
