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
class ESAWorldCoverProvider:
    """ESA WorldCover land-cover provider facade.

    WorldCover classes are land cover, not dispersion-ready land use. The
    acquisition pipeline remaps them later to Sprtz internal land-use classes and
    surface parameters.
    """

    year: int = 2021
    dataset: str = "ESA WorldCover"
    name: str = "esa-worldcover"
    stac_url: str | None = None

    def fetch(self, request: RasterRequest) -> RasterData:
        if request.kind != "landcover":
            raise TerrainConfigurationError(
                "ESA WorldCover provider can only supply categorical land-cover rasters"
            )
        if not request.allow_network:
            raise TerrainNetworkDisabledError(
                "ESA WorldCover acquisition requires network access; pass --allow-network "
                "or configure a local land-cover raster for offline runs"
            )
        if not self.stac_url:
            raise TerrainProviderError(
                "ESA WorldCover online acquisition needs a configured catalog/STAC/COG endpoint; "
                "no network catalog or credentials are bundled with Sprtz"
            )
        raise TerrainProviderError(
            f"ESA WorldCover STAC access is configured for {self.stac_url}, but live downloads "
            "are not implemented in the clean-room test fixture provider"
        )
