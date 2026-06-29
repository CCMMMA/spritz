from __future__ import annotations

import logging

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from sprtz.models import spritzmet, spritzwrf
from sprtz.logging import configure_logging
from sprtz.config import config_defaults
from datetime_args import script_datetime_to_date_and_hour
from plotting import plot_netcdf_if_available


LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class WindDownscalingResult:
    output_path: Path
    nx: int
    ny: int
    dx_m: float
    dy_m: float
    center_lat: float
    center_lon: float
    source: str
    format: str
    pipeline: str = "SpritzWRF -> SpritzMet"
    plot_path: Path | None = None

    def as_dict(self) -> dict[str, Any]:
        result = {
            "component": "usecase.high_resolution_wind",
            "output_path": str(self.output_path),
            "nx": self.nx,
            "ny": self.ny,
            "dx_m": self.dx_m,
            "dy_m": self.dy_m,
            "center_lat": self.center_lat,
            "center_lon": self.center_lon,
            "source": self.source,
            "format": self.format,
            "pipeline": self.pipeline,
        }
        if self.plot_path is not None:
            result["plot_path"] = str(self.plot_path)
        return result


def _synthetic_wrf(center_lat: float, center_lon: float, nx: int = 7, ny: int = 7) -> spritzwrf.WRFWindField:
    """Create a deterministic WRF-like field for tests and documentation examples."""
    lat_axis = center_lat + (np.arange(ny) - (ny - 1) / 2.0) * 0.009
    lon_axis = center_lon + (np.arange(nx) - (nx - 1) / 2.0) * 0.012
    lon, lat = np.meshgrid(lon_axis, lat_axis)
    u = 3.5 + 0.4 * np.sin(np.deg2rad((lat - center_lat) * 100.0))
    v = 1.2 + 0.3 * np.cos(np.deg2rad((lon - center_lon) * 100.0))
    return spritzwrf.WRFWindField(
        lat,
        lon,
        u,
        v,
        Path("synthetic-wrf5-d03"),
        metadata={"synthetic": True, "time_index": "0", "level_index": "0"},
    )


def _require_cf_valid_time_for_netcdf(wrf: spritzwrf.WRFWindField, *, prefer_netcdf: bool) -> None:
    if not prefer_netcdf:
        return
    if wrf.metadata and wrf.metadata.get("time_datetime"):
        return
    raise ValueError(
        "NetCDF output requires WRF valid-time metadata from SpritzWRF. "
        "Provide a WRF file with Times, CF time units, or explicit global time attributes; "
        "Sprtz does not infer scientific datetimes from filenames."
    )


def resolve_wrf_input(
    wrf_path: str | Path | None,
    *,
    download_date: str | None = None,
    download_cycle_hour: int = 0,
    download_dir: str | Path = "data/wrf",
    force_download: bool = False,
    download_timeout_s: float = 120.0,
) -> Path | None:
    """Return a local WRF path, downloading meteo@uniparthenope data when requested."""
    if wrf_path is not None:
        return Path(wrf_path)
    if download_date is None:
        return None
    return spritzwrf.download_meteo_uniparthenope_wrf(
        download_dir,
        run_date=download_date,
        cycle_hour=download_cycle_hour,
        timeout_s=download_timeout_s,
        force=force_download,
    )


def downscale_wrf_to_100m(
    wrf_path: str | Path | None,
    output_path: str | Path,
    *,
    center_lat: float,
    center_lon: float,
    nx: int = 101,
    ny: int = 101,
    dx_m: float = 100.0,
    dy_m: float = 100.0,
    time_index: int | None = None,
    level_index: int | None = None,
    prefer_netcdf: bool = True,
    allow_synthetic: bool = False,
    download_time: str | None = None,
    download_date: str | None = None,
    download_cycle_hour: int = 0,
    download_dir: str | Path = "data/wrf",
    force_download: bool = False,
    download_timeout_s: float = 120.0,
    dem_path: str | Path | None = None,
    land_cover_path: str | Path | None = None,
) -> WindDownscalingResult:
    """Downscale 1 km WRF wind to a 100 m local grid using SpritzWRF then SpritzMet.

    Workflow
    --------
    1. SpritzWRF loads a local WRF NetCDF file or downloads WRF5 d03 history data
       from the meteo@uniparthenope archive.
    2. SpritzMet creates an azimuthal-equidistant grid centered at the requested
       latitude/longitude and downscales the SpritzWRF wind vectors to that grid.
    3. The output is written as strict NetCDF-CF by default, with JSON fallback.
       NetCDF output requires SpritzWRF to provide WRF/CF valid-time metadata;
       datetimes are not inferred from filenames.
    """
    if download_time is not None:
        download_date, download_cycle_hour = script_datetime_to_date_and_hour(download_time)
    resolved = resolve_wrf_input(
        wrf_path,
        download_date=download_date,
        download_cycle_hour=download_cycle_hour,
        download_dir=download_dir,
        force_download=force_download,
        download_timeout_s=download_timeout_s,
    )
    if resolved is not None and resolved.exists():
        wrf = spritzwrf.load_near_surface_wind(resolved, time_index=time_index, level_index=level_index)
    elif allow_synthetic:
        wrf = _synthetic_wrf(center_lat, center_lon)
    else:
        raise FileNotFoundError(
            "WRF input file is required. Pass --wrf, or use --download-time YYYYMMDDZhhmm, "
            "or enable --allow-synthetic for tests."
        )
    _require_cf_valid_time_for_netcdf(wrf, prefer_netcdf=prefer_netcdf)
    dem_elevation_m, land_cover, terrain_metadata = spritzmet.terrain_downscaling_inputs_from_rasters(
        center_lat=center_lat,
        center_lon=center_lon,
        nx=nx,
        ny=ny,
        dx_m=dx_m,
        dy_m=dy_m,
        dem_path=dem_path,
        land_cover_path=land_cover_path,
    )
    met = spritzmet.downscale_wrf_to_local_grid(
        wrf,
        center_lat=center_lat,
        center_lon=center_lon,
        nx=nx,
        ny=ny,
        dx_m=dx_m,
        dy_m=dy_m,
        dem_elevation_m=dem_elevation_m,
        land_cover=land_cover,
        terrain_input_metadata=terrain_metadata,
    )
    fmt = spritzmet.write_local_meteorology(output_path, met, prefer_netcdf=prefer_netcdf)
    plot_path = plot_netcdf_if_available(
        output_path,
        Path(output_path).with_suffix(".png"),
        variable="wind_speed",
        title="SpritzMet Wind Speed",
        center_lat=center_lat,
        center_lon=center_lon,
    )
    return WindDownscalingResult(Path(output_path), nx, ny, dx_m, dy_m, center_lat, center_lon, met.source, fmt, plot_path=plot_path)


WindInterpolationResult = WindDownscalingResult
interpolate_wrf_to_100m = downscale_wrf_to_100m


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="SpritzWRF -> SpritzMet: downscale WRF 1 km winds to a 100 m local grid")
    parser.add_argument("--config", default=None, help="optional shared JSON configuration; CLI options override matching values")
    parser.add_argument("--wrf", default=None, help="Local WRF NetCDF input; omit when using --download-time or --allow-synthetic")
    parser.add_argument("--download-time", default=None, help="Download meteo@uniparthenope WRF5 d03 file for UTC YYYYMMDDZhhmm")
    parser.add_argument("--download-dir", default="data/wrf", help="Directory for downloaded WRF files")
    parser.add_argument("--download-timeout-s", type=float, default=120.0)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--print-download-url", action="store_true", help="Print the meteo@uniparthenope URL and exit")
    parser.add_argument("--output", default=None)
    parser.add_argument("--center-lat", type=float, default=None)
    parser.add_argument("--center-lon", type=float, default=None)
    parser.add_argument("--nx", type=int, default=101)
    parser.add_argument("--ny", type=int, default=101)
    parser.add_argument("--dx", type=float, default=100.0)
    parser.add_argument("--dy", type=float, default=100.0)
    parser.add_argument("--time-index", type=int, default=None, help="time index to extract; omit to downscale all WRF times")
    parser.add_argument("--level-index", type=int, default=None, help="vertical level index to extract; omit to downscale all WRF levels")
    parser.add_argument("--dem", default=None, help="Optional DEM raster, e.g. data/dem/cop30_naples.tif")
    parser.add_argument("--land-cover", "--landuse", dest="land_cover", default=None, help="Optional categorical land-cover raster, e.g. data/landcover/lc100_naples.tif")
    parser.add_argument("--json", action="store_true", help="write JSON even when netCDF4 is available")
    parser.add_argument("--allow-synthetic", action="store_true")
    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument("--config", default=None)
    config_args, _ = config_parser.parse_known_args(argv)
    if config_args.config:
        parser.set_defaults(**config_defaults(config_args.config, sections=("run", "domain", "terrain", "spritzmet")))
    args = parser.parse_args(argv)
    if args.output is None:
        parser.error("--output is required unless provided by --config")
    if args.center_lat is None or args.center_lon is None:
        parser.error("--center-lat and --center-lon are required unless provided by --config")
    download_date = None
    download_cycle_hour = 0
    if args.download_time is not None:
        download_date, download_cycle_hour = script_datetime_to_date_and_hour(args.download_time)
    if args.print_download_url:
        if download_date is None:
            parser.error("--print-download-url requires --download-time")
        configure_logging(False)
        LOGGER.info("%s", spritzwrf.meteo_uniparthenope_wrf_url(download_date, download_cycle_hour))
        return 0
    result = downscale_wrf_to_100m(
        args.wrf,
        args.output,
        center_lat=args.center_lat,
        center_lon=args.center_lon,
        nx=args.nx,
        ny=args.ny,
        dx_m=args.dx,
        dy_m=args.dy,
        time_index=args.time_index,
        level_index=args.level_index,
        prefer_netcdf=not args.json,
        allow_synthetic=args.allow_synthetic,
        download_date=download_date,
        download_cycle_hour=download_cycle_hour,
        download_dir=args.download_dir,
        force_download=args.force_download,
        download_timeout_s=args.download_timeout_s,
        dem_path=args.dem,
        land_cover_path=args.land_cover,
    )
    configure_logging(False)
    LOGGER.info("%s", result.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
