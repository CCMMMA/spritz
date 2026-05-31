from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from sprtz.exceptions import DataFormatError


def read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    try:
        with p.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise DataFormatError(f"JSON file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise DataFormatError(f"invalid JSON in {p}: {exc}") from exc
    if not isinstance(data, dict):
        raise DataFormatError("configuration root must be a JSON object")
    return data


def write_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=p.parent, delete=False) as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
        tmp_name = handle.name
    Path(tmp_name).replace(p)
