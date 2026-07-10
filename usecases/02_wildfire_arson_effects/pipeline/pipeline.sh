#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USECASE_DIR="$(cd "${PIPELINE_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${USECASE_DIR}/../.." && pwd)"
SCRIPTS_DIR="${REPO_ROOT}/scripts"
DATA_ROOT="${SPRTZ_DATA_ROOT:-${REPO_ROOT}/data}"
OUT_DIR="${SPRTZ_OUTPUT_DIR:-${DATA_ROOT}/output/wildfire_case}"
PYTHON="${PYTHON:-python3}"

NX="${NX:-31}"
NY="${NY:-31}"
DX="${DX:-100}"
DY="${DY:-100}"
WIND_SPEED_M_S="${WIND_SPEED_M_S:-4.0}"
WIND_FROM_DIRECTION_DEG="${WIND_FROM_DIRECTION_DEG:-270.0}"
TEMPERATURE_K="${TEMPERATURE_K:-298.0}"
MIXING_HEIGHT_M="${MIXING_HEIGHT_M:-1000.0}"
PRECIPITATION_RATE_MM_H="${PRECIPITATION_RATE_MM_H:-0.2}"
EMISSION_RATE_G_S="${EMISSION_RATE_G_S:-35.0}"
SOURCE_X_M="${SOURCE_X_M:-1500.0}"
SOURCE_Y_M="${SOURCE_Y_M:-1500.0}"
SOURCE_HEIGHT_M="${SOURCE_HEIGHT_M:-10.0}"
PARTICLE_SEED="${PARTICLE_SEED:-1234}"
OUTPUT_INTERVAL_S="${OUTPUT_INTERVAL_S:-3600}"

CONFIG_PATH="${OUT_DIR}/wildfire_event.json"
METEO_PATH="${OUT_DIR}/meteo.nc"
GAUSSIAN_DIR="${OUT_DIR}/model_compare/gaussian"
PARTICLE_DIR="${OUT_DIR}/model_compare/particles"
GAUSSIAN_CONC="${GAUSSIAN_DIR}/concentration.nc"
PARTICLE_CONC="${PARTICLE_DIR}/concentration.nc"
FIGURE_DIR="${OUT_DIR}/figures"
MPLCONFIGDIR="${MPLCONFIGDIR:-${OUT_DIR}/.matplotlib}"
XDG_CACHE_HOME="${XDG_CACHE_HOME:-${OUT_DIR}/.cache}"

mkdir -p "${GAUSSIAN_DIR}" "${PARTICLE_DIR}" "${FIGURE_DIR}" "${MPLCONFIGDIR}" "${XDG_CACHE_HOME}"
cd "${REPO_ROOT}"
export MPLCONFIGDIR XDG_CACHE_HOME

log_step() {
  printf '\n[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$1"
}

log_step "1/9 Runtime environment diagnostic"
"${PYTHON}" "${SCRIPTS_DIR}/sprtz_doctor.py"

log_step "2/9 Build the deterministic wildfire screening configuration"
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
      "id": "SYNTHETIC_UPWIND",
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
      "id": "WILDFIRE_ARSON_SOURCE",
      "x": ${SOURCE_X_M},
      "y": ${SOURCE_Y_M},
      "z": 0.0,
      "emission_rate": ${EMISSION_RATE_G_S},
      "stack_height": ${SOURCE_HEIGHT_M},
      "height_agl_m": ${SOURCE_HEIGHT_M},
      "source_type": "area",
      "material": "generic",
      "deposition_velocity": 0.001,
      "wet_scavenging": 0.00001,
      "decay_rate": 0.0
    }
  ],
  "receptors": [
    {"id": "R_DOWNWIND_1", "x": 2000.0, "y": 1500.0, "z": 1.5},
    {"id": "R_DOWNWIND_2", "x": 2500.0, "y": 1500.0, "z": 1.5},
    {"id": "R_CROSSWIND", "x": 2000.0, "y": 1800.0, "z": 1.5}
  ],
  "run": {
    "backend": "gaussian",
    "concentration_output": "both",
    "field_z_levels": [0.0, 10.0, 50.0, 100.0],
    "stability": "D",
    "threshold": 0.00001,
    "particles": 1000,
    "seed": ${PARTICLE_SEED},
    "particle_duration_s": 3600.0,
    "particle_sigma_h": 25.0,
    "particle_sigma_z": 10.0,
    "particle_advection_steps": 20,
    "preferred_interchange": "NetCDF-CF",
    "precipitation_washout": true,
    "output_interval_s": ${OUTPUT_INTERVAL_S}
  }
}
JSON

log_step "3/9 Validate the public Sprtz configuration"
"${PYTHON}" "${SCRIPTS_DIR}/sprtz.py" validate "${CONFIG_PATH}"

log_step "4/9 Generate SpritzMet meteorology"
"${PYTHON}" "${SCRIPTS_DIR}/spritzmet.py" \
  --config "${CONFIG_PATH}" --output "${METEO_PATH}" --format netcdf

log_step "5/9 Run Gaussian dispersion"
"${PYTHON}" "${SCRIPTS_DIR}/spritz.py" \
  --config "${CONFIG_PATH}" --meteo "${METEO_PATH}" \
  --output "${GAUSSIAN_CONC}" --format netcdf --backend gaussian \
  --output-interval "${OUTPUT_INTERVAL_S}"

log_step "6/9 Run particle dispersion"
"${PYTHON}" "${SCRIPTS_DIR}/spritz.py" \
  --config "${CONFIG_PATH}" --meteo "${METEO_PATH}" \
  --output "${PARTICLE_CONC}" --format netcdf --backend particles \
  --seed "${PARTICLE_SEED}" --output-interval "${OUTPUT_INTERVAL_S}"

log_step "7/9 Postprocess Gaussian output"
"${PYTHON}" "${SCRIPTS_DIR}/spritzpost.py" \
  --input "${GAUSSIAN_CONC}" --output "${GAUSSIAN_DIR}/post.json"

log_step "8/9 Postprocess particle output"
"${PYTHON}" "${SCRIPTS_DIR}/spritzpost.py" \
  --input "${PARTICLE_CONC}" --output "${PARTICLE_DIR}/post.json"

log_step "9/9 Render backend concentration figures"
"${PYTHON}" tools/plotter.py \
  "${GAUSSIAN_CONC}" \
  --output "${FIGURE_DIR}/gaussian_concentration.png" \
  --variable concentration_field \
  --title "Wildfire/Arson Gaussian Concentration" --dpi 300
"${PYTHON}" tools/plotter.py \
  "${PARTICLE_CONC}" \
  --output "${FIGURE_DIR}/particle_concentration.png" \
  --variable concentration_field \
  --title "Wildfire/Arson Particle Concentration" --dpi 300

log_step "Pipeline complete: ${OUT_DIR}"
