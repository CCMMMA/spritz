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

CONC_PATH="${OUT_DIR}/meteo_context.nc"
mkdir -p "${OUT_DIR}/model"

log_step "1. Runtime environment diagnostic"
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"

log_step "2. Wildfire configuration validation"
python3 "${SCRIPTS_DIR}/sprtz.py" validate "${REPO_ROOT}/examples/wildfire_minimal.json"

log_step "3. SpritzMet meteorological context"
python3 "${SCRIPTS_DIR}/spritzmet.py" --config "${REPO_ROOT}/examples/wildfire_minimal.json" --output "${CONC_PATH}" --format netcdf

log_step "4. Wildfire Fire Spread model execution"
python3 "${SCRIPTS_DIR}/sprtzfire.py" --config "${REPO_ROOT}/examples/wildfire_minimal.json" --output-dir "${OUT_DIR}/model" --interchange netcdf

log_step "5. Publication-ready 2-D meteorological context map"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" "${CONC_PATH}" --output "${FIGURE_DIR}/meteo_context_map.png" --variable wind_speed --title "Wildfire Fire Spread" --dpi 600

log_step "6. Publication-ready meteorological context profile"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" profile "${CONC_PATH}" --output "${FIGURE_DIR}/meteo_context_profile.png" --variable wind_speed --x 0 --y 0 --title "Wildfire Fire Spread Profile" --config "${REPO_ROOT}/examples/wildfire_minimal.json" --dpi 600

log_step "7. Publication-ready 3-D meteorological context surface"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" render3d "${CONC_PATH}" --output "${FIGURE_DIR}/meteo_context_3d.png" --variable wind_speed --title "Wildfire Fire Spread 3-D" --config "${REPO_ROOT}/examples/wildfire_minimal.json" --dpi 600 --mode surface --view northeast --vertical-exaggeration 3

log_step "Pipeline complete: ${OUT_DIR}"
