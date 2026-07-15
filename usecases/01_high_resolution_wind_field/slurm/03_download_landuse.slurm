#!/bin/bash
#SBATCH --job-name=uc01-lu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
#SBATCH --export=ALL

set -euo pipefail
cd "${SPRTZ_REPO_ROOT:-${SLURM_SUBMIT_DIR}}"
[[ -n "${SPRTZ_VENV:-}" ]] && source "${SPRTZ_VENV}/bin/activate"
PYTHON="${PYTHON:-python}"
CACHE=data/cache/copernicus-lc100/PROBAV_LC100_2019_discrete.tif
mkdir -p "$(dirname "${CACHE}")"

if [[ ! -s "${CACHE}" ]]; then
  curl -fL --retry 10 --continue-at - --output "${CACHE}" \
    "https://zenodo.org/api/records/3939050/files/PROBAV_LC100_global_v3.0.1_2019-nrt_Discrete-Classification-map_EPSG-4326.tif/content"
fi

"${PYTHON}" tools/copernicus-lc100-download.py \
  --south 40.78 --north 40.85 --west 14.18 --east 14.33 \
  --dx 100 --dy 100 --buffer-m 5000 --source-url "${CACHE}" \
  --output data/output/high_resolution_wind_field/landcover/lc100_naples.tif
