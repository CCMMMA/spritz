#!/bin/bash
#SBATCH --job-name=uc01-wrf
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=01:00:00
#SBATCH --export=ALL

set -euo pipefail
cd "${SPRTZ_REPO_ROOT:-${SLURM_SUBMIT_DIR}}"
[[ -n "${SPRTZ_VENV:-}" ]] && source "${SPRTZ_VENV}/bin/activate"
PYTHON="${PYTHON:-python}"

"${PYTHON}" tools/meteouniparthenope-wrf-download.py 20260621Z0000 \
  --hours 24 --domain d03 --data-root data/wrf/d03
