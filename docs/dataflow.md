# Data Flow

![Spritz data flow](assets/spritz_dataflow.svg)

Spritz data flow is designed so each scientific transformation is explicit,
reproducible, and tied to provenance metadata.

## Workflow Steps

1. **User configuration** defines the domain, projection, grid, Terrain
   providers, meteorology, sources, receptors, and output formats.
2. **Domain definition / projection / grid** resolves center latitude/longitude,
   `nx`, `ny`, `dx`, `dy`, optional buffer, and target CRS. `auto-utm` selects a
   WGS84 UTM zone from the domain center; local AEQD remains available for small
   centered grids.
3. **DEM acquisition** uses either local rasters or explicit online providers.
   Online Copernicus DEM access is behind a provider interface and requires
   network opt-in and deployment-specific catalog/credential configuration.
4. **Land-cover acquisition** uses either local categorical rasters or explicit
   online ESA WorldCover provider configuration.
5. **Raster mosaic / clipping / reprojection** is represented in the provider and
   regridding interface. Offline examples use centered local rasters, while
   production adapters can add STAC/COG mosaicking.
6. **DEM resampling and terrain derivatives** treat elevation as a continuous
   scalar field. Bilinear resampling is deterministic and suitable for
   aligning a DEM/DTM/DSM to the model grid.
7. **Land-cover categorical resampling** uses nearest-neighbor selection because
   class labels are not numeric magnitudes. Bilinear resampling would invent
   invalid land-cover classes.
8. **Land-cover to Spritz land-use remapping** converts ESA WorldCover-style
   classes to internal Spritz land-use categories.
9. **Surface parameter derivation** computes minimal roughness length, albedo,
   Bowen ratio, and vegetation fraction arrays from the internal land-use class.
10. **GEO/terrain output with provenance** writes NetCDF-CF when available or JSON
    fallback otherwise. Required metadata includes source datasets, resolution,
    CRS, resampling methods, cache key, and Spritz software version.
11. **Meteorological preprocessing** writes SpritzMet wind, temperature,
    mixing-height, and precipitation-rate outputs aligned with the same grid
    conventions.
12. **Emission/source preprocessing and dispersion** run the configured
    Gaussian or particle backend, applying source time windows, source release
    heights, optional firefighter emission factors, and optional precipitation
    washout from the meteorology product.
13. **Concentration/deposition outputs** feed SpritzPost and visualization; when
    requested, NetCDF-CF output also carries a gridded 3D concentration field.
14. **Post-processing and visualization** produce statistics, maps, and diagnostic
    figures.

## External Sources, Cache, And Outputs

The data-flow diagram distinguishes external data sources, local cache metadata,
deterministic preprocessing, model computation, and final outputs. Tests use
offline local rasters only. Network provider tests must remain opt-in through
environment variables such as `SPRTZ_RUN_NETWORK_TESTS=1`.

## Terminology

DEM is used here as the generic elevation source. A DTM represents bare-earth
terrain, while a DSM may include buildings and vegetation canopy. The Terrain
metadata records the source so users can decide whether a surface model warning
is relevant to their study.

Land cover describes what is physically observed on the surface. Land use is the
model category used to derive roughness and other parameters. Spritz keeps the
land-cover-to-land-use crosswalk visible and replaceable.
