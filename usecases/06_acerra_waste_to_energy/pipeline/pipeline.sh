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
EMISSION_RATE_G_S="${EMISSION_RATE_G_S:-18.0}"
WIND_SPEED_M_S="${WIND_SPEED_M_S:-3.5}"
SOURCE_X_M="${SOURCE_X_M:-1200.0}"
SOURCE_Y_M="${SOURCE_Y_M:-1200.0}"
CONFIG_PATH="${OUT_DIR}/acerra_waste_to_energy_config.json"
METEO_PATH="${OUT_DIR}/meteo.nc"
CONC_PATH="${OUT_DIR}/model/concentration.nc"
mkdir -p "${OUT_DIR}/model"

log_step "1. Runtime environment diagnostic"
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"

log_step "2. Scenario configuration synthesis"
cat > "${CONFIG_PATH}" <<JSON
{
  "grid": {"nx": ${NX}, "ny": ${NY}, "dx": ${DX}, "dy": ${DY}, "x0": 0.0, "y0": 0.0, "projection": "LOCAL"},
  "stations": [{"id": "S1", "x": 0.0, "y": 0.0, "wind_speed": ${WIND_SPEED_M_S}, "wind_dir": 270.0, "temperature": 294.0, "mixing_height": 900.0, "precipitation_rate": 0.0}],
  "sources": [{"id": "SOURCE", "x": ${SOURCE_X_M}, "y": ${SOURCE_Y_M}, "z": 0.0, "emission_rate": ${EMISSION_RATE_G_S}, "stack_height": 40.0, "height_agl_m": 40.0, "source_type": "point", "material": "generic"}],
  "receptors": [{"id": "R1", "x": 1800.0, "y": 1200.0, "z": 1.5}, {"id": "R2", "x": 2200.0, "y": 1200.0, "z": 1.5}],
  "run": {"backend": "gaussian", "concentration_output": "both", "field_z_levels": [0.0, 10.0, 50.0, 100.0], "stability": "D", "preferred_interchange": "NetCDF-CF", "output_interval_s": 3600.0}
}
JSON

log_step "3. Public configuration validation"
python3 "${SCRIPTS_DIR}/sprtz.py" validate "${CONFIG_PATH}"

log_step "4. Integrated Sprtz workflow execution"
python3 "${SCRIPTS_DIR}/sprtz.py" run "${CONFIG_PATH}" --output-dir "${OUT_DIR}/model" --backend gaussian --interchange netcdf --output-interval 3600

log_step "5. Publication-ready 2-D concentration map"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" "${CONC_PATH}" --output "${FIGURE_DIR}/concentration_map.png" --variable concentration_field --title "Acerra WTE concentration" --dpi 600 --level-index 1 --vector-density 18

log_step "6. Publication-ready vertical concentration profile"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" profile "${CONC_PATH}" --output "${FIGURE_DIR}/concentration_profile.png" --variable concentration_field --x "${SOURCE_X_M}" --y "${SOURCE_Y_M}" --title "Acerra WTE concentration Profile" --config "${CONFIG_PATH}" --dpi 600

log_step "7. Publication-ready 3-D concentration surface"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/plotter.py" render3d "${CONC_PATH}" --output "${FIGURE_DIR}/concentration_3d.png" --variable concentration_field --title "Acerra WTE concentration 3-D" --config "${CONFIG_PATH}" --dpi 600 --mode surface --view northeast --vertical-exaggeration 3

log_step "Pipeline complete: ${OUT_DIR}"
