from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from sprtz.exceptions import DataFormatError
from sprtz.io.netcdf_cf import _concentration_field

CALPUFF_CONC_SCHEMA_VERSION = 1
CALPUFF_CONC_MISSING_VALUE = -9999.0


def _record(handle: Any, payload: bytes, endian: str) -> None:
    marker = np.asarray([len(payload)], dtype=np.dtype(f"{endian}i4")).tobytes()
    handle.write(marker)
    handle.write(payload)
    handle.write(marker)


def _text_record(*values: str, width: int = 80) -> bytes:
    return b"".join(str(value)[:width].ljust(width).encode("ascii", errors="replace") for value in values)


def _i4_record(values: list[int] | tuple[int, ...], endian: str) -> bytes:
    return np.asarray(values, dtype=np.dtype(f"{endian}i4")).tobytes()


def _f4_record(values: Any, endian: str) -> bytes:
    arr = np.asarray(values, dtype=np.float32)
    arr = np.nan_to_num(
        arr,
        nan=CALPUFF_CONC_MISSING_VALUE,
        posinf=CALPUFF_CONC_MISSING_VALUE,
        neginf=CALPUFF_CONC_MISSING_VALUE,
    )
    return np.ascontiguousarray(arr.astype(np.dtype(f"{endian}f4"), copy=False)).tobytes(order="C")


def write_calpuff_concentration_dat(
    path: str | Path,
    rows: list[dict[str, Any]],
    *,
    title: str = "Sprtz clean-room CALPUFF concentration export",
    endian: str = ">",
) -> str:
    """Write a clean-room CALPUFF-style binary concentration grid.

    The canonical Sprtz concentration interchange remains NetCDF-CF. This
    export mirrors the gridded `time,z,y,x` concentration fields into Fortran
    sequential unformatted records so external comparison tools can consume the
    same horizontal and vertical grid from Gaussian and particle runs.
    """
    if endian not in {">", "<"}:
        raise ValueError("endian must be '>' for big-endian or '<' for little-endian")
    field = _concentration_field(rows)
    if field is None:
        raise DataFormatError("CALPUFF-style binary export requires complete gridded concentration_field rows")
    times = np.asarray(field["time"], dtype=float)
    x = np.asarray(field["x"], dtype=float)
    y = np.asarray(field["y"], dtype=float)
    z = np.asarray(field["z"], dtype=float)
    concentration = np.asarray(field["concentration"], dtype=float)
    dry_flux = np.asarray(field["dry_flux"], dtype=float)
    wet_flux = np.asarray(field["wet_flux"], dtype=float)
    expected_shape = (times.size, z.size, y.size, x.size)
    for name, values in [
        ("concentration", concentration),
        ("dry_flux", dry_flux),
        ("wet_flux", wet_flux),
    ]:
        if values.shape != expected_shape:
            raise DataFormatError(f"{name} shape {values.shape} must match {expected_shape}")
    datetime_by_time: dict[float, str] = {}
    for row in rows:
        if row.get("datetime"):
            datetime_by_time.setdefault(float(row.get("time", 0.0)), str(row["datetime"]))
    labels = [datetime_by_time.get(float(value), f"time_s_{float(value):.3f}") for value in times]
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(out.parent), prefix=f".{out.name}.", suffix=".tmp") as tmp:
        tmp_path = Path(tmp.name)
        _record(
            tmp,
            _text_record(
                "CALPUFF.CONC",
                title,
                "Sprtz clean-room binary export",
                f"schema={CALPUFF_CONC_SCHEMA_VERSION}",
            ),
            endian,
        )
        _record(tmp, _i4_record([CALPUFF_CONC_SCHEMA_VERSION, x.size, y.size, z.size, times.size, 3], endian), endian)
        _record(tmp, _f4_record(x, endian), endian)
        _record(tmp, _f4_record(y, endian), endian)
        _record(tmp, _f4_record(z, endian), endian)
        _record(tmp, _f4_record(times, endian), endian)
        _record(tmp, _text_record(*labels, width=32), endian)
        _record(tmp, _text_record("CONCENTRATION_G_M3", "DRY_FLUX_G_M2_S", "WET_FLUX_G_M2_S"), endian)
        for time_index in range(times.size):
            _record(tmp, _i4_record([time_index], endian), endian)
            for level_index in range(z.size):
                _record(tmp, _i4_record([time_index, level_index], endian), endian)
                _record(tmp, _f4_record(concentration[time_index, level_index], endian), endian)
                _record(tmp, _f4_record(dry_flux[time_index, level_index], endian), endian)
                _record(tmp, _f4_record(wet_flux[time_index, level_index], endian), endian)
    tmp_path.replace(out)
    return "CALPUFF.CONC"
