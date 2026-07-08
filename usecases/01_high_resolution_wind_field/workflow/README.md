# 01 High Resolution Wind Field CWL Workflow

`workflow.cwl` is a Common Workflow Language wrapper for the shell pipeline in
`../pipeline/pipeline.sh`. The shell pipeline remains the canonical executable
sequence: it downloads WRF forcing, prepares buffered COP30 and LC100 rasters,
builds the GEO terrain product, runs the SpritzWRF -> SpritzMet downscaling
driver, and renders the 2-D, profile, and 3-D visualization products.

The CWL workflow intentionally delegates to `pipeline.sh` instead of duplicating
the ten scientific and rendering commands. This keeps workflow-engine execution
aligned with the maintained operational wrapper.

## Inputs

The workflow requires one input:

- `repo_root`: a CWL `Directory` pointing at the Sprtz repository checkout.

Optional inputs mirror the environment variables accepted by `pipeline.sh`:

- path controls: `sprtz_data_root`, `sprtz_output_dir`, `wrf_dir`, `dem_path`,
  `landuse_path`, `geo_path`, `meteo_path`, `terrain_cache_dir`, `config_path`,
  and `mplconfigdir`;
- scenario controls: `date_utc`, `hours`, `south`, `north`, `west`, `east`,
  `dx`, `dy`, and `buffer_m`;
- rendering controls: `plot_dpi`, `vector_density`, `profile_duration_ms`,
  `render3d_duration_ms`, `vertical_exaggeration`, `coastline_source`,
  `coastline_resolution`, and `allow_cartopy_download`.

Defaults match `../pipeline/pipeline.sh`: the Velalonga 2026 scenario starts at
`20260621Z0000`, runs for `24` hours, uses the Bay of Naples bounding box, and
writes under `data/output/high_resolution_wind_field/` unless paths are
overridden.

## Example job file

```yaml
repo_root:
  class: Directory
  path: ../../..
date_utc: "20260621Z0000"
hours: 24
allow_cartopy_download: 1
```

Run from this directory with a CWL runner such as `cwltool`:

```bash
cwltool workflow.cwl job.yml
```

The command must run in an environment where the Sprtz package, optional
NetCDF/visualization dependencies, downloader requirements, and command-line
tools used by `pipeline.sh` are available.

## Outputs

The workflow exposes the main products written by the pipeline:

- `output_root`;
- `geo`;
- `meteo`;
- `wind_maps`;
- `vertical_profile`;
- `terrain_3d_animation`;
- `vector_3d_frame`;
- `voxel_3d_frame`.

The pipeline also writes intermediate DEM, land-cover, WRF, cache, and
Matplotlib files in the configured output and data directories.

## Notes

The workflow uses the same clean-room, terrain-aware SpritzWRF -> SpritzMet path
as the shell pipeline and demo. It requires explicit network access for WRF,
COP30, LC100, and optional Cartopy coastline downloads. The generated 100 m
wind field is a deterministic downscaling diagnostic and is not a regulatory or
official operational forecast product.
