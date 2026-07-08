#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USECASE_DIR="$(cd "${PIPELINE_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${USECASE_DIR}/../.." && pwd)"
DATA_ROOT="${SPRTZ_DATA_ROOT:-${REPO_ROOT}/data}"
USECASE_NAME="$(basename "${USECASE_DIR}")"
OUTPUT_ROOT="${SPRTZ_OUTPUT_DIR:-${DATA_ROOT}/output/high_resolution_wind_field}"
WRF_DIR="${WRF_DIR:-${DATA_ROOT}/wrf/d03}"
DEM_PATH="${DEM_PATH:-${OUTPUT_ROOT}/dem/cop30_naples.tif}"
LANDUSE_PATH="${LANDUSE_PATH:-${OUTPUT_ROOT}/landcover/lc100_naples.tif}"
GEO_PATH="${GEO_PATH:-${OUTPUT_ROOT}/geo.nc}"
METEO_PATH="${METEO_PATH:-${OUTPUT_ROOT}/wrf_100m_wind_bbox.nc}"
TERRAIN_CACHE_DIR="${TERRAIN_CACHE_DIR:-${OUTPUT_ROOT}/terrain-cache}"
CONFIG_PATH="${CONFIG_PATH:-${REPO_ROOT}/usecases/01_high_resolution_wind_field/demo/config.json}"
MPLCONFIGDIR="${MPLCONFIGDIR:-${OUTPUT_ROOT}/.matplotlib}"

DATE_UTC="${DATE_UTC:-20260621Z0000}"
HOURS="${HOURS:-24}"
SOUTH="${SOUTH:-40.78}"
NORTH="${NORTH:-40.85}"
WEST="${WEST:-14.18}"
EAST="${EAST:-14.33}"
DX="${DX:-100}"
DY="${DY:-100}"
BUFFER_M="${BUFFER_M:-5000}"
PLOT_DPI="${PLOT_DPI:-600}"
VECTOR_DENSITY="${VECTOR_DENSITY:-50}"
PROFILE_DURATION_MS="${PROFILE_DURATION_MS:-400}"
RENDER3D_DURATION_MS="${RENDER3D_DURATION_MS:-400}"
VERTICAL_EXAGGERATION="${VERTICAL_EXAGGERATION:-5}"
COASTLINE_SOURCE="${COASTLINE_SOURCE:-gshhs}"
COASTLINE_RESOLUTION="${COASTLINE_RESOLUTION:-10m}"
ALLOW_CARTOPY_DOWNLOAD="${ALLOW_CARTOPY_DOWNLOAD:-1}"

mkdir -p "${OUTPUT_ROOT}" "${WRF_DIR}" "$(dirname "${DEM_PATH}")" "$(dirname "${LANDUSE_PATH}")" "${TERRAIN_CACHE_DIR}" "${MPLCONFIGDIR}"
cd "${REPO_ROOT}"
export MPLCONFIGDIR

log_step() {
  printf '\n[%s] %s\n' "${USECASE_NAME}" "$1"
}

plotter_download_args=()
if [[ "${ALLOW_CARTOPY_DOWNLOAD}" == "1" ]]; then
  plotter_download_args+=(--allow-cartopy-download)
fi

log_step "1. Download 24 hourly WRF d03 files for Velalonga 2026"
python tools/meteouniparthenope-wrf-download.py "${DATE_UTC}" \
  --hours "${HOURS}" \
  --domain d03 \
  --data-root "${WRF_DIR}"

log_step "2. Download buffered COP30 DEM"
python tools/copernicus-cop30-dem-download.py \
  --south "${SOUTH}" --north "${NORTH}" --west "${WEST}" --east "${EAST}" \
  --dx "${DX}" \
  --dy "${DY}" \
  --buffer-m "${BUFFER_M}" \
  --output "${DEM_PATH}"

log_step "3. Download buffered Copernicus LC100 land cover"
python tools/copernicus-lc100-download.py \
  --south "${SOUTH}" --north "${NORTH}" --west "${WEST}" --east "${EAST}" \
  --dx "${DX}" \
  --dy "${DY}" \
  --buffer-m "${BUFFER_M}" \
  --output "${LANDUSE_PATH}"

log_step "4. Build terrain/GEO product with automatic nx/ny"
sprtz-terrain fetch \
  --south "${SOUTH}" --north "${NORTH}" --west "${WEST}" --east "${EAST}" \
  --dx "${DX}" \
  --dy "${DY}" \
  --dem "${DEM_PATH}" \
  --landuse "${LANDUSE_PATH}" \
  --landuse-mapping copernicus-lc100 \
  --cache-dir "${TERRAIN_CACHE_DIR}" \
  --output "${GEO_PATH}"

log_step "5. Compute the 24-hour Velalonga downscaled wind field"
python usecases/01_high_resolution_wind_field/demo/step_01_downscale_wind.py \
  --date "${DATE_UTC}" \
  --hours "${HOURS}" \
  --download-dir "${WRF_DIR}/" \
  --output "${METEO_PATH}" \
  --south "${SOUTH}" --north "${NORTH}" --west "${WEST}" --east "${EAST}" \
  --dx "${DX}" --dy "${DY}" \
  --config "${CONFIG_PATH}" \
  --dem "${DEM_PATH}" \
  --land-cover "${LANDUSE_PATH}" \
  --parallel auto

log_step "6. Render six 10 m wind maps for Z0900 through Z1400"
for hour in 09 10 11 12 13 14; do
  index=$((10#${hour}))
  MPLBACKEND=Agg python tools/plotter.py \
    "${METEO_PATH}" \
    --variable wind_speed_10m \
    --time-index "${index}" \
    --vector-density "${VECTOR_DENSITY}" \
    --coastline-source "${COASTLINE_SOURCE}" \
    --coastline-resolution "${COASTLINE_RESOLUTION}" \
    "${plotter_download_args[@]}" \
    --title "Velalonga 2026 — ${DATE_UTC:0:8}Z${hour}00 — wind at 10 m AGL" \
    --dpi "${PLOT_DPI}" \
    --output "${OUTPUT_ROOT}/velalonga_wind_10m_${DATE_UTC:0:8}Z${hour}00.png"
done

log_step "7. Render the animated central vertical profile"
MPLBACKEND=Agg python tools/profiler.py \
  "${METEO_PATH}" \
  --variable wind_speed \
  --x 0 \
  --y 0 \
  --animate \
  --frame-duration-ms "${PROFILE_DURATION_MS}" \
  --gif-loop 0 \
  --title "Velalonga 2026 — central Bay of Naples vertical wind profile" \
  --output "${OUTPUT_ROOT}/velalonga_vertical_profile.gif"

log_step "8. Render the animated terrain-aware 3-D wind field"
MPLBACKEND=Agg python tools/render3d.py \
  "${METEO_PATH}" \
  --variable wind_speed \
  --terrain "${GEO_PATH}" \
  --mode surface \
  --ground-color terrain \
  --vertical-exaggeration "${VERTICAL_EXAGGERATION}" \
  --animate \
  --frame-duration-ms "${RENDER3D_DURATION_MS}" \
  --gif-loop 0 \
  --title "Velalonga 2026 — 3-D wind speed, terrain ×${VERTICAL_EXAGGERATION}" \
  --output "${OUTPUT_ROOT}/velalonga_wind_3d_terrain_x${VERTICAL_EXAGGERATION}.gif"

log_step "9. Render the 3-D vector field at 20260621Z1200"
MPLBACKEND=Agg python tools/render3d.py \
  "${METEO_PATH}" \
  --variable wind_speed \
  --time-index 12 \
  --terrain "${GEO_PATH}" \
  --mode quiver \
  --max-points 18 \
  --ground-color terrain \
  --vertical-exaggeration "${VERTICAL_EXAGGERATION}" \
  --title "Velalonga 2026 — 3-D wind vectors — 20260621Z1200" \
  --output "${OUTPUT_ROOT}/velalonga_wind_vectors_3d_20260621Z1200.png"

log_step "10. Render the wind-speed voxel view at 20260621Z1200"
MPLBACKEND=Agg python tools/render3d.py \
  "${METEO_PATH}" \
  --variable wind_speed \
  --time-index 12 \
  --terrain "${GEO_PATH}" \
  --mode voxel \
  --threshold-quantile 0.85 \
  --ground-color terrain \
  --vertical-exaggeration "${VERTICAL_EXAGGERATION}" \
  --title "Velalonga 2026 — wind-speed voxels — 20260621Z1200" \
  --output "${OUTPUT_ROOT}/velalonga_wind_voxels_20260621Z1200.png"

log_step "Pipeline complete: ${OUTPUT_ROOT}"
