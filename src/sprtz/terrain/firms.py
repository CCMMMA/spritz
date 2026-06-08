from __future__ import annotations

from io import StringIO
import logging
import math
import os
from pathlib import Path
import urllib.request

from sprtz.config import FIRMSConfig, FireIgnitionPoint


class FIRMSDownloader:
    """Download and convert NASA FIRMS active-fire detections."""

    BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

    def __init__(self, config: FIRMSConfig):
        self.cfg = config
        self._log = logging.getLogger(__name__)

    def _get_map_key(self) -> str:
        key = os.environ.get(self.cfg.map_key_env, "").strip()
        if not key:
            raise OSError(f"FIRMS API key not found. Set {self.cfg.map_key_env}.")
        return key

    def _build_url(self, bbox: tuple[float, float, float, float]) -> str:
        bbox_str = ",".join(f"{v:.4f}" for v in bbox)
        key = self._get_map_key()
        tail = f"{self.cfg.day_range}/{self.cfg.date}" if self.cfg.date else str(self.cfg.day_range)
        return f"{self.BASE_URL}/{key}/{self.cfg.source}/{bbox_str}/{tail}"

    def _cache_path(self, bbox: tuple[float, float, float, float]) -> str:
        w, s, e, n = bbox
        name = f"firms_{self.cfg.source}_{w:.2f}_{s:.2f}_{e:.2f}_{n:.2f}_{self.cfg.date or self.cfg.day_range}.csv"
        return str(Path(self.cfg.cache_dir) / name)

    def download(self, bbox: tuple[float, float, float, float]):
        import pandas as pd

        if self.cfg.cache_dir:
            cache_path = self._cache_path(bbox)
            if os.path.exists(cache_path):
                return pd.read_csv(cache_path)
        url = self._build_url(bbox)
        self._log.info("FIRMS: downloading from %s", url.replace(self._get_map_key(), "***"))
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = resp.read().decode("utf-8")
        except Exception as exc:
            raise RuntimeError(f"FIRMS download failed: {exc}") from exc
        df = pd.read_csv(StringIO(data))
        if self.cfg.cache_dir:
            Path(self.cfg.cache_dir).mkdir(parents=True, exist_ok=True)
            df.to_csv(self._cache_path(bbox), index=False)
        return df

    def filter(self, df):
        out = df[df["confidence"].isin(self.cfg.confidence_filter)]
        if "frp" in out.columns:
            out = out[out["frp"] >= self.cfg.min_frp_mw]
        return out.reset_index(drop=True)

    def to_ignition_points(self, df) -> list[FireIgnitionPoint]:
        if df.empty:
            return []
        import pandas as pd

        work = df.copy()
        work["acq_datetime"] = pd.to_datetime(work["acq_date"] + " " + work["acq_time"].astype(str).str.zfill(4), format="%Y-%m-%d %H%M", utc=True)
        work = work.sort_values("acq_datetime")
        if self.cfg.cluster_distance_m > 0:
            work = self._cluster_hotspots(work)
        return [FireIgnitionPoint(lat=float(row["latitude"]), lon=float(row["longitude"]), time=row["acq_datetime"].isoformat()) for _, row in work.iterrows()]

    def _cluster_hotspots(self, df):
        rows = list(df.to_dict("records"))
        clusters: list[list[dict]] = []
        for row in rows:
            placed = False
            for cluster in clusters:
                if _haversine_m(float(row["latitude"]), float(row["longitude"]), float(cluster[0]["latitude"]), float(cluster[0]["longitude"])) <= self.cfg.cluster_distance_m:
                    cluster.append(row)
                    placed = True
                    break
            if not placed:
                clusters.append([row])
        import pandas as pd

        merged = []
        for cluster in clusters:
            merged.append(
                {
                    **cluster[0],
                    "latitude": sum(float(r["latitude"]) for r in cluster) / len(cluster),
                    "longitude": sum(float(r["longitude"]) for r in cluster) / len(cluster),
                    "acq_datetime": min(r["acq_datetime"] for r in cluster),
                }
            )
        return pd.DataFrame(merged).sort_values("acq_datetime")


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))
