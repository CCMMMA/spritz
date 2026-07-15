#!/bin/bash
#SBATCH --job-name=uc03-dem
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=01:00:00
#SBATCH --export=ALL
set -euo pipefail
cd "${SPRTZ_REPO_ROOT:-${SLURM_SUBMIT_DIR}}"
[[ -n "${SPRTZ_VENV:-}" ]] && source "${SPRTZ_VENV}/bin/activate"
"${PYTHON:-python}" tools/copernicus-cop30-dem-download.py \
  --center-lat 40.9769 --center-lon 14.2168 --nx 601 --ny 351 \
  --dx 100 --dy 100 --buffer-m 5000 \
  --output data/output/satellite_ai_evaluation/dem/cop30_aversa.tif
