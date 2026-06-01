from __future__ import annotations

from dataclasses import dataclass

from sprtz.terrain.providers.base import (
    RasterData,
    RasterRequest,
    TerrainConfigurationError,
    TerrainNetworkDisabledError,
    TerrainProviderError,
)


@dataclass(frozen=True)
class CopernicusDEMProvider:
    """Copernicus DEM provider facade.

    The class keeps online acquisition behind an explicit provider interface so
    production deployments can plug in a STAC/COG endpoint or credentialed
    downloader without changing the Terrain pipeline. The repository test suite
    intentionally does not contact external services.
    """

    resolution: str = "30m"
    dataset: str = "Copernicus DEM GLO-30"
    name: str = "copernicus-dem"
    stac_url: str | None = None

    def fetch(self, request: RasterRequest) -> RasterData:
        if request.kind != "dem":
            raise TerrainConfigurationError("Copernicus DEM provider can only supply DEM rasters")
        if not request.allow_network:
            raise TerrainNetworkDisabledError(
                "Copernicus DEM acquisition requires network access; pass --allow-network "
                "or configure a local DEM provider for offline runs"
            )
        if not self.stac_url:
            raise TerrainProviderError(
                "Copernicus DEM online acquisition needs a configured STAC/COG endpoint "
                "or a project-specific credentialed downloader; no private credentials are bundled"
            )
        raise TerrainProviderError(
            f"Copernicus DEM STAC access is configured for {self.stac_url}, but live downloads "
            "are not implemented in the clean-room test fixture provider"
        )
