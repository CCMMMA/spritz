#!/bin/bash
#SBATCH --job-name=uc01-dem
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=01:00:00
#SBATCH --export=ALL

set -euo pipefail
cd "${SPRTZ_REPO_ROOT:-${SLURM_SUBMIT_DIR}}"
[[ -n "${SPRTZ_VENV:-}" ]] && source "${SPRTZ_VENV}/bin/activate"
PYTHON="${PYTHON:-python}"

"${PYTHON}" tools/copernicus-cop30-dem-download.py \
  --south 40.78 --north 40.85 --west 14.18 --east 14.33 \
  --dx 100 --dy 100 --buffer-m 5000 \
  --output data/output/high_resolution_wind_field/dem/cop30_naples.tif
