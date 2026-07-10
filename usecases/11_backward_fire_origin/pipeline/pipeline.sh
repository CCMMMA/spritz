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

LIKELIHOOD_JSON="${OUT_DIR}/ignition_likelihood.json"
FIRE_OUT="${OUT_DIR}/fire_context"
CONC_PATH="${OUT_DIR}/meteo_context.nc"
mkdir -p "${FIRE_OUT}"

log_step "1. Runtime environment diagnostic"
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"

log_step "2. Backward fire configuration validation"
python3 "${SCRIPTS_DIR}/sprtz.py" validate "${REPO_ROOT}/examples/backward_firefront.json"

log_step "3. Backward fire-origin attribution"
python3 "${SCRIPTS_DIR}/sprtz_backward.py" --config "${REPO_ROOT}/examples/backward_firefront.json" --output "${LIKELIHOOD_JSON}" --model firefront --format json

log_step "4. SpritzMet meteorological context"
python3 "${SCRIPTS_DIR}/spritzmet.py" --config "${REPO_ROOT}/examples/wildfire_minimal.json" --output "${CONC_PATH}" --format netcdf

log_step "5. Firefront context simulation"
python3 "${SCRIPTS_DIR}/sprtzfire.py" --config "${REPO_ROOT}/examples/wildfire_minimal.json" --output-dir "${FIRE_OUT}" --interchange netcdf

log_step "6. Publication-ready 2-D meteorological context map"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" "${CONC_PATH}" --output "${FIGURE_DIR}/fire_context_map.png" --variable wind_speed --title "Backward Fire Meteorological Context" --dpi 600 --vector-density 18

log_step "7. Publication-ready meteorological context profile"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" profile "${CONC_PATH}" --output "${FIGURE_DIR}/fire_context_profile.png" --variable wind_speed --x 0 --y 0 --title "Backward Fire Meteorological Context Profile" --config "${REPO_ROOT}/examples/wildfire_minimal.json" --dpi 600

log_step "8. Publication-ready 3-D meteorological context surface"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" render3d "${CONC_PATH}" --output "${FIGURE_DIR}/fire_context_3d.png" --variable wind_speed --title "Backward Fire Meteorological Context 3-D" --config "${REPO_ROOT}/examples/wildfire_minimal.json" --dpi 600 --mode surface --view northeast --vertical-exaggeration 3

log_step "Pipeline complete: ${OUT_DIR}"
