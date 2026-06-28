# meteo@uniparthenope WRF downloader

`tools/meteouniparthenope-wrf-download` downloads WRF5 history NetCDF files from
the meteo@uniparthenope archive into the repository data tree. It is a
miscellaneous developer/operator tool, not an installed `sprtz` console command.

The script uses only the Python standard library, logs operational messages with
`logging`, writes each file through a temporary `.part` file, and reuses existing
non-empty files unless `--force` is supplied.

## URL pattern

The downloader builds one URL per requested hour:

```text
https://data.meteo.uniparthenope.it/files/wrf5/<domain>/history/YYYY/MM/DD/wrf5_<domain>_YYYYMMDDZhhmm.nc
```

Supported domains are:

- `d01`
- `d02`
- `d03`

The timestamp argument must use `YYYYMMDDZhhmm`, for example `20260628Z0000`.

## Basic usage

Run the script from the repository root:

```bash
tools/meteouniparthenope-wrf-download.py 20260628Z0000 --hours 24 --domain d03
```

This requests 24 hourly files starting at `2026-06-28 00:00`, using domain
`d03`. By default, files are written under:

```text
data/wrf/d03/
```

The first and last target file names for the example are:

```text
data/wrf/d03/wrf5_d03_20260628Z0000.nc
data/wrf/d03/wrf5_d03_20260628Z2300.nc
```

## Dry run

Use `--dry-run` to inspect URLs and target paths without downloading:

```bash
tools/meteouniparthenope-wrf-download.py 20260628Z0000 --hours 24 --domain d03 --dry-run
```

The script logs entries in this form:

```text
INFO https://data.meteo.uniparthenope.it/files/wrf5/d03/history/2026/06/28/wrf5_d03_20260628Z0000.nc -> data/wrf/d03/wrf5_d03_20260628Z0000.nc
```

## Options

`date`
: Required positional argument. Start timestamp in `YYYYMMDDZhhmm` format.

`--hours HOURS`
: Required. Number of hourly files to request. Must be at least `1`.

`--domain DOMAIN`
: Required. WRF domain to download. Must be `d01`, `d02`, or `d03`.

`--data-root PATH`
: Root directory for downloaded data. Defaults to `data`, so files go to
  `data/wrf/<domain>/`. Use this only when a workflow explicitly needs a
  different data root.

`--timeout-s SECONDS`
: Per-file network timeout. Defaults to `120.0`.

`--workers WORKERS`
: Number of parallel download workers. Defaults to `1` for serial downloads.
  Increase this for long windows when the archive and local network can tolerate
  concurrent requests.

`--force`
: Download files even when a non-empty target file already exists.

`--dry-run`
: Log planned URLs and output paths without making network requests or writing
  files.

`--verbose`
: Enable debug-level logging.

## Output and overwrite behavior

For each hour, the script:

1. Builds the archive URL from the timestamp and domain.
2. Creates `data/wrf/<domain>/` or the equivalent directory under `--data-root`.
3. Skips an existing non-empty target file unless `--force` is set.
4. Downloads to `<filename>.nc.part`.
5. Atomically replaces the final `.nc` file when the download succeeds.

With `--workers` greater than `1`, multiple files are downloaded concurrently.
Each file still uses its own temporary `.part` file and final atomic replace.

If a download fails, the partial `.part` file is removed and the script exits
with status `1`.

## Examples

Download one day of `d03` history files:

```bash
tools/meteouniparthenope-wrf-download.py 20260628Z0000 --hours 24 --domain d03
```

Preview the same download:

```bash
tools/meteouniparthenope-wrf-download.py 20260628Z0000 --hours 24 --domain d03 --dry-run
```

Download six hours of `d02` history files into the default data root:

```bash
tools/meteouniparthenope-wrf-download.py 20260628Z0600 --hours 6 --domain d02
```

Refresh files that already exist:

```bash
tools/meteouniparthenope-wrf-download.py 20260628Z0000 --hours 24 --domain d03 --force
```

Download one day using four parallel workers:

```bash
tools/meteouniparthenope-wrf-download.py 20260628Z0000 --hours 24 --domain d03 --workers 4
```

Download into a custom root:

```bash
tools/meteouniparthenope-wrf-download.py 20260628Z0000 --hours 24 --domain d03 --data-root /tmp/sprtz-wrf
```

## Relationship to SpritzWRF

Downloaded NetCDF files can be read by `sprtz.models.spritzwrf` and used in the
SpritzWRF to SpritzMet workflow. For example, after the 24-hour `d03` download:

```python
from sprtz.models import spritzwrf

wrf = spritzwrf.load_near_surface_wind(
    "data/wrf/d03/wrf5_d03_20260628Z0000.nc",
    time_index=0,
    level_index=0,
)
```

For four-dimensional WRF wind variables, SpritzWRF treats the axes as
`time,level,y,x` when WRF/CF dimension names are available. Surface
precipitation-rate products are carried as `time,y,x` in downstream
SpritzMet NetCDF files.

See `docs/spritzwrf_spritzmet.md` for the clean-room WRF ingestion and
meteorological interpolation workflow.

## Troubleshooting

- `date must use YYYYMMDDZhhmm`: check the timestamp format, including the `Z`.
- `domain must be one of d01, d02, d03`: choose one of the supported WRF domains.
- HTTP or timeout errors usually mean the requested archive file is unavailable,
  the network is unavailable, or the remote service did not respond before
  `--timeout-s`.
- Use `--dry-run` first when validating long download windows.
