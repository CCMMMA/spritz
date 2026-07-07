#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USECASE_DIR="$(cd "${PIPELINE_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${USECASE_DIR}/../.." && pwd)"
SCRIPTS_DIR="${REPO_ROOT}/scripts"
DATA_ROOT="${SPRTZ_DATA_ROOT:-${REPO_ROOT}/data}"
USECASE_NAME="$(basename "${USECASE_DIR}")"
OUT_DIR="${SPRTZ_OUTPUT_DIR:-${DATA_ROOT}/${USECASE_NAME}}"

mkdir -p "${OUT_DIR}"
cd "${REPO_ROOT}"

log_step() {
  printf '\n[%s] %s\n' "${USECASE_NAME}" "$1"
}

NX="${NX:-21}"
NY="${NY:-21}"
DX="${DX:-100}"
DY="${DY:-100}"
WIND_SPEED_M_S="${WIND_SPEED_M_S:-5.0}"
WIND_FROM_DIRECTION_DEG="${WIND_FROM_DIRECTION_DEG:-270.0}"
TEMPERATURE_K="${TEMPERATURE_K:-294.0}"
MIXING_HEIGHT_M="${MIXING_HEIGHT_M:-900.0}"
PRECIPITATION_RATE_MM_H="${PRECIPITATION_RATE_MM_H:-0.0}"

CONFIG_PATH="${OUT_DIR}/high_resolution_wind_config.json"
METEO_PATH="${OUT_DIR}/spritzmet_100m_wind.nc"
FIGURE_DIR="${OUT_DIR}/figures"
MPLCONFIGDIR="${MPLCONFIGDIR:-${OUT_DIR}/.matplotlib}"
mkdir -p "${FIGURE_DIR}"
export MPLCONFIGDIR

log_step "1. Runtime environment diagnostic"
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"

log_step "2. Local-grid configuration synthesis"
cat > "${CONFIG_PATH}" <<JSON
{
  "grid": {
    "nx": ${NX},
    "ny": ${NY},
    "dx": ${DX},
    "dy": ${DY},
    "x0": 0.0,
    "y0": 0.0,
    "projection": "LOCAL"
  },
  "stations": [
    {
      "id": "SYNTHETIC_CENTER",
      "x": 0.0,
      "y": 0.0,
      "wind_speed": ${WIND_SPEED_M_S},
      "wind_dir": ${WIND_FROM_DIRECTION_DEG},
      "temperature": ${TEMPERATURE_K},
      "mixing_height": ${MIXING_HEIGHT_M},
      "precipitation_rate": ${PRECIPITATION_RATE_MM_H}
    }
  ],
  "sources": [
    {
      "id": "REFERENCE_SOURCE",
      "x": 0.0,
      "y": 0.0,
      "z": 0.0,
      "emission_rate": 1.0,
      "stack_height": 10.0,
      "height_agl_m": 10.0,
      "source_type": "point",
      "material": "generic"
    }
  ],
  "receptors": [
    {
      "id": "REFERENCE_RECEPTOR",
      "x": 0.0,
      "y": 0.0,
      "z": 1.5
    }
  ],
  "run": {
    "backend": "gaussian",
    "stability": "D",
    "preferred_interchange": "NetCDF-CF"
  }
}
JSON

log_step "3. Public configuration validation"
python3 "${SCRIPTS_DIR}/sprtz.py" validate "${CONFIG_PATH}"

log_step "4. SpritzMet high-resolution wind generation"
python3 "${SCRIPTS_DIR}/spritzmet.py" --config "${CONFIG_PATH}" --output "${METEO_PATH}" --format netcdf

log_step "5. Publication-ready 2-D wind map"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render.py" "${METEO_PATH}" --output "${FIGURE_DIR}/wind_speed_map.png" --variable wind_speed --title "SpritzMet 100 m Wind Speed" --dpi 600 --vector-density 18

log_step "6. Publication-ready vertical profile"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/profiler.py" "${METEO_PATH}" --output "${FIGURE_DIR}/wind_speed_profile.png" --variable wind_speed --x 0 --y 0 --title "SpritzMet 100 m Wind Profile" --dpi 600

log_step "7. Publication-ready 3-D wind surface"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render3d.py" "${METEO_PATH}" --output "${FIGURE_DIR}/wind_speed_3d.png" --variable wind_speed --title "SpritzMet 100 m Wind Field" --dpi 600 --mode surface --view northeast --vertical-exaggeration 3

log_step "Pipeline complete: ${OUT_DIR}"
