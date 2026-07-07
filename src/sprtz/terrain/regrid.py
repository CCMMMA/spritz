from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pyproj import CRS, Transformer

from sprtz.models.spritzmet import local_grid_latlon
from sprtz.models.terrain import _axis_for_source, _bilinear_regular_grid
from sprtz.terrain.providers.base import RasterData, TerrainConfigurationError


@dataclass(frozen=True)
class DomainDefinition:
    """Spritz modeling domain used to align terrain, land use, meteo, and dispersion grids."""

    center_lat: float
    center_lon: float
    nx: int
    ny: int
    dx_m: float
    dy_m: float
    projection: str = "local-aeqd"
    buffer_m: float = 0.0

    @classmethod
    def from_mapping(cls, data: dict[str, object]) -> DomainDefinition:
        try:
            center_lat = float(data["center_lat"])
            center_lon = float(data["center_lon"])
        except KeyError as exc:
            raise TerrainConfigurationError("domain requires center_lat and center_lon") from exc
        nx = int(data.get("nx", data.get("NX", 0)))
        ny = int(data.get("ny", data.get("NY", 0)))
        dx_m = float(data.get("dx_m", data.get("dx", data.get("DX", 0.0))))
        dy_m = float(data.get("dy_m", data.get("dy", data.get("DY", dx_m))))
        domain = cls(
            center_lat=center_lat,
            center_lon=center_lon,
            nx=nx,
            ny=ny,
            dx_m=dx_m,
            dy_m=dy_m,
            projection=str(data.get("projection", "local-aeqd")),
            buffer_m=float(data.get("buffer_m", 0.0)),
        )
        domain.validate()
        return domain

    def validate(self) -> None:
        if not -90.0 <= self.center_lat <= 90.0:
            raise TerrainConfigurationError("domain center_lat must be in [-90, 90]")
        if not -180.0 <= self.center_lon <= 180.0:
            raise TerrainConfigurationError("domain center_lon must be in [-180, 180]")
        if self.nx < 2 or self.ny < 2:
            raise TerrainConfigurationError("domain nx and ny must be at least 2")
        if self.dx_m <= 0 or self.dy_m <= 0:
            raise TerrainConfigurationError("domain dx_m and dy_m must be positive")
        if self.buffer_m < 0:
            raise TerrainConfigurationError("domain buffer_m must be non-negative")

    @property
    def width_m(self) -> float:
        return (self.nx - 1) * self.dx_m

    @property
    def height_m(self) -> float:
        return (self.ny - 1) * self.dy_m


@dataclass(frozen=True)
class TargetGrid:
    x: np.ndarray
    y: np.ndarray
    latitude: np.ndarray
    longitude: np.ndarray
    target_crs: str


def auto_utm_crs(lat: float, lon: float) -> CRS:
    """Return the WGS84 UTM CRS for a domain center.

    UTM is chosen by longitude zone and hemisphere; this is appropriate for
    city/regional domains where projection distortion is small compared with the
    modeling grid spacing. Larger domains should specify a project CRS.
    """
    zone = int((lon + 180.0) // 6.0) + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


def target_crs(domain: DomainDefinition) -> CRS:
    projection = domain.projection.lower()
    if projection == "auto-utm":
        return auto_utm_crs(domain.center_lat, domain.center_lon)
    if projection in {"local-aeqd", "aeqd", "local"}:
        return CRS.from_proj4(
            f"+proj=aeqd +lat_0={domain.center_lat:.12f} +lon_0={domain.center_lon:.12f} "
            "+datum=WGS84 +units=m +no_defs"
        )
    return CRS.from_user_input(domain.projection)


def build_target_grid(domain: DomainDefinition) -> TargetGrid:
    if domain.projection.lower() == "auto-utm":
        crs = target_crs(domain)
        x_offset = (np.arange(domain.nx, dtype=float) - (domain.nx - 1) / 2.0) * domain.dx_m
        y_offset = (np.arange(domain.ny, dtype=float) - (domain.ny - 1) / 2.0) * domain.dy_m
        xx, yy = np.meshgrid(x_offset, y_offset)
        to_target = Transformer.from_crs(CRS.from_epsg(4326), crs, always_xy=True)
        to_wgs84 = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)
        center_x, center_y = to_target.transform(domain.center_lon, domain.center_lat)
        lon, lat = to_wgs84.transform(center_x + xx, center_y + yy)
        return TargetGrid(
            xx,
            yy,
            np.asarray(lat, dtype=float),
            np.asarray(lon, dtype=float),
            crs.to_string(),
        )
    xx, yy, lat, lon = local_grid_latlon(
        domain.center_lat,
        domain.center_lon,
        domain.nx,
        domain.ny,
        domain.dx_m,
        domain.dy_m,
    )
    return TargetGrid(xx, yy, lat, lon, target_crs(domain).to_string())


def aoi_bounds(domain: DomainDefinition) -> tuple[float, float, float, float]:
    """Return a WGS84 bounding box for the model domain plus buffer."""
    grid = build_target_grid(domain)
    if domain.buffer_m > 0.0:
        x_min = float(np.nanmin(grid.x)) - domain.buffer_m
        x_max = float(np.nanmax(grid.x)) + domain.buffer_m
        y_min = float(np.nanmin(grid.y)) - domain.buffer_m
        y_max = float(np.nanmax(grid.y)) + domain.buffer_m
        xx, yy = np.meshgrid(
            np.asarray([x_min, x_max], dtype=float),
            np.asarray([y_min, y_max], dtype=float),
        )
        crs = target_crs(domain)
        if domain.projection.lower() == "auto-utm":
            to_target = Transformer.from_crs(CRS.from_epsg(4326), crs, always_xy=True)
            center_x, center_y = to_target.transform(domain.center_lon, domain.center_lat)
            xx = center_x + xx
            yy = center_y + yy
        to_wgs84 = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)
        lon, lat = to_wgs84.transform(xx, yy)
        return (
            float(np.nanmin(lon)),
            float(np.nanmin(lat)),
            float(np.nanmax(lon)),
            float(np.nanmax(lat)),
        )
    return (
        float(np.nanmin(grid.longitude)),
        float(np.nanmin(grid.latitude)),
        float(np.nanmax(grid.longitude)),
        float(np.nanmax(grid.latitude)),
    )


def _source_axes(raster: RasterData) -> tuple[np.ndarray, np.ndarray]:
    if "x_coords" in raster.metadata and "y_coords" in raster.metadata:
        return (
            np.asarray(raster.metadata["x_coords"], dtype=float),
            np.asarray(raster.metadata["y_coords"], dtype=float),
        )
    return (
        _axis_for_source(raster.values.shape[1], raster.x_spacing_m),
        _axis_for_source(raster.values.shape[0], raster.y_spacing_m),
    )


def _ascending_source(
    values: np.ndarray,
    src_x: np.ndarray,
    src_y: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return source values with monotonically increasing x/y axes."""
    out = np.asarray(values, dtype=float)
    x = np.asarray(src_x, dtype=float)
    y = np.asarray(src_y, dtype=float)
    if x.size != out.shape[1] or y.size != out.shape[0]:
        raise TerrainConfigurationError("source coordinate axes do not match raster shape")
    if x.size < 2 or y.size < 2:
        raise TerrainConfigurationError("source coordinate axes must contain at least two cells")
    if np.any(np.diff(x) == 0.0) or np.any(np.diff(y) == 0.0):
        raise TerrainConfigurationError("source coordinate axes must be strictly monotonic")
    if x[0] > x[-1]:
        x = x[::-1]
        out = out[:, ::-1]
    if y[0] > y[-1]:
        y = y[::-1]
        out = out[::-1, :]
    return out, x, y


def _target_points_for_source(
    raster: RasterData,
    grid: TargetGrid,
) -> tuple[np.ndarray, np.ndarray]:
    crs = str(raster.crs or "").strip()
    if "x_coords" not in raster.metadata or "y_coords" not in raster.metadata:
        return grid.x, grid.y
    if not crs or crs.upper() == "LOCAL":
        return grid.x, grid.y
    try:
        transformer = Transformer.from_crs(
            CRS.from_epsg(4326),
            CRS.from_user_input(crs),
            always_xy=True,
        )
    except Exception as exc:
        raise TerrainConfigurationError(
            f"cannot transform Sprtz grid from {grid.target_crs!r} to source raster CRS {crs!r}"
        ) from exc
    source_x, source_y = transformer.transform(grid.longitude, grid.latitude)
    return np.asarray(source_x, dtype=float), np.asarray(source_y, dtype=float)


def _require_source_coverage(
    raster: RasterData,
    src_x: np.ndarray,
    src_y: np.ndarray,
    dst_x: np.ndarray,
    dst_y: np.ndarray,
) -> None:
    outside = (
        (dst_x < src_x[0])
        | (dst_x > src_x[-1])
        | (dst_y < src_y[0])
        | (dst_y > src_y[-1])
    )
    if not np.any(outside):
        return
    total = int(outside.size)
    outside_count = int(np.count_nonzero(outside))
    raise TerrainConfigurationError(
        "source raster does not cover the requested terrain grid: "
        f"{outside_count}/{total} target points "
        f"({outside_count / total:.1%}) fall outside {raster.source}; "
        f"source x=[{float(src_x[0]):.8g}, {float(src_x[-1]):.8g}], "
        f"y=[{float(src_y[0]):.8g}, {float(src_y[-1]):.8g}], "
        f"target x=[{float(np.nanmin(dst_x)):.8g}, {float(np.nanmax(dst_x)):.8g}], "
        f"y=[{float(np.nanmin(dst_y)):.8g}, {float(np.nanmax(dst_y)):.8g}]. "
        "Download or provide a DEM/land-cover raster with enough buffer around "
        "the full model domain."
    )


def sanitize_dem(raster: RasterData) -> np.ndarray:
    """Return DEM values with nodata converted to NaN and finite checks applied."""
    values = np.asarray(raster.values, dtype=float)
    if raster.nodata is not None:
        values = np.where(values == float(raster.nodata), np.nan, values)
    if not np.isfinite(values).any():
        raise TerrainConfigurationError(
            f"DEM raster contains no finite elevation values: {raster.source}"
        )
    return values


def resample_dem(raster: RasterData, grid: TargetGrid, *, allow_outside: bool = False) -> np.ndarray:
    """Resample continuous elevation to the model grid.

    DEM/DTM/DSM elevations are continuous scalar fields, so bilinear
    resampling is appropriate for deterministic grid alignment. This must not
    be reused for categorical land-cover classes.
    """
    source = raster.validated()
    src_x, src_y = _source_axes(source)
    values = sanitize_dem(source)
    values, src_x, src_y = _ascending_source(values, src_x, src_y)
    dst_x, dst_y = _target_points_for_source(source, grid)
    if allow_outside:
        dst_x = np.clip(np.asarray(dst_x, dtype=float), src_x[0], src_x[-1])
        dst_y = np.clip(np.asarray(dst_y, dtype=float), src_y[0], src_y[-1])
    else:
        _require_source_coverage(source, src_x, src_y, dst_x, dst_y)
    return _bilinear_regular_grid(values, src_x, src_y, dst_x, dst_y)


def resample_land_cover(raster: RasterData, grid: TargetGrid, *, allow_outside: bool = False) -> np.ndarray:
    """Nearest-neighbor resampling for categorical land-cover classes.

    Land-cover values are labels, not magnitudes. Bilinear resampling would
    invent non-existent classes such as 35 between grassland (30) and cropland
    (40), so the deterministic nearest source cell is selected for each target
    cell. Majority aggregation can be added later for coarsening workflows.
    """
    source = raster.validated()
    src_x, src_y = _source_axes(source)
    values = np.asarray(source.values, dtype=float)
    values, src_x, src_y = _ascending_source(values, src_x, src_y)
    dst_x, dst_y = _target_points_for_source(source, grid)
    if not allow_outside:
        _require_source_coverage(source, src_x, src_y, dst_x, dst_y)
    x = np.clip(np.asarray(dst_x, dtype=float).ravel(), src_x[0], src_x[-1])
    y = np.clip(np.asarray(dst_y, dtype=float).ravel(), src_y[0], src_y[-1])
    ix = np.abs(src_x[:, None] - x[None, :]).argmin(axis=0)
    iy = np.abs(src_y[:, None] - y[None, :]).argmin(axis=0)
    if source.nodata is not None:
        values = np.where(values == float(source.nodata), np.nan, values)
    out = values[iy, ix]
    return np.where(np.isfinite(out), out, 0).astype(int).reshape(grid.x.shape)
