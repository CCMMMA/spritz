from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sprtz.io.jsonio import write_json

DEFAULT_CACHE = Path.home() / ".cache" / "sprtz" / "terrain"


def terrain_cache_dir(override: str | Path | None = None) -> Path:
    """Resolve the deterministic terrain cache directory."""
    value = override or os.environ.get("SPRTZ_TERRAIN_CACHE")
    return Path(value).expanduser() if value else DEFAULT_CACHE


def cache_key(parts: dict[str, Any]) -> str:
    """Build a stable cache key from provider, dataset, AOI, CRS, and resolution metadata."""
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def write_cache_metadata(cache_dir: str | Path, key: str, metadata: dict[str, Any]) -> Path:
    """Write human-readable metadata for cached or derived terrain inputs."""
    path = Path(cache_dir) / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        path,
        {
            "cache_key": key,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **metadata,
        },
    )
    return path
