#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USECASE_DIR="$(cd "${PIPELINE_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${USECASE_DIR}/../.." && pwd)"
SCRIPTS_DIR="${REPO_ROOT}/scripts"
DATA_ROOT="${SPRTZ_DATA_ROOT:-${REPO_ROOT}/data}"
USECASE_NAME="$(basename "${USECASE_DIR}")"
OUT_DIR="${SPRTZ_OUTPUT_DIR:-${DATA_ROOT}/${USECASE_NAME}}"
FIGURE_DIR="${OUT_DIR}/figures"
MPLCONFIGDIR="${MPLCONFIGDIR:-${OUT_DIR}/.matplotlib}"
XDG_CACHE_HOME="${XDG_CACHE_HOME:-${OUT_DIR}/.cache}"

mkdir -p "${OUT_DIR}" "${FIGURE_DIR}" "${MPLCONFIGDIR}" "${XDG_CACHE_HOME}"
export MPLCONFIGDIR XDG_CACHE_HOME
cd "${REPO_ROOT}"

log_step() {
  printf '\n[%s] %s\n' "${USECASE_NAME}" "$1"
}

log_step "1. Runtime environment diagnostic"
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"

log_step "2. Reference Sprtz workflow execution"
python3 "${SCRIPTS_DIR}/sprtz.py" run "${REPO_ROOT}/examples/minimal.json" --output-dir "${OUT_DIR}/model" --interchange netcdf

log_step "3. Publication-ready reference wind map"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render.py" "${OUT_DIR}/model/meteo.nc" --output "${FIGURE_DIR}/reference_wind_map.png" --variable wind_speed --title "Reference Wind Field" --dpi 600 --vector-density 18

log_step "4. Publication-ready reference wind profile"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/profiler.py" "${OUT_DIR}/model/meteo.nc" --output "${FIGURE_DIR}/reference_wind_profile.png" --variable wind_speed --x 0 --y 0 --title "Reference Wind Profile" --dpi 600

log_step "5. Publication-ready 3-D reference wind surface"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render3d.py" "${OUT_DIR}/model/meteo.nc" --output "${FIGURE_DIR}/reference_wind_3d.png" --variable wind_speed --title "Reference Wind Surface" --dpi 600 --mode surface --view northeast --vertical-exaggeration 3

log_step "Pipeline complete: ${OUT_DIR}"
