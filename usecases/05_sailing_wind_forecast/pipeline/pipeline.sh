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

NX="${NX:-25}"
NY="${NY:-25}"
DX="${DX:-100}"
DY="${DY:-100}"
WIND_SPEED_M_S="${WIND_SPEED_M_S:-6.0}"
WIND_FROM_DIRECTION_DEG="${WIND_FROM_DIRECTION_DEG:-245.0}"
CONFIG_PATH="${OUT_DIR}/sailing_wind_config.json"
METEO_PATH="${OUT_DIR}/sailing_wind.nc"

log_step "1. Runtime environment diagnostic"
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"

log_step "2. Sailing wind configuration synthesis"
cat > "${CONFIG_PATH}" <<JSON
{"grid":{"nx":${NX},"ny":${NY},"dx":${DX},"dy":${DY},"x0":0.0,"y0":0.0,"projection":"LOCAL"},"stations":[{"id":"BAY_WIND","x":0.0,"y":0.0,"wind_speed":${WIND_SPEED_M_S},"wind_dir":${WIND_FROM_DIRECTION_DEG},"temperature":296.0,"mixing_height":800.0,"precipitation_rate":0.0}],"sources":[{"id":"REFERENCE","x":0.0,"y":0.0,"z":0.0,"emission_rate":1.0,"stack_height":10.0,"height_agl_m":10.0,"source_type":"point","material":"generic"}],"receptors":[{"id":"MARK","x":0.0,"y":0.0,"z":1.5}],"run":{"backend":"gaussian","stability":"D","preferred_interchange":"NetCDF-CF"}}
JSON

log_step "3. Public configuration validation"
python3 "${SCRIPTS_DIR}/sprtz.py" validate "${CONFIG_PATH}"

log_step "4. SpritzMet sailing wind generation"
python3 "${SCRIPTS_DIR}/spritzmet.py" --config "${CONFIG_PATH}" --output "${METEO_PATH}" --format netcdf

log_step "5. Publication-ready 2-D wind map"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" "${METEO_PATH}" --output "${FIGURE_DIR}/sailing_wind_map.png" --variable wind_speed --title "Sailing Wind Speed" --dpi 600 --vector-density 18

log_step "6. Publication-ready vertical wind profile"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" profile "${METEO_PATH}" --output "${FIGURE_DIR}/sailing_wind_profile.png" --variable wind_speed --x 0 --y 0 --title "Sailing Wind Profile" --dpi 600

log_step "7. Publication-ready 3-D wind surface"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" render3d "${METEO_PATH}" --output "${FIGURE_DIR}/sailing_wind_3d.png" --variable wind_speed --title "Sailing Wind Field" --dpi 600 --mode surface --view northeast --vertical-exaggeration 3

log_step "Pipeline complete: ${OUT_DIR}"
