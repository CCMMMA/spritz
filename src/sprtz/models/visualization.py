from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from sprtz.exceptions import DataFormatError
from sprtz.io.netcdf_cf import read_cf_concentration

CoordinateSystem = Literal["auto", "local", "geographic"]

LATITUDE_KEYS = ("latitude", "lat")
LONGITUDE_KEYS = ("longitude", "lon", "long", "lng")


@dataclass(frozen=True)
class PlotData:
    x: np.ndarray
    y: np.ndarray
    values: np.ndarray
    coordinate_system: Literal["local", "geographic"]
    x_label: str
    y_label: str


def _read_rows(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if p.suffix.lower() in {".nc", ".nc4", ".cdf", ".netcdf", ".json", ".jsn"}:
        return read_cf_concentration(p)
    with p.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _float_value(row: dict[str, Any], key: str, *, row_index: int) -> float:
    try:
        value = row[key]
    except KeyError as exc:
        raise DataFormatError(f"row {row_index} is missing required field {key!r}") from exc
    if value is None or value == "":
        raise DataFormatError(f"row {row_index} has an empty value for {key!r}")
    try:
        return float(str(value).replace(",", "."))
    except ValueError as exc:
        raise DataFormatError(f"row {row_index} field {key!r} is not numeric: {value!r}") from exc


def _first_key(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    lowered = {str(key).lower(): key for key in row}
    for key in keys:
        if key in lowered:
            return str(lowered[key])
    return None


def _lat_lon_from_rows(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray] | None:
    lat: list[float] = []
    lon: list[float] = []
    for index, row in enumerate(rows):
        lat_key = _first_key(row, LATITUDE_KEYS)
        lon_key = _first_key(row, LONGITUDE_KEYS)
        if lat_key is None or lon_key is None:
            return None
        lat.append(_float_value(row, lat_key, row_index=index))
        lon.append(_float_value(row, lon_key, row_index=index))
    return np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)


def _local_to_lat_lon(
    x: np.ndarray,
    y: np.ndarray,
    *,
    center_lat: float,
    center_lon: float,
) -> tuple[np.ndarray, np.ndarray]:
    try:
        from pyproj import CRS, Transformer
    except Exception as exc:  # pragma: no cover - pyproj is a core dependency
        raise DataFormatError("pyproj is required to transform local coordinates") from exc

    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat:.12f} +lon_0={center_lon:.12f} "
        "+datum=WGS84 +units=m +no_defs"
    )
    transformer = Transformer.from_crs(local, CRS.from_epsg(4326), always_xy=True)
    lon, lat = transformer.transform(x, y)
    return np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)


def prepare_plot_data(
    rows: list[dict[str, Any]],
    *,
    value_field: str = "concentration",
    coordinate_system: CoordinateSystem = "auto",
    center_lat: float | None = None,
    center_lon: float | None = None,
) -> PlotData:
    """Validate plotting rows and resolve local or geographic coordinates."""
    if not rows:
        raise DataFormatError("no concentration rows available for plotting")

    values = np.asarray(
        [_float_value(row, value_field, row_index=i) for i, row in enumerate(rows)],
        dtype=float,
    )
    x = np.asarray([_float_value(row, "x", row_index=i) for i, row in enumerate(rows)], dtype=float)
    y = np.asarray([_float_value(row, "y", row_index=i) for i, row in enumerate(rows)], dtype=float)

    lat_lon = _lat_lon_from_rows(rows)
    use_geographic = coordinate_system == "geographic" or (
        coordinate_system == "auto" and (lat_lon is not None or center_lat is not None)
    )
    if use_geographic:
        if lat_lon is None:
            if center_lat is None or center_lon is None:
                raise DataFormatError(
                    "geographic plotting requires latitude/longitude fields or "
                    "--center-lat/--center-lon for local-grid transformation"
                )
            lat, lon = _local_to_lat_lon(x, y, center_lat=center_lat, center_lon=center_lon)
        else:
            lat, lon = lat_lon
        return PlotData(lon, lat, values, "geographic", "Longitude [deg]", "Latitude [deg]")

    return PlotData(x, y, values, "local", "x [m]", "y [m]")


def parse_extent(value: str | None) -> tuple[float, float, float, float] | None:
    """Parse west,south,east,north or left,bottom,right,top plot extent."""
    if value is None:
        return None
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise DataFormatError("basemap extent must have four comma-separated values")
    try:
        west, south, east, north = (float(part) for part in parts)
    except ValueError as exc:
        raise DataFormatError(f"invalid basemap extent: {value}") from exc
    if east <= west or north <= south:
        raise DataFormatError("basemap extent must satisfy east > west and north > south")
    return west, south, east, north


def _apply_margin(ax: Any, data: PlotData, margin_fraction: float = 0.08) -> None:
    dx = max(float(np.nanmax(data.x) - np.nanmin(data.x)), 1.0e-9)
    dy = max(float(np.nanmax(data.y) - np.nanmin(data.y)), 1.0e-9)
    ax.set_xlim(
        float(np.nanmin(data.x) - dx * margin_fraction),
        float(np.nanmax(data.x) + dx * margin_fraction),
    )
    ax.set_ylim(
        float(np.nanmin(data.y) - dy * margin_fraction),
        float(np.nanmax(data.y) + dy * margin_fraction),
    )


def _add_image_basemap(
    ax: Any,
    *,
    basemap_path: str | Path,
    basemap_extent: tuple[float, float, float, float] | None,
    alpha: float,
) -> None:
    if basemap_extent is None:
        raise DataFormatError("local raster basemaps require --basemap-extent")
    path = Path(basemap_path)
    if not path.exists():
        raise DataFormatError(f"basemap image not found: {path}")
    try:
        import matplotlib.image as mpimg
    except Exception as exc:  # pragma: no cover - depends on optional extra
        raise DataFormatError("matplotlib image support is required for basemap rendering") from exc
    west, south, east, north = basemap_extent
    ax.imshow(mpimg.imread(path), extent=(west, east, south, north), origin="upper", alpha=alpha)


def _resolve_contextily_provider(contextily: Any, provider: str | None) -> Any:
    if not provider:
        return contextily.providers.OpenStreetMap.Mapnik
    current: Any = contextily.providers
    try:
        for part in provider.split("."):
            current = getattr(current, part)
        return current
    except AttributeError:
        return provider


def _add_tile_basemap(
    ax: Any,
    *,
    data: PlotData,
    provider: str | None,
    zoom: int,
    allow_network: bool,
) -> None:
    if data.coordinate_system != "geographic":
        raise DataFormatError("tile basemaps require geographic coordinates")
    if not allow_network:
        raise DataFormatError("network basemap tiles require --allow-network-basemap")
    try:
        import contextily
    except Exception as exc:  # pragma: no cover - depends on optional extra
        raise DataFormatError("contextily is required for tile basemaps; install .[maps]") from exc
    contextily.add_basemap(
        ax,
        crs="EPSG:4326",
        source=_resolve_contextily_provider(contextily, provider),
        zoom=zoom,
        attribution_size=6,
    )


def concentration_scatter(
    input_path: str | Path,
    output_path: str | Path,
    *,
    title: str = "Concentration field",
    dpi: int = 300,
    coordinate_system: CoordinateSystem = "auto",
    center_lat: float | None = None,
    center_lon: float | None = None,
    value_field: str = "concentration",
    basemap_path: str | Path | None = None,
    basemap_extent: tuple[float, float, float, float] | None = None,
    tile_provider: str | None = None,
    tile_zoom: int = 14,
    allow_network_basemap: bool = False,
    basemap_alpha: float = 0.72,
    marker_size: float | None = None,
    cmap: str = "viridis",
    log_scale: bool = False,
    figure_size: tuple[float, float] = (7.6, 6.0),
) -> Path:
    """Create a production-quality receptor scatter plot.

    Geographic plotting uses latitude/longitude fields when available. If rows
    only contain local x/y coordinates, pass ``center_lat`` and ``center_lon`` to
    transform the local azimuthal-equidistant grid to WGS84 lon/lat. Base maps
    are optional and explicit: local image files are offline, while web tiles
    require ``allow_network_basemap=True``.
    """
    rows = _read_rows(input_path)
    data = prepare_plot_data(
        rows,
        value_field=value_field,
        coordinate_system=coordinate_system,
        center_lat=center_lat,
        center_lon=center_lon,
    )
    try:
        import matplotlib.pyplot as plt
        from matplotlib.colors import LogNorm
    except Exception as exc:  # pragma: no cover - depends on optional extra
        raise DataFormatError("matplotlib is required for visualization; install .[viz]") from exc

    fig, ax = plt.subplots(figsize=figure_size, constrained_layout=True)
    _apply_margin(ax, data)
    if basemap_path is not None:
        _add_image_basemap(
            ax,
            basemap_path=basemap_path,
            basemap_extent=basemap_extent,
            alpha=basemap_alpha,
        )
    if tile_provider is not None:
        _add_tile_basemap(
            ax,
            data=data,
            provider=tile_provider,
            zoom=tile_zoom,
            allow_network=allow_network_basemap,
        )

    size = marker_size if marker_size is not None else (72.0 if len(rows) < 50 else 34.0)
    positive = data.values[data.values > 0]
    norm = None
    if log_scale:
        if positive.size == 0:
            raise DataFormatError("log-scale plotting requires at least one positive value")
        norm = LogNorm(
            vmin=max(float(np.nanmin(positive)), 1.0e-30),
            vmax=float(np.nanmax(positive)),
        )

    scatter = ax.scatter(
        data.x,
        data.y,
        c=data.values,
        s=size,
        cmap=cmap,
        norm=norm,
        edgecolors="black",
        linewidths=0.25,
        zorder=3,
    )
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label(value_field.replace("_", " ").title())
    ax.set_title(title)
    ax.set_xlabel(data.x_label)
    ax.set_ylabel(data.y_label)
    if data.coordinate_system == "local":
        ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linewidth=0.3, alpha=0.5, zorder=1)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out
