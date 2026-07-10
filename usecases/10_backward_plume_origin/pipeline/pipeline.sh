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

METEO_PATH="${OUT_DIR}/meteo.nc"
LIKELIHOOD_JSON="${OUT_DIR}/source_likelihood.json"

log_step "1. Runtime environment diagnostic"
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"

log_step "2. Backward plume configuration validation"
python3 "${SCRIPTS_DIR}/sprtz.py" validate "${REPO_ROOT}/examples/backward_plume.json"

log_step "3. SpritzMet meteorology generation"
python3 "${SCRIPTS_DIR}/spritzmet.py" --config "${REPO_ROOT}/examples/backward_plume.json" --output "${METEO_PATH}" --format netcdf

log_step "4. Backward plume-source attribution"
python3 "${SCRIPTS_DIR}/sprtz_backward.py" --config "${REPO_ROOT}/examples/backward_plume.json" --meteo "${METEO_PATH}" --output "${LIKELIHOOD_JSON}" --model gaussian --format json

log_step "5. Publication-ready 2-D wind map"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" "${METEO_PATH}" --output "${FIGURE_DIR}/backward_meteo_map.png" --variable wind_speed --title "Backward Plume Meteorology" --dpi 600 --vector-density 18

log_step "6. Publication-ready vertical wind profile"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" profile "${METEO_PATH}" --output "${FIGURE_DIR}/backward_meteo_profile.png" --variable wind_speed --x 0 --y 0 --title "Backward Plume Wind Profile" --dpi 600

log_step "7. Publication-ready 3-D wind surface"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" render3d "${METEO_PATH}" --output "${FIGURE_DIR}/backward_meteo_3d.png" --variable wind_speed --title "Backward Plume Wind Field" --dpi 600 --mode surface --view northeast --vertical-exaggeration 3

log_step "Pipeline complete: ${OUT_DIR}"
