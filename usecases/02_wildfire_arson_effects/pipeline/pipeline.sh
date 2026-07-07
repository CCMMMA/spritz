#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USECASE_DIR="$(cd "${PIPELINE_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${USECASE_DIR}/../.." && pwd)"
SCRIPTS_DIR="${REPO_ROOT}/scripts"
DATA_ROOT="${SPRTZ_DATA_ROOT:-${REPO_ROOT}/data}"
USECASE_NAME="$(basename "${USECASE_DIR}")"
OUT_DIR="${SPRTZ_OUTPUT_DIR:-${DATA_ROOT}/${USECASE_NAME}}"

mkdir -p "${OUT_DIR}" "${OUT_DIR}/gaussian" "${OUT_DIR}/particles"
cd "${REPO_ROOT}"

log_step() {
  printf '\n[%s] %s\n' "${USECASE_NAME}" "$1"
}

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

CONFIG_PATH="${OUT_DIR}/wildfire_arson_effects_config.json"
METEO_PATH="${OUT_DIR}/meteo.nc"
GAUSSIAN_CONC="${OUT_DIR}/gaussian/concentration.nc"
PARTICLE_CONC="${OUT_DIR}/particles/concentration.nc"
FIGURE_DIR="${OUT_DIR}/figures"
MPLCONFIGDIR="${MPLCONFIGDIR:-${OUT_DIR}/.matplotlib}"
XDG_CACHE_HOME="${XDG_CACHE_HOME:-${OUT_DIR}/.cache}"

mkdir -p "${FIGURE_DIR}" "${MPLCONFIGDIR}" "${XDG_CACHE_HOME}"
export MPLCONFIGDIR XDG_CACHE_HOME

log_step "1. Runtime environment diagnostic"
python3 "${SCRIPTS_DIR}/sprtz_doctor.py"

log_step "2. Wildfire/arson configuration synthesis"
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
    "output_interval_s": 3600.0
  }
}
JSON

log_step "3. Public configuration validation"
python3 "${SCRIPTS_DIR}/sprtz.py" validate "${CONFIG_PATH}"

log_step "4. SpritzMet meteorological interpolation"
python3 "${SCRIPTS_DIR}/spritzmet.py" --config "${CONFIG_PATH}" --output "${METEO_PATH}" --format netcdf

log_step "5. Gaussian dispersion simulation"
python3 "${SCRIPTS_DIR}/spritz.py" --config "${CONFIG_PATH}" --meteo "${METEO_PATH}" --output "${GAUSSIAN_CONC}" --format netcdf --backend gaussian --output-interval 3600

log_step "6. Particle dispersion simulation"
python3 "${SCRIPTS_DIR}/spritz.py" --config "${CONFIG_PATH}" --meteo "${METEO_PATH}" --output "${PARTICLE_CONC}" --format netcdf --backend particles --seed "${PARTICLE_SEED}" --output-interval 3600

log_step "7. Gaussian SpritzPost summary generation"
python3 "${SCRIPTS_DIR}/spritzpost.py" --input "${GAUSSIAN_CONC}" --output "${OUT_DIR}/gaussian/post.json"

log_step "8. Particle SpritzPost summary generation"
python3 "${SCRIPTS_DIR}/spritzpost.py" --input "${PARTICLE_CONC}" --output "${OUT_DIR}/particles/post.json"

log_step "9. Publication-ready 2-D concentration map"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render.py" "${GAUSSIAN_CONC}" --output "${FIGURE_DIR}/gaussian_concentration_map.png" --variable concentration_field --title "Wildfire/Arson Gaussian Concentration" --dpi 600 --level-index 1 --vector-density 18

log_step "10. Publication-ready vertical concentration profile"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/profiler.py" "${GAUSSIAN_CONC}" --output "${FIGURE_DIR}/gaussian_concentration_profile.png" --variable concentration_field --x "${SOURCE_X_M}" --y "${SOURCE_Y_M}" --title "Wildfire/Arson Concentration Profile" --config "${CONFIG_PATH}" --dpi 600

log_step "11. Publication-ready 3-D concentration surface"
MPLBACKEND=Agg python3 "${REPO_ROOT}/tools/render3d.py" "${GAUSSIAN_CONC}" --output "${FIGURE_DIR}/gaussian_concentration_3d.png" --variable concentration_field --title "Wildfire/Arson Concentration Field" --config "${CONFIG_PATH}" --dpi 600 --mode surface --view northeast --vertical-exaggeration 3

log_step "Pipeline complete: ${OUT_DIR}"
