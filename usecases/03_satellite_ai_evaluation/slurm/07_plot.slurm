#!/bin/bash
#SBATCH --job-name=uc03-plot
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --time=01:00:00
#SBATCH --export=ALL
set -euo pipefail
cd "${SPRTZ_REPO_ROOT:-${SLURM_SUBMIT_DIR}}"
[[ -n "${SPRTZ_VENV:-}" ]] && source "${SPRTZ_VENV}/bin/activate"
PYTHON="${PYTHON:-python}"
OUT=data/output/satellite_ai_evaluation
export MPLBACKEND=Agg
mkdir -p "${OUT}/figures"
"${PYTHON}" tools/plotter.py "${OUT}/domain/meteo_mpi.nc" \
  --variable wind_speed_10m --time-index 1 --output "${OUT}/figures/meteo_mpi.png"
for backend in particles gaussian; do
  "${PYTHON}" tools/plotter.py "${OUT}/model/${backend}/concentration.nc" \
    --variable concentration_field --time-index 1 --level-index 0 \
    --config usecases/03_satellite_ai_evaluation/demo/config.json --log-scale \
    --output "${OUT}/figures/${backend}_concentration_mpi.png"
done
