"""Dynamic threshold configuration for optional region-specific tuning.

This service preserves the hardcoded alert thresholds as the default
fallback. It can optionally merge overrides from JSON and SQLite without
changing the behavior of the existing alert pipeline when those sources
are absent.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alert_system import THRESHOLDS as DEFAULT_THRESHOLDS


@dataclass(slots=True)
class ThresholdConfigService:
    base_thresholds: dict[str, dict[str, float]] = field(default_factory=lambda: {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()})
    json_path: Path | None = None
    sqlite_path: Path | None = None

    def load(self, region: str | None = None) -> dict[str, dict[str, float]]:
        thresholds = {k: dict(v) for k, v in self.base_thresholds.items()}
        thresholds.update(self._load_json_overrides(region))
        thresholds.update(self._load_sqlite_overrides(region))
        return thresholds

    def _load_json_overrides(self, region: str | None) -> dict[str, dict[str, float]]:
        path = self.json_path
        if path is None or not path.exists():
            return {}

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

        if isinstance(payload, dict):
            if region and isinstance(payload.get(region), dict):
                return self._sanitize(payload[region])
            if isinstance(payload.get("thresholds"), dict):
                return self._sanitize(payload["thresholds"])
        return {}

    def _load_sqlite_overrides(self, region: str | None) -> dict[str, dict[str, float]]:
        path = self.sqlite_path
        if path is None or not path.exists():
            return {}

        try:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
        except Exception:
            return {}

        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT feature_name, high_threshold, medium_threshold
                FROM threshold_overrides
                WHERE region = ? OR region IS NULL
                ORDER BY CASE WHEN region = ? THEN 0 ELSE 1 END
                """,
                (region, region),
            )
            rows = cur.fetchall()
        except Exception:
            conn.close()
            return {}
        finally:
            conn.close()

        merged: dict[str, dict[str, float]] = {}
        for row in rows:
            feature_name = str(row["feature_name"])
            high_val = row["high_threshold"]
            medium_val = row["medium_threshold"]
            feature = merged.setdefault(feature_name, {})
            if high_val is not None:
                feature["HIGH"] = float(high_val)
            if medium_val is not None:
                feature["MEDIUM"] = float(medium_val)
        return merged

    @staticmethod
    def _sanitize(candidate: Any) -> dict[str, dict[str, float]]:
        sanitized: dict[str, dict[str, float]] = {}
        if not isinstance(candidate, dict):
            return sanitized

        for feature_name, feature_values in candidate.items():
            if not isinstance(feature_values, dict):
                continue
            cleaned: dict[str, float] = {}
            for level in ("HIGH", "MEDIUM", "LOW"):
                value = feature_values.get(level)
                try:
                    if value is not None:
                        cleaned[level] = float(value)
                except Exception:
                    continue
            if cleaned:
                sanitized[str(feature_name)] = cleaned
        return sanitized

    def threshold_for(self, feature_name: str, region: str | None = None) -> dict[str, float]:
        return self.load(region).get(feature_name, dict(self.base_thresholds.get(feature_name, {})))
