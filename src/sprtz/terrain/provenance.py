from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sprtz import __version__
from sprtz.terrain.cache import cache_key
from sprtz.terrain.providers.base import RasterData
from sprtz.terrain.regrid import DomainDefinition


def build_provenance(
    *,
    domain: DomainDefinition,
    dem: RasterData,
    landcover: RasterData,
    source_crs: str,
    target_crs: str,
) -> dict[str, Any]:
    """Create required provenance metadata for derived GEO/terrain products."""
    access_date = datetime.now(timezone.utc).date().isoformat()
    key = cache_key(
        {
            "dem_provider": dem.provider,
            "dem_dataset": dem.dataset,
            "dem_resolution": dem.resolution,
            "landuse_provider": landcover.provider,
            "landuse_dataset": landcover.dataset,
            "landuse_resolution": landcover.resolution,
            "domain": {
                "center_lat": domain.center_lat,
                "center_lon": domain.center_lon,
                "nx": domain.nx,
                "ny": domain.ny,
                "dx_m": domain.dx_m,
                "dy_m": domain.dy_m,
                "projection": domain.projection,
                "buffer_m": domain.buffer_m,
            },
            "target_crs": target_crs,
        }
    )
    return {
        "dem_source": dem.source,
        "dem_dataset": dem.dataset,
        "dem_resolution": dem.resolution,
        "dem_access_date": dem.access_date or access_date,
        "landuse_source": landcover.source,
        "landuse_dataset": landcover.dataset,
        "landuse_year": landcover.metadata.get("year", ""),
        "landuse_resolution": landcover.resolution,
        "source_crs": source_crs,
        "target_crs": target_crs,
        "resampling_dem": "bilinear",
        "resampling_landuse": "nearest-neighbor categorical",
        "cache_key": key,
        "software_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
