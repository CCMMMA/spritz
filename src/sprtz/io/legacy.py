from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LegacyControl:
    values: dict[str, str]

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.values.get(key.upper(), default)

    def get_int(self, key: str, default: int) -> int:
        value = self.get(key)
        return default if value is None else int(float(value))

    def get_float(self, key: str, default: float) -> float:
        value = self.get(key)
        return default if value is None else float(value)


def parse_legacy_text(text: str) -> LegacyControl:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("!", 1)[0].split("#", 1)[0].strip()
        if not line:
            continue
        if "=" in line:
            key, value = line.split("=", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            key, value = parts
        values[key.strip().upper()] = value.strip().strip('"\'')
    return LegacyControl(values)


def parse_legacy_file(path: str | Path) -> LegacyControl:
    return parse_legacy_text(Path(path).read_text(encoding="utf-8"))
