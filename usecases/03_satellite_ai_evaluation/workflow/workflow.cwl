cwlVersion: v1.2
class: Workflow
label: Sprtz satellite and AI evaluation pipeline
doc: CWL wrapper for the canonical use case 03 shell pipeline.

requirements:
  InlineJavascriptRequirement: {}

inputs:
  repo_root: Directory
  sprtz_data_root:
    type: string?
    default: null
  sprtz_output_dir:
    type: string?
    default: null
  python:
    type: string
    default: python3
  threshold:
    type: float
    default: 0.5

outputs:
  output_root:
    type: Directory?
    outputSource: run_pipeline/output_root
  concentration:
    type: File?
    outputSource: run_pipeline/concentration
  satellite_mask:
    type: File?
    outputSource: run_pipeline/satellite_mask
  satellite_no2:
    type: File?
    outputSource: run_pipeline/satellite_no2
  evaluation:
    type: File?
    outputSource: run_pipeline/evaluation
  no2_column_evaluation:
    type: File?
    outputSource: run_pipeline/no2_column_evaluation
  difference:
    type: File?
    outputSource: run_pipeline/difference
  ratio:
    type: File?
    outputSource: run_pipeline/ratio
  statistics:
    type: File?
    outputSource: run_pipeline/statistics
  figure:
    type: File?
    outputSource: run_pipeline/figure

steps:
  run_pipeline:
    in:
      repo_root: repo_root
      sprtz_data_root: sprtz_data_root
      sprtz_output_dir: sprtz_output_dir
      python: python
      threshold: threshold
    out: [output_root, concentration, satellite_mask, satellite_no2, evaluation, no2_column_evaluation, difference, ratio, statistics, figure]
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
            THRESHOLD: $(inputs.threshold.toString())
      inputs:
        repo_root: Directory
        sprtz_data_root: string?
        sprtz_output_dir: string?
        python: string
        threshold: float
      baseCommand: bash
      arguments:
        - -c
        - |
          set -euo pipefail
          cd "$0"
          bash usecases/03_satellite_ai_evaluation/pipeline/pipeline.sh
        - $(inputs.repo_root.path)
      outputs:
        output_root:
          type: Directory?
          outputBinding:
            glob: $(inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/03_satellite_ai_evaluation")
        concentration:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/03_satellite_ai_evaluation") + "/model/gaussian/concentration.nc")
        satellite_mask:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/03_satellite_ai_evaluation") + "/satellite/sentinel5p_aer_ai_downscaled.json")
        satellite_no2:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/03_satellite_ai_evaluation") + "/satellite/sentinel5p_no2_20240619T120518Z_full_orbit.tif")
        evaluation:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/03_satellite_ai_evaluation") + "/model/gaussian/evaluation.json")
        no2_column_evaluation:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/03_satellite_ai_evaluation") + "/model/gaussian/no2_column_evaluation.json")
        difference:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/03_satellite_ai_evaluation") + "/model/gaussian/evaluation_difference.json")
        ratio:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/03_satellite_ai_evaluation") + "/model/gaussian/evaluation_ratio.json")
        statistics:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/03_satellite_ai_evaluation") + "/model/gaussian/evaluation_stats.csv")
        figure:
          type: File?
          outputBinding:
            glob: $((inputs.sprtz_output_dir || (inputs.sprtz_data_root || inputs.repo_root.path + "/data") + "/03_satellite_ai_evaluation") + "/figures/gaussian_concentration.png")
