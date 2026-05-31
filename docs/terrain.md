# Terrain Preprocessing

Terrain is the clean-room Sprtz component for preparing terrain elevations on the Sprtz modeling grid and for downstream SpritzMet, MakeGeo, and dispersion workflows.

## Responsibilities

Terrain provides four production tasks:

1. read a terrain raster, currently lightweight ASCII grid input for repository tests and examples;
2. construct the same local azimuthal-equidistant grid convention used by SpritzMet;
3. interpolate terrain elevations to that local grid with deterministic bilinear interpolation;
4. write a NetCDF-CF terrain product by preference, or JSON when NetCDF support is not installed.

## Command-line use

```bash
terrain \
  --terrain examples/terrain.asc \
  --output output/terrain.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 --ny 101 \
  --dx 100 --dy 100
```

Use `--json` to force the lightweight JSON fallback:

```bash
terrain --terrain examples/terrain.asc --output output/terrain.json \
  --center-lat 40.85 --center-lon 14.27 --json
```

## Python API

```python
from sprtz.models import terrain

result = terrain.run(
    "examples/terrain.asc",
    "output/terrain.nc",
    center_lat=40.85,
    center_lon=14.27,
    nx=101,
    ny=101,
    dx_m=100.0,
    dy_m=100.0,
)
```

## Interoperability

The NetCDF-CF output contains:

- `x`, `y` local grid coordinates in metres;
- `latitude`, `longitude` geographic coordinates;
- `surface_altitude` terrain elevation in metres.

This makes the product directly usable by SpritzMet, MakeGeo-style geophysical tables, visualization, and future terrain-aware dispersion refinements.

## Production notes

The current Terrain implementation is intentionally conservative and deterministic. For operational terrain deployments, use a documented DEM source and record its horizontal datum, vertical datum, native resolution, and preprocessing steps. The example ASCII-grid reader is suitable for tutorials and small tests; production deployments should add project-specific DEM adapters under the same clean-room boundary.
