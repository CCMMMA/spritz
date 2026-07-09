# Use case 03 — CWL workflow

[`workflow.cwl`](workflow.cwl) is a CWL v1.2 wrapper around the canonical
[`pipeline.sh`](../pipeline/pipeline.sh). It exposes the interpreter, output
locations, and classification threshold as typed inputs and returns the model
concentration, satellite mask, evaluation report, difference and ratio grids,
statistics CSV, and figure.

Create a job file:

```yaml
repo_root:
  class: Directory
  path: ../../..
sprtz_output_dir: data/03_satellite_ai_evaluation_cwl
threshold: 0.5
```

Run it from the repository root:

```bash
cwltool \
  usecases/03_satellite_ai_evaluation/workflow/workflow.cwl \
  usecases/03_satellite_ai_evaluation/workflow/job.yml
```

The runner must provide Bash, Python 3.10 or newer, Sprtz, and the `netcdf` and
`viz` optional dependencies. The workflow performs no hidden network access.
The shell pipeline remains the executable source of truth so its command order
and CWL behavior cannot drift.

## References

No additional bibliographic references are required. Scientific assumptions
are documented in the use-case demo and Sprtz numerical documentation.
