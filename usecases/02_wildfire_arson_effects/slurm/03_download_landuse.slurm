#!/bin/bash
#SBATCH --job-name=uc02-lu
#SBATCH --nodes=1
#SBATCH --ntasks=1
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
  --center-lat 40.827 --center-lon 14.518 --nx 201 --ny 201 \
  --dx 100 --dy 100 --buffer-m 5000 --source-url "${CACHE}" \
  --output data/output/wildfire_case/landcover/lc100_wildfire_case.tif
