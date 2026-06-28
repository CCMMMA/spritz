from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class LandUseClass:
    code: int
    name: str
    roughness_length_m: float
    albedo: float
    bowen_ratio: float
    vegetation_fraction: float


SPRTZ_LAND_USE: dict[int, LandUseClass] = {
    0: LandUseClass(0, "unknown", 0.10, 0.18, 1.0, 0.0),
    1: LandUseClass(1, "tree_cover", 1.00, 0.12, 0.7, 0.90),
    2: LandUseClass(2, "shrubland", 0.35, 0.18, 1.0, 0.60),
    3: LandUseClass(3, "grassland", 0.05, 0.20, 0.8, 0.70),
    4: LandUseClass(4, "cropland", 0.10, 0.18, 0.6, 0.80),
    5: LandUseClass(5, "built_up", 1.20, 0.15, 2.0, 0.10),
    6: LandUseClass(6, "bare_sparse", 0.03, 0.28, 4.0, 0.05),
    7: LandUseClass(7, "snow_ice", 0.01, 0.70, 0.1, 0.00),
    8: LandUseClass(8, "permanent_water", 0.0002, 0.08, 0.0, 0.00),
    9: LandUseClass(9, "herbaceous_wetland", 0.20, 0.14, 0.2, 0.90),
    10: LandUseClass(10, "mangroves", 0.80, 0.12, 0.4, 0.95),
    11: LandUseClass(11, "moss_lichen", 0.04, 0.22, 0.7, 0.40),
}

# ESA WorldCover encodes land cover. Spritz needs internal land-use classes and
# surface parameters; this clean-room crosswalk is deliberately visible so users
# can replace it with project-specific validation data.
ESA_WORLDCOVER_TO_SPRTZ = {
    10: 1,   # Tree cover
    20: 2,   # Shrubland
    30: 3,   # Grassland
    40: 4,   # Cropland
    50: 5,   # Built-up
    60: 6,   # Bare/sparse vegetation
    70: 7,   # Snow and ice
    80: 8,   # Permanent water bodies
    90: 9,   # Herbaceous wetland
    95: 10,  # Mangroves
    100: 11, # Moss and lichen
}

# Copernicus Global Land Cover 100 m discrete classification (PROBA-V LC100)
# uses several forest sub-classes plus broad non-forest classes. Sprtz keeps the
# crosswalk explicit because these source labels are land cover, not model-ready
# land-use parameters.
COPERNICUS_LC100_TO_SPRTZ = {
    0: 0,    # Unknown / no data
    20: 2,   # Shrubs
    30: 3,   # Herbaceous vegetation
    40: 4,   # Cultivated and managed vegetation / agriculture
    50: 5,   # Urban / built up
    60: 6,   # Bare / sparse vegetation
    70: 7,   # Snow and ice
    80: 8,   # Permanent water bodies
    90: 9,   # Herbaceous wetland
    100: 11, # Moss and lichen
    111: 1,  # Closed forest, evergreen needle leaf
    112: 1,  # Closed forest, evergreen broad leaf
    113: 1,  # Closed forest, deciduous needle leaf
    114: 1,  # Closed forest, deciduous broad leaf
    115: 1,  # Closed forest, mixed
    116: 1,  # Closed forest, unknown
    121: 1,  # Open forest, evergreen needle leaf
    122: 1,  # Open forest, evergreen broad leaf
    123: 1,  # Open forest, deciduous needle leaf
    124: 1,  # Open forest, deciduous broad leaf
    125: 1,  # Open forest, mixed
    126: 1,  # Open forest, unknown
    200: 8,  # Open sea / ocean
}


LAND_COVER_MAPPINGS = {
    "esa-worldcover": ESA_WORLDCOVER_TO_SPRTZ,
    "worldcover": ESA_WORLDCOVER_TO_SPRTZ,
    "sprtz": ESA_WORLDCOVER_TO_SPRTZ,
    "copernicus-lc100": COPERNICUS_LC100_TO_SPRTZ,
    "lc100": COPERNICUS_LC100_TO_SPRTZ,
    "copernicus-global-land-cover-100m": COPERNICUS_LC100_TO_SPRTZ,
}


def land_cover_mapping(name: str | None) -> dict[int, int]:
    """Return a visible source land-cover to Sprtz land-use crosswalk."""
    if not name:
        return ESA_WORLDCOVER_TO_SPRTZ
    key = str(name).strip().lower()
    try:
        return LAND_COVER_MAPPINGS[key]
    except KeyError as exc:
        choices = ", ".join(sorted(LAND_COVER_MAPPINGS))
        raise ValueError(
            f"unsupported land-cover mapping {name!r}; choose one of: {choices}"
        ) from exc


def remap_land_cover(
    land_cover: np.ndarray,
    mapping: dict[int, int] | None = None,
) -> np.ndarray:
    """Map source land-cover labels to Spritz land-use class codes."""
    source_to_target = mapping or ESA_WORLDCOVER_TO_SPRTZ
    source = np.asarray(land_cover, dtype=int)
    out = np.zeros_like(source, dtype=int)
    for source_code, target_code in source_to_target.items():
        out[source == int(source_code)] = int(target_code)
    return out


def derive_surface_parameters(landuse: np.ndarray) -> dict[str, np.ndarray]:
    """Derive minimal surface parameters from Spritz land-use classes."""
    classes = np.asarray(landuse, dtype=int)
    params = {
        "roughness_length_m": np.zeros(classes.shape, dtype=float),
        "albedo": np.zeros(classes.shape, dtype=float),
        "bowen_ratio": np.zeros(classes.shape, dtype=float),
        "vegetation_fraction": np.zeros(classes.shape, dtype=float),
    }
    for code, item in SPRTZ_LAND_USE.items():
        mask = classes == code
        params["roughness_length_m"][mask] = item.roughness_length_m
        params["albedo"][mask] = item.albedo
        params["bowen_ratio"][mask] = item.bowen_ratio
        params["vegetation_fraction"][mask] = item.vegetation_fraction
    return params


def landuse_table_payload() -> list[dict[str, object]]:
    return [asdict(SPRTZ_LAND_USE[code]) for code in sorted(SPRTZ_LAND_USE)]
