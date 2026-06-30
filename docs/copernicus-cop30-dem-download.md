# Copernicus COP30 DEM downloader

`tools/copernicus-cop30-dem-download.py` downloads a Copernicus DEM GLO-30
(`COP30`) elevation tile for a WGS84 latitude-longitude bounding box from the
OpenTopography Global DEM API. It writes a GeoTIFF that can be used as a local
DEM input for Sprtz terrain workflows.

The script is a repository tool, not an installed `sprtz` console command. It
requires network access, an OpenTopography API key, and the Python `requests`
package.

## Basic Usage

Run the script from the repository root:

```bash
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_naples.tif
```

The API key can be supplied on the command line:

```bash
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --api-key "$OPENTOPO_API_KEY" \
  --output data/dem/cop30_naples.tif
```

or through the environment:

```bash
export OPENTOPO_API_KEY=YOUR_OPENTOPOGRAPHY_API_KEY
python3 tools/copernicus-cop30-dem-download.py \
  --south 40.40 --north 41.10 \
  --west 13.80 --east 14.80 \
  --output data/dem/cop30_naples.tif
```

The script creates the output directory if needed, streams the response to disk,
and reports download progress on standard error. It exits with status `2` when
no API key is available, `1` on validation or download failure, and `0` on
success.

## Bounding Box

The bounding box is geographic WGS84:

- `--south`: minimum latitude in degrees, from `-90` to `90`;
- `--north`: maximum latitude in degrees, from `-90` to `90`;
- `--west`: minimum longitude in degrees, from `-180` to `180`;
- `--east`: maximum longitude in degrees, from `-180` to `180`.

`south` must be smaller than `north`, and `west` must be smaller than `east`.
Anti-meridian-crossing boxes are not supported by this helper.

Choose a box that fully covers the Sprtz modeling domain plus a buffer. For
regional domains, use the `domain.center_lat`, `domain.center_lon`, `nx`, `ny`,
`dx_m`, `dy_m`, and `buffer_m` values as the source of truth, then request a DEM
box that extends beyond the model grid. Avoid clipping the DEM exactly to the
outer model cell centers.

## Output

The output is an OpenTopography GeoTIFF for `demtype=COP30` and
`outputFormat=GTiff`. A typical repository layout is:

```text
data/dem/cop30_<area>.tif
```

Use a descriptive area name and keep downloaded operational data out of release
archives. Large GeoTIFF products should not be committed unless they are tiny
test fixtures intentionally added for the repository.

## Use With Sprtz Terrain

The downloaded GeoTIFF can be used by `sprtz-terrain fetch` as a local DEM
provider. Install the optional geospatial dependencies first:

```bash
python3 -m pip install -e .[geo,netcdf]
```

Then reference the GeoTIFF in the `terrain.dem` section of a Sprtz configuration:

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
    "output": "output/highres_terrain_cop30/geo.nc"
  }
}
```

Run the terrain workflow:

```bash
sprtz-terrain fetch --config examples/highres_terrain_cop30.json
```

or run it before a full Sprtz workflow:

```bash
sprtz run examples/highres_terrain_cop30.json --auto-terrain --interchange netcdf
```

`sprtz-terrain fetch` requires both a DEM and a land-cover input because the GEO
product contains elevation, land-use class, and derived surface parameters. The
COP30 downloader supplies only the DEM. Pair it with a compatible local
land-cover raster, for example an LC100 GeoTIFF prepared with
`tools/copernicus-lc100-download.py` for the same area.

## Compatibility Notes

Sprtz reads local GeoTIFF terrain inputs through `rasterio`, so `sprtz[geo]` must
be installed for `.tif`, `.tiff`, or `.cog` files. Without it, the local raster
provider raises an explicit dependency error.

For reliable alignment, download a DEM that is centered on and larger than the
Sprtz domain, and keep the configuration domain identical between terrain
generation, SpritzMet downscaling, and dispersion. Terrain, meteorology, and
dispersion grids must share dimensions, spacing, and projection choices.

For GeoTIFF/COG inputs, Sprtz reads the raster CRS and pixel-center coordinates
with `rasterio`, transforms the Sprtz target grid into the source CRS, and
bilinearly samples the DEM. Users should still verify the resulting GEO product
for their domain before production use.

## Validation

After downloading, check that the file is non-empty and readable:

```bash
ls -lh data/dem/cop30_naples.tif
python3 - <<'PY'
import rasterio

path = "data/dem/cop30_naples.tif"
with rasterio.open(path) as src:
    print(src.driver, src.width, src.height, src.crs, src.bounds, src.nodata)
PY
```

After running `sprtz-terrain fetch`, confirm that the GEO product exists and
contains finite elevation values. For JSON output:

```bash
python3 - <<'PY'
import json
import math

with open("output/highres_terrain_cop30/geo.json", "r", encoding="utf-8") as f:
    geo = json.load(f)

values = [v for row in geo["elevation_m"] for v in row]
finite = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
print(len(finite), min(finite), max(finite))
PY
```

For NetCDF output, inspect `surface_altitude` with `netCDF4` or another NetCDF
viewer.

## Troubleshooting

- `Error: OpenTopography API key is required`: pass `--api-key` or set
  `OPENTOPO_API_KEY`.
- `OpenTopography did not return a GeoTIFF`: check the API key, bbox, service
  availability, and OpenTopography response message.
- `west must be smaller than east`: split anti-meridian-crossing areas into
  separate downloads.
- `rasterio is required to read GeoTIFF/COG terrain inputs`: install
  `sprtz[geo]` in the active environment.
- Missing or suspicious terrain values in the GEO product usually mean the DEM
  does not cover the configured domain, the bbox was too tight, or the terrain
  domain settings differ from the downstream Sprtz run.
