from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import numpy as np

from sprtz.exceptions import SpritzError

RasterKind = Literal["dem", "landcover"]


class TerrainProviderError(SpritzError, RuntimeError):
    """Base error for terrain data acquisition failures."""


class TerrainConfigurationError(TerrainProviderError, ValueError):
    """Raised when terrain acquisition configuration is incomplete or invalid."""


class TerrainDependencyError(TerrainProviderError, ImportError):
    """Raised when an optional geospatial dependency is needed but not installed."""


class TerrainNetworkDisabledError(TerrainProviderError):
    """Raised when a provider would need network access but it was not enabled."""


@dataclass(frozen=True)
class RasterData:
    """A source raster plus enough metadata to make resampling traceable.

    Values are stored as a 2-D array. Local lightweight rasters use a centered
    regular grid in metres; GeoTIFF/COG/NetCDF adapters may provide richer CRS
    metadata, but must still expose deterministic source spacing for the current
    Spritz regridding pipeline.
    """

    values: np.ndarray
    kind: RasterKind
    source: str
    provider: str
    dataset: str
    resolution: str
    crs: str = "LOCAL"
    x_spacing_m: float = 100.0
    y_spacing_m: float = 100.0
    nodata: float | None = None
    access_date: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validated(self) -> "RasterData":
        values = np.asarray(self.values, dtype=float)
        if values.ndim != 2:
            raise TerrainConfigurationError(f"{self.kind} raster must be two-dimensional")
        if values.size == 0:
            raise TerrainConfigurationError(f"{self.kind} raster must not be empty")
        if self.x_spacing_m <= 0 or self.y_spacing_m <= 0:
            raise TerrainConfigurationError(f"{self.kind} raster spacing must be positive")
        return RasterData(
            values=values,
            kind=self.kind,
            source=self.source,
            provider=self.provider,
            dataset=self.dataset,
            resolution=self.resolution,
            crs=self.crs,
            x_spacing_m=float(self.x_spacing_m),
            y_spacing_m=float(self.y_spacing_m),
            nodata=self.nodata,
            access_date=self.access_date,
            metadata=dict(self.metadata),
        )


@dataclass(frozen=True)
class RasterRequest:
    """Provider request for one source raster kind."""

    kind: RasterKind
    domain: Any
    cache_dir: str
    allow_network: bool = False
    options: dict[str, Any] = field(default_factory=dict)


class RasterProvider(Protocol):
    """Interface implemented by local and online Terrain data providers."""

    name: str
    dataset: str

    def fetch(self, request: RasterRequest) -> RasterData:
        """Return a source raster or raise a user-actionable provider error."""
