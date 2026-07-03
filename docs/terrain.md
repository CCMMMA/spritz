# Terrain Preprocessing

## Scientific Scope

This document describes Sprtz terrain preprocessing. It emphasizes DEM and land-cover provenance, grid alignment, categorical resampling discipline, and metadata sufficient for audit or reproduction.

Terrain is the clean-room Spritz component for preparing terrain elevations,
land-use classes, and surface parameters on the Spritz modeling grid.

## Two Compatible APIs

The existing `terrain` CLI and `sprtz.models.terrain` API remain available for
small local ASCII DEM resampling:

```bash
terrain \
  --terrain examples/terrain.asc \
  --output output/terrain.nc \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 101 --ny 101 \
  --dx 100 --dy 100
```

The production-style acquisition path is exposed as `sprtz-terrain fetch`:

```bash
sprtz-terrain fetch --config examples/highres_terrain_local.json --json
```

The local example is offline and deterministic. It reads small ASCII fixtures
under `examples/data/`, aligns DEM and land-cover rasters to the model grid,
remaps land cover to Spritz land-use classes, derives surface parameters, and
writes a GEO JSON product.

## Online Providers

The provider interfaces include Copernicus DEM and ESA WorldCover facades:

```bash
sprtz-terrain fetch \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --dx 100 --dy 100 \
  --nx 100 --ny 100 \
  --projection auto-utm \
  --dem copernicus-30 \
  --landuse esa-worldcover-2021 \
  --output output/geo.nc \
  --allow-network
```

Live online access is not implicit. Deployments must configure appropriate
STAC/COG/catalog endpoints or credentialed downloaders. Without `--allow-network`
the providers fail with clear errors so tests never make hidden web requests.

Install optional geospatial dependencies for GeoTIFF/COG and richer provider
adapters:

```bash
python -m pip install -e .[geo,netcdf]
```

Local GeoTIFF/COG DEM and land-cover inputs, including COP30 products downloaded
with `tools/copernicus-cop30-dem-download.py` and LC100 products downloaded with
`tools/copernicus-lc100-download.py`, are read through `rasterio`. Sprtz uses the
raster CRS and pixel-center coordinates to sample each raster on the target
Terrain/SpritzMet grid. Keep both bounding boxes larger than the configured
domain and set `terrain.landuse.target_categories` to `copernicus-lc100` for
LC100 inputs.

## JSON Configuration

Terrain configuration can be embedded in a normal Spritz run file:

```json
{
  "domain": {
    "center_lat": 40.85,
    "center_lon": 14.27,
    "nx": 100,
    "ny": 100,
    "dx_m": 100,
    "dy_m": 100,
    "projection": "auto-utm",
    "buffer_m": 5000
  },
  "terrain": {
    "enabled": true,
    "dem": {"source": "copernicus-dem", "resolution": "30m"},
    "landuse": {"source": "esa-worldcover", "year": 2021},
    "output": "geo.nc"
  }
}
```

Run it as a standalone terrain job or as part of the workflow:

```bash
sprtz-terrain fetch --config examples/highres_terrain_local.json --json
sprtz run examples/highres_terrain_local.json --auto-terrain --interchange json
```

When `terrain.enabled` is true, `sprtz run` also builds the configured GEO
product before meteorology. Relative `terrain.output` paths are written under the
workflow output directory.

## Caching

The default cache metadata directory is:

```text
~/.cache/sprtz/terrain
```

Override it with `SPRTZ_TERRAIN_CACHE`, `--cache-dir`, or `terrain.cache_dir` in
JSON. Cache keys include provider, dataset, resolution, AOI/domain, CRS, and
grid metadata so incompatible data is not silently reused.

## Scientific Assumptions

DEM, DTM, and DSM are not interchangeable. A DTM is bare-earth terrain; a DSM may
include buildings or canopy. Spritz records `dem_source`, `dem_dataset`, and
`dem_resolution` so users can validate whether the source is appropriate.

Land cover is observed surface class; land use is the model category used for
surface parameters. ESA WorldCover-style labels are remapped through an explicit
crosswalk to Spritz classes. The default parameters are minimal, visible, and
replaceable:

- roughness length;
- albedo;
- Bowen ratio;
- vegetation fraction.

Continuous terrain is bilinearly resampled. Categorical land-cover rasters are
nearest-neighbor resampled because class labels are not scalar measurements;
bilinear resampling would invent invalid classes.

## Provenance

Derived GEO products include:

- `dem_source`, `dem_dataset`, `dem_resolution`, `dem_access_date`;
- `landuse_source`, `landuse_dataset`, `landuse_year`, `landuse_resolution`;
- `source_crs`, `target_crs`;
- `resampling_dem`, `resampling_landuse`;
- `cache_key`, `software_version`.

NetCDF-CF is preferred when `netCDF4` is installed. JSON fallback keeps local
tests and teaching examples portable.

## References

- Yamazaki, D., Ikeshima, D., Tawatari, R., Yamaguchi, T., O'Loughlin, F., Neal, J. C., Sampson, C. C., Kanae, S., and Bates, P. D. (2017). A high-accuracy map of global terrain elevations. Geophysical Research Letters, 44(11), 5844-5853. https://doi.org/10.1002/2017GL072874
- Farr, T. G., Rosen, P. A., Caro, E., Crippen, R., Duren, R., Hensley, S., Kobrick, M., Paller, M., Rodriguez, E., Roth, L., Seal, D., Shaffer, S., Shimada, J., Umland, J., Werner, M., Oskin, M., Burbank, D., and Alsdorf, D. (2007). The Shuttle Radar Topography Mission. Reviews of Geophysics, 45(2), RG2004. https://doi.org/10.1029/2005RG000183
- Buchhorn, M., Smets, B., Bertels, L., De Roo, B., Lesiv, M., Tsendbazar, N.-E., Herold, M., and Fritz, S. (2020). Copernicus Global Land Cover Layers - Collection 2. Remote Sensing, 12(6), 1044. https://doi.org/10.3390/rs12061044
