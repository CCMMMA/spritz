# Data Flow

## Scientific Scope

This document specifies the movement of configuration, meteorology, terrain, concentration, fire-front, and visualization products through Sprtz. The goal is a reproducible, auditable chain of scientific data transformations.

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

## References

- Rew, R., and Davis, G. (1990). NetCDF: an interface for scientific data access. IEEE Computer Graphics and Applications, 10(4), 76-82. https://doi.org/10.1109/38.56302
- Balaji, V., Taylor, K. E., Juckes, M., Lawrence, B. N., Durack, P. J., Lautenschlager, M., Blanton, C., Cinquini, L., Denvil, S., Elkington, M., Guglielmo, F., Guilyardi, E., Hassell, D., Kharin, S., Kindermann, S., Nikonov, S., Radhakrishnan, A., Stockhause, M., and Weigel, T. (2018). Requirements for a global data infrastructure in support of CMIP6. Geoscientific Model Development, 11, 3659-3680. https://doi.org/10.5194/gmd-11-3659-2018
- Wilson, G., Aruliah, D. A., Brown, C. T., Hong, N. P. C., Davis, M., Guy, R. T., Haddock, S. H. D., Huff, K. D., Mitchell, I. M., Plumbley, M. D., Waugh, B., White, E. P., and Wilson, P. (2014). Best practices for scientific computing. PLOS Biology, 12(1), e1001745. https://doi.org/10.1371/journal.pbio.1001745
- Sandve, G. K., Nekrutenko, A., Taylor, J., and Hovig, E. (2013). Ten simple rules for reproducible computational research. PLOS Computational Biology, 9(10), e1003285. https://doi.org/10.1371/journal.pcbi.1003285
