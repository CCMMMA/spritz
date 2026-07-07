# Copernicus LC100 land-cover downloader

## Scientific Scope

This document describes land-cover acquisition for Sprtz surface-parameter derivation. It distinguishes categorical land cover from continuous fields and emphasizes nearest-neighbor or documented aggregation semantics.

`tools/copernicus-lc100-download.py` crops the Copernicus Global Land Cover
100 m discrete classification product to a WGS84 latitude-longitude bounding
box. It writes a categorical GeoTIFF that can be used by `sprtz-terrain fetch`
as a local land-cover input.

The script is a repository tool, not an installed `sprtz` console command. It
uses GDAL's `gdalwarp` command-line program and reads the public LC100 GeoTIFF
through GDAL `/vsicurl/`.

## Requirements

Install GDAL command-line tools before running the script:

```bash
gdalwarp --version
```

Common installation options are:

```bash
sudo apt install gdal-bin
conda install -c conda-forge gdal
```

Sprtz needs `rasterio` to read the resulting GeoTIFF:

```bash
python3 -m pip install -e .[geo,netcdf]
```

## Basic Usage

Run the script from the repository root:

```bash
python3 tools/copernicus-lc100-download.py \
  --center-lat 40.75 --center-lon 14.30 \
  --nx 101 --ny 101 \
  --dx 100 --dy 100 \
  --buffer-m 1000 \
  --output data/landcover/lc100_naples.tif
```

The default source is the 2019 Copernicus Global Land Cover 100 m discrete
classification GeoTIFF hosted on Zenodo. Override it only when a project has
archived a vetted mirror:

```bash
python3 tools/copernicus-lc100-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --source-url "https://example.org/path/to/lc100.tif" \
  --output data/landcover/lc100_naples.tif
```

If the output path already exists, the script writes the new crop to a
temporary file in the same directory and replaces the target only after
`gdalwarp` succeeds. Use `--overwrite` to pass GDAL's direct `-overwrite` mode
instead.

## Bounding Box

The bounding box is geographic WGS84:

- `--south`: minimum latitude in degrees, from `-90` to `90`;
- `--north`: maximum latitude in degrees, from `-90` to `90`;
- `--west`: minimum longitude in degrees, from `-180` to `180`;
- `--east`: maximum longitude in degrees, from `-180` to `180`;
- `--center-lat`, `--center-lon`, `--nx`, `--ny`, `--dx`, `--dy`,
  `--projection`, and `--buffer-m`: alternatively compute the WGS84 bbox from
  the same terrain-domain definition used by `sprtz-terrain fetch`.

`south` must be smaller than `north`, and `west` must be smaller than `east`.
When using domain arguments, use the same settings and buffer as the DEM
download so the categorical land-cover raster fully covers the GEO grid.
Choose a box that covers the complete Sprtz modeling domain plus the same buffer
used for DEM preparation. Use nearest-neighbor resampling for LC100 because its
pixel values are class labels, not continuous measurements.

## Output

The script runs `gdalwarp` with:

- `-te west south east north`;
- `-te_srs EPSG:4326`;
- `-t_srs EPSG:4326`;
- `-r near`;
- `COMPRESS=DEFLATE`, `TILED=YES`, and `BIGTIFF=IF_SAFER`.

A typical repository layout is:

```text
data/landcover/lc100_<area>.tif
```

Downloaded operational GeoTIFFs can be large. Keep them out of release archives
unless they are intentionally tiny test fixtures.

## Use With Sprtz Terrain

Use the LC100 GeoTIFF as the `terrain.landuse` local raster. Pair it with a DEM,
for example a COP30 GeoTIFF downloaded with
`tools/copernicus-cop30-dem-download.py`:

```json
{
  "domain": {
    "center_lat": 40.85,
    "center_lon": 14.27,
    "nx": 100,
    "ny": 100,
    "dx_m": 100.0,
    "dy_m": 100.0,
    "projection": "auto-utm",
    "buffer_m": 5000.0
  },
  "terrain": {
    "enabled": true,
    "dem": {
      "source": "local",
      "path": "data/dem/cop30_naples.tif",
      "dataset": "Copernicus DEM GLO-30 / COP30 via OpenTopography",
      "resolution_m": 30.0,
      "crs": "EPSG:4326"
    },
    "landuse": {
      "source": "local",
      "path": "data/landcover/lc100_naples.tif",
      "dataset": "Copernicus Global Land Cover 100 m",
      "year": 2019,
      "resolution_m": 100.0,
      "target_categories": "copernicus-lc100"
    },
    "output": "output/highres_terrain_lc100/geo.nc"
  }
}
```

Run:

```bash
sprtz-terrain fetch --config examples/highres_terrain_lc100.json
```

For command-line terrain jobs without a JSON config, pass the local LC100 path
and mapping explicitly:

```bash
sprtz-terrain fetch \
  --center-lat 40.85 \
  --center-lon 14.27 \
  --nx 100 --ny 100 \
  --dx 100 --dy 100 \
  --dem data/dem/cop30_naples.tif \
  --landuse data/landcover/lc100_naples.tif \
  --landuse-mapping copernicus-lc100 \
  --output output/highres_terrain_lc100/geo.nc
```

Sprtz reads the GeoTIFF CRS and pixel-center coordinates with `rasterio`,
transforms the target Terrain/SpritzMet grid into the source CRS, and samples
land-cover classes with nearest neighbor. The `target_categories:
"copernicus-lc100"` setting selects the LC100-to-Sprtz land-use crosswalk.

## LC100 Class Handling

LC100 is land cover. Sprtz converts it to internal land-use classes before
deriving roughness length, albedo, Bowen ratio, and vegetation fraction.

The built-in clean-room crosswalk maps:

- LC100 forest classes `111` through `126` to Sprtz tree cover;
- shrubs `20`, herbaceous vegetation `30`, cultivated vegetation `40`, urban
  `50`, bare/sparse `60`, snow/ice `70`, water `80`, wetland `90`, moss/lichen
  `100`, and ocean `200` to the corresponding Sprtz classes;
- unknown or no-data class `0` to Sprtz unknown.

Project-specific studies may replace the crosswalk in code or preprocess the
GeoTIFF to a validated local class scheme.

## Validation

Inspect the cropped GeoTIFF:

```bash
python3 - <<'PY'
import rasterio

path = "data/landcover/lc100_naples.tif"
with rasterio.open(path) as src:
    print(src.driver, src.width, src.height, src.crs, src.bounds, src.nodata)
    print(src.read(1).min(), src.read(1).max())
PY
```

After `sprtz-terrain fetch`, inspect the output `land_cover` and
`landuse_class` variables in the GEO JSON or NetCDF product.

## Troubleshooting

- `ERROR: gdalwarp was not found`: install GDAL command-line tools.
- `gdalwarp failed`: check network access to the source URL, bbox values, local
  disk space, and whether `--overwrite` is needed.
- All `landuse_class` values are `0`: confirm the configuration includes
  `"target_categories": "copernicus-lc100"` and that the raster contains LC100
  discrete-classification codes.
- Misaligned land-cover classes usually mean the LC100 bbox, DEM bbox, and Sprtz
  domain/buffer do not cover the same area.

## References

- Yamazaki, D., Ikeshima, D., Tawatari, R., Yamaguchi, T., O'Loughlin, F., Neal, J. C., Sampson, C. C., Kanae, S., and Bates, P. D. (2017). A high-accuracy map of global terrain elevations. Geophysical Research Letters, 44(11), 5844-5853. https://doi.org/10.1002/2017GL072874
- Farr, T. G., Rosen, P. A., Caro, E., Crippen, R., Duren, R., Hensley, S., Kobrick, M., Paller, M., Rodriguez, E., Roth, L., Seal, D., Shaffer, S., Shimada, J., Umland, J., Werner, M., Oskin, M., Burbank, D., and Alsdorf, D. (2007). The Shuttle Radar Topography Mission. Reviews of Geophysics, 45(2), RG2004. https://doi.org/10.1029/2005RG000183
- Buchhorn, M., Smets, B., Bertels, L., De Roo, B., Lesiv, M., Tsendbazar, N.-E., Herold, M., and Fritz, S. (2020). Copernicus Global Land Cover Layers - Collection 2. Remote Sensing, 12(6), 1044. https://doi.org/10.3390/rs12061044
