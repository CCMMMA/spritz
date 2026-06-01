# Examples

`minimal.json` and `minimal.inp` describe the same synthetic domain: a 5 x 4 local grid, two stations, one point source, and two receptors.

Recommended interoperability workflow uses NetCDF-CF:

```bash
sprtz run examples/minimal.json --output-dir output --interchange netcdf
sprtz run examples/minimal.inp --output-dir output-particles --backend particles --interchange netcdf
sprtz-plot --input output/concentration.nc --output output/concentration.png
```

High-resolution Terrain examples:

```bash
sprtz-terrain fetch --config examples/highres_terrain_local.json --json
sprtz run examples/highres_terrain_local.json --output-dir output-terrain-local --interchange json
sprtz-terrain fetch --config examples/highres_terrain_auto.json --allow-network
```

`highres_terrain_local.json` is the offline CI-safe example. `highres_terrain_auto.json`
documents the Copernicus DEM and ESA WorldCover provider configuration and
requires explicit network/provider access.

Legacy-compatible text/CSV workflow is still available:

```bash
spritzmet --config examples/minimal.inp --output output/meteo.json --format json
spritz --config examples/minimal.inp --meteo output/meteo.json --output output/concentration.csv --format csv
sprtz-particles --config examples/minimal.inp --meteo output/meteo.json --output output/particle_concentration.csv --format csv
spritzpost --input output/concentration.csv --output output/post.json
```
