cwlVersion: v1.2
class: Workflow
label: Spritz wildfire/arson scripts-only pipeline
doc: |
  CWL wrapper for usecases/02_wildfire_arson_effects/pipeline/pipeline.sh.
  The shell pipeline remains the canonical command sequence.

requirements:
  InlineJavascriptRequirement: {}
  StepInputExpressionRequirement: {}

inputs:
  repo_root:
    type: Directory
    doc: Repository root containing the Spritz checkout.
  sprtz_data_root:
    type: string?
    default: null
  sprtz_output_dir:
    type: string?
    default: null
  python:
    type: string
    default: python3
  nx:
    type: int
    default: 31
  ny:
    type: int
    default: 31
  dx:
    type: float
    default: 100
  dy:
    type: float
    default: 100
  wind_speed_m_s:
    type: float
    default: 4.0
  wind_from_direction_deg:
    type: float
    default: 270.0
  temperature_k:
    type: float
    default: 298.0
  mixing_height_m:
    type: float
    default: 1000.0
  precipitation_rate_mm_h:
    type: float
    default: 0.2
  emission_rate_g_s:
    type: float
    default: 35.0
  source_x_m:
    type: float
    default: 1500.0
  source_y_m:
    type: float
    default: 1500.0
  source_height_m:
    type: float
    default: 10.0
  particle_seed:
    type: int
    default: 1234
  output_interval_s:
    type: float
    default: 3600

outputs:
  output_root:
    type: Directory?
    outputSource: run_pipeline/output_root
  config:
    type: File?
    outputSource: run_pipeline/config
  meteo:
    type: File?
    outputSource: run_pipeline/meteo
  gaussian_concentration:
    type: File?
    outputSource: run_pipeline/gaussian_concentration
  particle_concentration:
    type: File?
    outputSource: run_pipeline/particle_concentration
  gaussian_post:
    type: File?
    outputSource: run_pipeline/gaussian_post
  particle_post:
    type: File?
    outputSource: run_pipeline/particle_post
  gaussian_figure:
    type: File?
    outputSource: run_pipeline/gaussian_figure
  particle_figure:
    type: File?
    outputSource: run_pipeline/particle_figure

steps:
  run_pipeline:
    in:
      repo_root: repo_root
      sprtz_data_root: sprtz_data_root
      sprtz_output_dir: sprtz_output_dir
      python: python
      nx: nx
      ny: ny
      dx: dx
      dy: dy
      wind_speed_m_s: wind_speed_m_s
      wind_from_direction_deg: wind_from_direction_deg
      temperature_k: temperature_k
      mixing_height_m: mixing_height_m
      precipitation_rate_mm_h: precipitation_rate_mm_h
      emission_rate_g_s: emission_rate_g_s
      source_x_m: source_x_m
      source_y_m: source_y_m
      source_height_m: source_height_m
      particle_seed: particle_seed
      output_interval_s: output_interval_s
    out:
      - output_root
      - config
      - meteo
      - gaussian_concentration
      - particle_concentration
      - gaussian_post
      - particle_post
      - gaussian_figure
      - particle_figure
    run:
      class: CommandLineTool
      requirements:
        ShellCommandRequirement: {}
        InlineJavascriptRequirement: {}
        EnvVarRequirement:
          envDef:
            SPRTZ_DATA_ROOT: $(inputs.sprtz_data_root || "")
            SPRTZ_OUTPUT_DIR: $(inputs.sprtz_output_dir || "")
            PYTHON: $(inputs.python)
            NX: $(inputs.nx.toString())
            NY: $(inputs.ny.toString())
            DX: $(inputs.dx.toString())
            DY: $(inputs.dy.toString())
            WIND_SPEED_M_S: $(inputs.wind_speed_m_s.toString())
            WIND_FROM_DIRECTION_DEG: $(inputs.wind_from_direction_deg.toString())
            TEMPERATURE_K: $(inputs.temperature_k.toString())
            MIXING_HEIGHT_M: $(inputs.mixing_height_m.toString())
            PRECIPITATION_RATE_MM_H: $(inputs.precipitation_rate_mm_h.toString())
            EMISSION_RATE_G_S: $(inputs.emission_rate_g_s.toString())
            SOURCE_X_M: $(inputs.source_x_m.toString())
            SOURCE_Y_M: $(inputs.source_y_m.toString())
            SOURCE_HEIGHT_M: $(inputs.source_height_m.toString())
            PARTICLE_SEED: $(inputs.particle_seed.toString())
            OUTPUT_INTERVAL_S: $(inputs.output_interval_s.toString())
      inputs:
        repo_root: Directory
        sprtz_data_root: string?
        sprtz_output_dir: string?
        python: string
        nx: int
        ny: int
        dx: float
        dy: float
        wind_speed_m_s: float
        wind_from_direction_deg: float
        temperature_k: float
        mixing_height_m: float
        precipitation_rate_mm_h: float
        emission_rate_g_s: float
        source_x_m: float
        source_y_m: float
        source_height_m: float
        particle_seed: int
        output_interval_s: float
      baseCommand: bash
      arguments:
        - -c
        - |
          set -euo pipefail
          cd "$0"
          bash usecases/02_wildfire_arson_effects/pipeline/pipeline.sh
        - $(inputs.repo_root.path)
      outputs:
        output_root:
          type: Directory?
          outputBinding:
            glob: $(inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/output/wildfire_case")
        config:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/output/wildfire_case") + "/wildfire_event.json")
        meteo:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/output/wildfire_case") + "/meteo.nc")
        gaussian_concentration:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/output/wildfire_case") + "/model_compare/gaussian/concentration.nc")
        particle_concentration:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/output/wildfire_case") + "/model_compare/particles/concentration.nc")
        gaussian_post:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/output/wildfire_case") + "/model_compare/gaussian/post.json")
        particle_post:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/output/wildfire_case") + "/model_compare/particles/post.json")
        gaussian_figure:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/output/wildfire_case") + "/figures/gaussian_concentration.png")
        particle_figure:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/output/wildfire_case") + "/figures/particle_concentration.png")
