#!/bin/bash
#SBATCH --job-name=uc01-plot
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --time=00:30:00
#SBATCH --export=ALL

set -euo pipefail
cd "${SPRTZ_REPO_ROOT:-${SLURM_SUBMIT_DIR}}"
[[ -n "${SPRTZ_VENV:-}" ]] && source "${SPRTZ_VENV}/bin/activate"
PYTHON="${PYTHON:-python}"
OUT=data/output/high_resolution_wind_field
export MPLBACKEND=Agg

"${PYTHON}" tools/plotter.py "${OUT}/wrf_100m_wind_bbox_mpi.nc" \
  --variable wind_speed_10m --time-index 12 \
  --output "${OUT}/velalonga_wind_10m_mpi.png"
"${PYTHON}" tools/plotter.py profile "${OUT}/wrf_100m_wind_bbox_mpi.nc" \
  --variable wind_speed --x 0 --y 0 \
  --output "${OUT}/velalonga_vertical_profile_mpi.png"
