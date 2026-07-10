#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USECASE_DIR="$(cd "${PIPELINE_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${USECASE_DIR}/../.." && pwd)"
SCRIPTS_DIR="${REPO_ROOT}/scripts"
DATA_ROOT="${SPRTZ_DATA_ROOT:-${REPO_ROOT}/data}"
OUT_DIR="${SPRTZ_OUTPUT_DIR:-${DATA_ROOT}/03_satellite_ai_evaluation}"
PYTHON="${PYTHON:-python3}"
NETWORK="${SPRTZ_RUN_NETWORK:-0}"
ALLOW_SYNTHETIC_SATELLITE_FALLBACK="${SPRTZ_ALLOW_SYNTHETIC_SATELLITE_FALLBACK:-0}"
CONFIG_PATH="${USECASE_DIR}/demo/config.json"
STATION_OBSERVATIONS="${USECASE_DIR}/usecase_03_stations.csv"
WRF_DIR="${OUT_DIR}/wrf"
SATELLITE_DIR="${OUT_DIR}/satellite"
DEM_PATH="${OUT_DIR}/dem/cop30_aversa.tif"
LAND_COVER_PATH="${OUT_DIR}/landcover/lc100_aversa.tif"
GEO_PATH="${OUT_DIR}/geo.nc"
TERRAIN_CACHE_DIR="${OUT_DIR}/terrain-cache"
METEO_PATH="${OUT_DIR}/domain/meteo.nc"
GAUSSIAN_DIR="${OUT_DIR}/model/gaussian"
PARTICLE_DIR="${OUT_DIR}/model/particles"
SATELLITE_RAW="${SATELLITE_DIR}/sentinel5p_aer_ai_20240619T120518Z_full_orbit.tif"
SATELLITE_ALIGNED="${SATELLITE_DIR}/sentinel5p_aer_ai_downscaled.json"
SATELLITE_NO2_RAW="${SATELLITE_DIR}/sentinel5p_no2_20240619T120518Z_full_orbit.tif"
FIGURE_DIR="${OUT_DIR}/figures"

mkdir -p "${WRF_DIR}" "${SATELLITE_DIR}" "$(dirname "${DEM_PATH}")" \
  "$(dirname "${LAND_COVER_PATH}")" "${TERRAIN_CACHE_DIR}" "$(dirname "${METEO_PATH}")" \
  "${GAUSSIAN_DIR}" "${PARTICLE_DIR}" "${FIGURE_DIR}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-${OUT_DIR}/.matplotlib}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${OUT_DIR}/.cache}"
mkdir -p "${MPLCONFIGDIR}" "${XDG_CACHE_HOME}"
cd "${REPO_ROOT}"

log_step() { printf '\n[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$1"; }

log_step "1/12 Diagnose runtime and validate the Aversa event configuration"
"${PYTHON}" "${SCRIPTS_DIR}/sprtz_doctor.py"
"${PYTHON}" "${SCRIPTS_DIR}/sprtz.py" validate "${CONFIG_PATH}"

log_step "2/12 Download three hourly WRF d03 files for the event"
if [[ "${NETWORK}" == "1" ]]; then
  "${PYTHON}" tools/meteouniparthenope-wrf-download.py 20240619Z1000 \
    --hours 4 --domain d03 --data-root "${WRF_DIR}"
else
  log_step "Network disabled; set SPRTZ_RUN_NETWORK=1 for operational downloads"
fi

log_step "3/12 Download buffered COP30 DEM"
if [[ "${NETWORK}" == "1" ]]; then
  "${PYTHON}" tools/copernicus-cop30-dem-download.py \
    --center-lat 40.9769 --center-lon 14.2168 \
    --nx 601 --ny 351 --dx 100 --dy 100 --buffer-m 5000 \
    --output "${DEM_PATH}"
fi

log_step "4/12 Download buffered Copernicus LC100 land cover"
if [[ "${NETWORK}" == "1" ]]; then
  "${PYTHON}" tools/copernicus-lc100-download.py \
    --center-lat 40.9769 --center-lon 14.2168 \
    --nx 601 --ny 351 --dx 100 --dy 100 --buffer-m 5000 \
    --output "${LAND_COVER_PATH}"
fi

log_step "5/12 Build the matching terrain/GEO product"
if [[ "${NETWORK}" == "1" ]]; then
  "${PYTHON}" "${SCRIPTS_DIR}/sprtz_terrain.py" fetch \
    --center-lat 40.9769 --center-lon 14.2168 \
    --nx 601 --ny 351 --dx 100 --dy 100 \
    --dem "${DEM_PATH}" --landuse "${LAND_COVER_PATH}" \
    --landuse-mapping copernicus-lc100 \
    --cache-dir "${TERRAIN_CACHE_DIR}" --output "${GEO_PATH}"
fi

log_step "6/12 Compute the Aversa high-resolution wind field"
if [[ "${NETWORK}" == "1" ]]; then
  "${PYTHON}" "${USECASE_DIR}/demo/step_02_prepare_domain.py" \
    --date 20240619Z1000 --hours 4 --download-dir "${WRF_DIR}" \
    --center-lat 40.9769 --center-lon 14.2168 \
    --nx 601 --ny 351 --dx 100 --dy 100 \
    --dem "${DEM_PATH}" --land-cover "${LAND_COVER_PATH}" \
    --advanced-physics --bulk-richardson-number 0.0 \
    --mass-consistency-iterations 80 --mass-consistency-relaxation 0.8 \
    --output "${METEO_PATH}"
else
  "${PYTHON}" "${SCRIPTS_DIR}/spritzmet.py" \
    --config "${CONFIG_PATH}" --output "${METEO_PATH}" --format netcdf
fi

log_step "7/12 Run Gaussian and particle dispersion for the three-hour event"
"${PYTHON}" "${SCRIPTS_DIR}/spritz.py" --config "${CONFIG_PATH}" --meteo "${METEO_PATH}" \
  --output "${GAUSSIAN_DIR}/concentration.nc" --format netcdf --backend gaussian --output-interval 3600
"${PYTHON}" "${SCRIPTS_DIR}/spritz.py" --config "${CONFIG_PATH}" --meteo "${METEO_PATH}" \
  --output "${PARTICLE_DIR}/concentration.nc" --format netcdf --backend particles \
  --seed 20240619 --output-interval 3600

log_step "8/12 Download primary TROPOMI NO2 and secondary UV Aerosol Index"
SATELLITE_DOWNLOADED=0
NO2_DOWNLOADED=0
if [[ "${NETWORK}" == "1" ]]; then
  if ! "${PYTHON}" tools/copernicus-s5p-download.py \
    --bbox 12.00 39.00 16.50 43.00 \
    --time-start 2024-06-19T11:34:07Z --time-end 2024-06-19T13:15:37Z \
    --band AER_AI_340_380 --min-qa 0 --width 256 --height 256 \
    --output "${SATELLITE_RAW}"; then
    if [[ "${ALLOW_SYNTHETIC_SATELLITE_FALLBACK}" == "1" ]]; then
      log_step "Sentinel-5P unavailable; using explicitly requested synthetic fallback"
      "${PYTHON}" "${SCRIPTS_DIR}/sprtz_satellite_mask.py" \
        --output "${SATELLITE_ALIGNED}" --width 11 --height 1
    else
      cat >&2 <<'EOF'
Sentinel-5P Aerosol Index is unavailable for the configured Aversa request.
The pipeline stops here to avoid presenting synthetic data as satellite
validation. Inspect the .request.json provenance, retry a documented wider
time/bbox window manually, or set SPRTZ_ALLOW_SYNTHETIC_SATELLITE_FALLBACK=1
to continue with the deterministic non-satellite demonstration mask.
EOF
      exit 2
    fi
  else
    SATELLITE_DOWNLOADED=1
  fi
  "${PYTHON}" tools/copernicus-s5p-download.py \
    --bbox 12.00 39.00 16.50 43.00 \
    --time-start 2024-06-19T11:34:07Z --time-end 2024-06-19T13:15:37Z \
    --band NO2 --min-qa 75 --width 256 --height 256 \
    --output "${SATELLITE_NO2_RAW}"
  NO2_DOWNLOADED=1
else
  "${PYTHON}" "${SCRIPTS_DIR}/sprtz_satellite_mask.py" \
    --output "${SATELLITE_ALIGNED}" --width 11 --height 1
fi

log_step "9/12 Conservatively downscale Aerosol Index to the Spritz domain"
if [[ "${SATELLITE_DOWNLOADED}" == "1" ]]; then
  "${PYTHON}" "${USECASE_DIR}/demo/step_03_align_satellite.py" \
    --satellite "${SATELLITE_RAW}" --config "${CONFIG_PATH}" \
    --station-observations "${STATION_OBSERVATIONS}" \
    --dem "${DEM_PATH}" --land-cover "${LAND_COVER_PATH}" \
    --satellite-time 2024-06-19T12:05:18Z --event-end 2024-06-19T13:00:00Z \
    --output "${SATELLITE_ALIGNED}"
fi

log_step "10/12 Plot original and downscaled Aerosol Index"
if [[ "${SATELLITE_DOWNLOADED}" == "1" ]]; then
  MPLBACKEND=Agg "${PYTHON}" "${USECASE_DIR}/demo/step_04_plot_satellite.py" \
    --satellite "${SATELLITE_RAW}" --downscaled "${SATELLITE_ALIGNED}" \
    --gaussian "${GAUSSIAN_DIR}/concentration.nc" \
    --particles "${PARTICLE_DIR}/concentration.nc" --model-time-index 1 \
    --config "${CONFIG_PATH}" --output "${FIGURE_DIR}/satellite_downscaling.png"
fi

log_step "11/12 Evaluate Gaussian and particle results"
for backend in gaussian particles; do
  if [[ "${NO2_DOWNLOADED}" == "1" ]]; then
    "${PYTHON}" "${USECASE_DIR}/demo/step_05_evaluate_no2.py" \
      --concentration "${OUT_DIR}/model/${backend}/concentration.nc" \
      --satellite-no2 "${SATELLITE_NO2_RAW}" --config "${CONFIG_PATH}" \
      --time-index 1 --output "${OUT_DIR}/model/${backend}/no2_column_evaluation.json"
  fi
  "${PYTHON}" "${SCRIPTS_DIR}/sprtz_satellite_evaluate.py" \
    --concentration "${OUT_DIR}/model/${backend}/concentration.nc" \
    --satellite-mask "${SATELLITE_ALIGNED}" \
    --output "${OUT_DIR}/model/${backend}/evaluation.json" --threshold 0.5 \
    --time-index 1 \
    --boundary-threshold-absolute 1e-15 \
    --boundary-threshold-relative 1e-12 \
    --boundary-mass-fraction-threshold 1e-6 \
    --model-unit ug_m3 --satellite-unit normalized_aerosol_index \
    --target-unit normalized_probability \
    --station-observations "${STATION_OBSERVATIONS}"
done

log_step "12/12 Plot Gaussian and particle concentration"
for backend in gaussian particles; do
  MPLBACKEND=Agg "${PYTHON}" "${SCRIPTS_DIR}/sprtz_plot.py" \
    --input "${OUT_DIR}/model/${backend}/concentration.nc" \
    --output "${FIGURE_DIR}/${backend}_concentration.png" \
    --title "Aversa ${backend} concentration" --dpi 300
done

log_step "Pipeline complete: ${OUT_DIR}"
