from __future__ import annotations

import logging

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from sprtz.models import spritzmet, spritzwrf
from sprtz.logging import configure_logging


LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class WindInterpolationResult:
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

    def as_dict(self) -> dict[str, Any]:
        return {
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


def _synthetic_wrf(center_lat: float, center_lon: float, nx: int = 7, ny: int = 7) -> spritzwrf.WRFWindField:
    """Create a deterministic WRF-like field for tests and documentation examples."""
    lat_axis = center_lat + (np.arange(ny) - (ny - 1) / 2.0) * 0.009
    lon_axis = center_lon + (np.arange(nx) - (nx - 1) / 2.0) * 0.012
    lon, lat = np.meshgrid(lon_axis, lat_axis)
    u = 3.5 + 0.4 * np.sin(np.deg2rad((lat - center_lat) * 100.0))
    v = 1.2 + 0.3 * np.cos(np.deg2rad((lon - center_lon) * 100.0))
    return spritzwrf.WRFWindField(lat, lon, u, v, Path("synthetic-wrf5-d03"), metadata={"synthetic": True})


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


def interpolate_wrf_to_100m(
    wrf_path: str | Path | None,
    output_path: str | Path,
    *,
    center_lat: float,
    center_lon: float,
    nx: int = 101,
    ny: int = 101,
    dx_m: float = 100.0,
    dy_m: float = 100.0,
    time_index: int = 0,
    prefer_netcdf: bool = True,
    allow_synthetic: bool = False,
    download_date: str | None = None,
    download_cycle_hour: int = 0,
    download_dir: str | Path = "data/wrf",
    force_download: bool = False,
    download_timeout_s: float = 120.0,
) -> WindInterpolationResult:
    """Downscale 1 km WRF wind to a 100 m local grid using SpritzWRF then SpritzMet.

    Workflow
    --------
    1. SpritzWRF loads a local WRF NetCDF file or downloads WRF5 d03 history data
       from the meteo@uniparthenope archive.
    2. SpritzMet creates an azimuthal-equidistant grid centered at the requested
       latitude/longitude and interpolates the SpritzWRF wind vectors to that grid.
    3. The output is written as NetCDF-CF by default, with JSON fallback.
    """
    resolved = resolve_wrf_input(
        wrf_path,
        download_date=download_date,
        download_cycle_hour=download_cycle_hour,
        download_dir=download_dir,
        force_download=force_download,
        download_timeout_s=download_timeout_s,
    )
    if resolved is not None and resolved.exists():
        wrf = spritzwrf.load_near_surface_wind(resolved, time_index=time_index)
    elif allow_synthetic:
        wrf = _synthetic_wrf(center_lat, center_lon)
    else:
        raise FileNotFoundError(
            "WRF input file is required. Pass --wrf, or use --download-date YYYY-MM-DD "
            "with --download-cycle-hour, or enable --allow-synthetic for tests."
        )
    met = spritzmet.downscale_wrf_to_local_grid(
        wrf,
        center_lat=center_lat,
        center_lon=center_lon,
        nx=nx,
        ny=ny,
        dx_m=dx_m,
        dy_m=dy_m,
    )
    fmt = spritzmet.write_local_meteorology(output_path, met, prefer_netcdf=prefer_netcdf)
    return WindInterpolationResult(Path(output_path), nx, ny, dx_m, dy_m, center_lat, center_lon, met.source, fmt)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="SpritzWRF -> SpritzMet: interpolate WRF 1 km winds to a 100 m local grid")
    parser.add_argument("--wrf", default=None, help="Local WRF NetCDF input; omit when using --download-date or --allow-synthetic")
    parser.add_argument("--download-date", default=None, help="Download meteo@uniparthenope WRF5 d03 file for YYYY-MM-DD")
    parser.add_argument("--download-cycle-hour", type=int, default=0, help="WRF cycle hour, e.g. 0, 6, 12, 18")
    parser.add_argument("--download-dir", default="data/wrf", help="Directory for downloaded WRF files")
    parser.add_argument("--download-timeout-s", type=float, default=120.0)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--print-download-url", action="store_true", help="Print the meteo@uniparthenope URL and exit")
    parser.add_argument("--output", required=True)
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lon", type=float, required=True)
    parser.add_argument("--nx", type=int, default=101)
    parser.add_argument("--ny", type=int, default=101)
    parser.add_argument("--dx", type=float, default=100.0)
    parser.add_argument("--dy", type=float, default=100.0)
    parser.add_argument("--time-index", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="write JSON even when netCDF4 is available")
    parser.add_argument("--allow-synthetic", action="store_true")
    args = parser.parse_args(argv)
    if args.print_download_url:
        if args.download_date is None:
            parser.error("--print-download-url requires --download-date")
        configure_logging(False)
        LOGGER.info("%s", spritzwrf.meteo_uniparthenope_wrf_url(args.download_date, args.download_cycle_hour))
        return 0
    result = interpolate_wrf_to_100m(
        args.wrf,
        args.output,
        center_lat=args.center_lat,
        center_lon=args.center_lon,
        nx=args.nx,
        ny=args.ny,
        dx_m=args.dx,
        dy_m=args.dy,
        time_index=args.time_index,
        prefer_netcdf=not args.json,
        allow_synthetic=args.allow_synthetic,
        download_date=args.download_date,
        download_cycle_hour=args.download_cycle_hour,
        download_dir=args.download_dir,
        force_download=args.force_download,
        download_timeout_s=args.download_timeout_s,
    )
    configure_logging(False)
    LOGGER.info("%s", result.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
