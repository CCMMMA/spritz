cwlVersion: v1.2
class: Workflow
label: Sprtz high-resolution wind field pipeline
doc: |
  CWL wrapper for usecases/01_high_resolution_wind_field/pipeline/pipeline.sh.

  The shell pipeline remains the canonical operational command sequence. This
  workflow exposes the same main environment overrides so a CWL runner can bind
  scenario, data, terrain, meteorology, and visualization paths while preserving
  the SpritzWRF -> SpritzMet pipeline order implemented by pipeline.sh.

requirements:
  InlineJavascriptRequirement: {}
  StepInputExpressionRequirement: {}

inputs:
  repo_root:
    type: Directory
    doc: Repository root containing the Sprtz checkout.
  sprtz_data_root:
    type: string?
    default: null
    doc: Optional repository data root override.
  sprtz_output_dir:
    type: string?
    default: null
    doc: Optional exact output directory for terrain, NetCDF, and rendered products.
  wrf_dir:
    type: string?
    default: null
    doc: Optional WRF d03 download directory.
  dem_path:
    type: string?
    default: null
    doc: Optional buffered COP30 DEM output path.
  landuse_path:
    type: string?
    default: null
    doc: Optional buffered Copernicus LC100 land-cover output path.
  geo_path:
    type: string?
    default: null
    doc: Optional terrain/GEO NetCDF output path.
  meteo_path:
    type: string?
    default: null
    doc: Optional downscaled SpritzMet NetCDF output path.
  terrain_cache_dir:
    type: string?
    default: null
    doc: Optional terrain cache directory.
  config_path:
    type: string?
    default: null
    doc: Optional SpritzMet configuration JSON path.
  mplconfigdir:
    type: string?
    default: null
    doc: Optional Matplotlib configuration/cache directory.
  date_utc:
    type: string
    default: "20260621Z0000"
    doc: Scenario start time in compact UTC format YYYYMMDDZhhmm.
  hours:
    type: int
    default: 24
  south:
    type: float
    default: 40.78
  north:
    type: float
    default: 40.85
  west:
    type: float
    default: 14.18
  east:
    type: float
    default: 14.33
  dx:
    type: int
    default: 100
  dy:
    type: int
    default: 100
  buffer_m:
    type: int
    default: 5000
  plot_dpi:
    type: int
    default: 600
  vector_density:
    type: int
    default: 50
  profile_duration_ms:
    type: int
    default: 400
  render3d_duration_ms:
    type: int
    default: 400
  vertical_exaggeration:
    type: float
    default: 5
  coastline_source:
    type: string
    default: gshhs
  coastline_resolution:
    type: string
    default: 10m
  allow_cartopy_download:
    type: int
    default: 1

outputs:
  output_root:
    type: Directory?
    outputSource: run_pipeline/output_root
  geo:
    type: File?
    outputSource: run_pipeline/geo
  meteo:
    type: File?
    outputSource: run_pipeline/meteo
  wind_maps:
    type:
      type: array
      items: File
    outputSource: run_pipeline/wind_maps
  vertical_profile:
    type: File?
    outputSource: run_pipeline/vertical_profile
  terrain_3d_animation:
    type: File?
    outputSource: run_pipeline/terrain_3d_animation
  vector_3d_frame:
    type: File?
    outputSource: run_pipeline/vector_3d_frame
  voxel_3d_frame:
    type: File?
    outputSource: run_pipeline/voxel_3d_frame

steps:
  run_pipeline:
    in:
      repo_root: repo_root
      sprtz_data_root: sprtz_data_root
      sprtz_output_dir: sprtz_output_dir
      wrf_dir: wrf_dir
      dem_path: dem_path
      landuse_path: landuse_path
      geo_path: geo_path
      meteo_path: meteo_path
      terrain_cache_dir: terrain_cache_dir
      config_path: config_path
      mplconfigdir: mplconfigdir
      date_utc: date_utc
      hours: hours
      south: south
      north: north
      west: west
      east: east
      dx: dx
      dy: dy
      buffer_m: buffer_m
      plot_dpi: plot_dpi
      vector_density: vector_density
      profile_duration_ms: profile_duration_ms
      render3d_duration_ms: render3d_duration_ms
      vertical_exaggeration: vertical_exaggeration
      coastline_source: coastline_source
      coastline_resolution: coastline_resolution
      allow_cartopy_download: allow_cartopy_download
    out:
      - output_root
      - geo
      - meteo
      - wind_maps
      - vertical_profile
      - terrain_3d_animation
      - vector_3d_frame
      - voxel_3d_frame
    run:
      class: CommandLineTool
      requirements:
        ShellCommandRequirement: {}
        InlineJavascriptRequirement: {}
        EnvVarRequirement:
          envDef:
            SPRTZ_DATA_ROOT: $(inputs.sprtz_data_root || "")
            SPRTZ_OUTPUT_DIR: $(inputs.sprtz_output_dir || "")
            WRF_DIR: $(inputs.wrf_dir || "")
            DEM_PATH: $(inputs.dem_path || "")
            LANDUSE_PATH: $(inputs.landuse_path || "")
            GEO_PATH: $(inputs.geo_path || "")
            METEO_PATH: $(inputs.meteo_path || "")
            TERRAIN_CACHE_DIR: $(inputs.terrain_cache_dir || "")
            CONFIG_PATH: $(inputs.config_path || "")
            MPLCONFIGDIR: $(inputs.mplconfigdir || "")
            DATE_UTC: $(inputs.date_utc)
            HOURS: $(inputs.hours.toString())
            SOUTH: $(inputs.south.toString())
            NORTH: $(inputs.north.toString())
            WEST: $(inputs.west.toString())
            EAST: $(inputs.east.toString())
            DX: $(inputs.dx.toString())
            DY: $(inputs.dy.toString())
            BUFFER_M: $(inputs.buffer_m.toString())
            PLOT_DPI: $(inputs.plot_dpi.toString())
            VECTOR_DENSITY: $(inputs.vector_density.toString())
            PROFILE_DURATION_MS: $(inputs.profile_duration_ms.toString())
            RENDER3D_DURATION_MS: $(inputs.render3d_duration_ms.toString())
            VERTICAL_EXAGGERATION: $(inputs.vertical_exaggeration.toString())
            COASTLINE_SOURCE: $(inputs.coastline_source)
            COASTLINE_RESOLUTION: $(inputs.coastline_resolution)
            ALLOW_CARTOPY_DOWNLOAD: $(inputs.allow_cartopy_download.toString())
      inputs:
        repo_root: Directory
        sprtz_data_root: string?
        sprtz_output_dir: string?
        wrf_dir: string?
        dem_path: string?
        landuse_path: string?
        geo_path: string?
        meteo_path: string?
        terrain_cache_dir: string?
        config_path: string?
        mplconfigdir: string?
        date_utc: string
        hours: int
        south: float
        north: float
        west: float
        east: float
        dx: int
        dy: int
        buffer_m: int
        plot_dpi: int
        vector_density: int
        profile_duration_ms: int
        render3d_duration_ms: int
        vertical_exaggeration: float
        coastline_source: string
        coastline_resolution: string
        allow_cartopy_download: int
      baseCommand: bash
      arguments:
        - -c
        - |
          set -euo pipefail
          cd "$0"
          bash usecases/01_high_resolution_wind_field/pipeline/pipeline.sh
        - $(inputs.repo_root.path)
      outputs:
        output_root:
          type: Directory?
          outputBinding:
            glob: $(inputs.sprtz_output_dir || inputs.repo_root.path + "/data/output/high_resolution_wind_field")
        geo:
          type: File?
          outputBinding:
            glob: $(inputs.geo_path || inputs.repo_root.path + "/data/output/high_resolution_wind_field/geo.nc")
        meteo:
          type: File?
          outputBinding:
            glob: $(inputs.meteo_path || inputs.repo_root.path + "/data/output/high_resolution_wind_field/wrf_100m_wind_bbox.nc")
        wind_maps:
          type:
            type: array
            items: File
          outputBinding:
            glob: $((inputs.sprtz_output_dir || inputs.repo_root.path + "/data/output/high_resolution_wind_field") + "/velalonga_wind_10m_" + inputs.date_utc.slice(0, 8) + "Z*.png")
        vertical_profile:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || inputs.repo_root.path + "/data/output/high_resolution_wind_field") + "/velalonga_vertical_profile.gif")
        terrain_3d_animation:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || inputs.repo_root.path + "/data/output/high_resolution_wind_field") + "/velalonga_wind_3d_terrain_x" + inputs.vertical_exaggeration + ".gif")
        vector_3d_frame:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || inputs.repo_root.path + "/data/output/high_resolution_wind_field") + "/velalonga_wind_vectors_3d_20260621Z1200.png")
        voxel_3d_frame:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || inputs.repo_root.path + "/data/output/high_resolution_wind_field") + "/velalonga_wind_voxels_20260621Z1200.png")
