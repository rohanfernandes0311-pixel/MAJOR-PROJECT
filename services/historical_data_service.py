"""Historical data ingestion and archival helpers.

Supports optional CSV, GeoJSON, and archive-based ingestion while keeping
the synthetic dataset workflow as the default and non-breaking path.
"""

from __future__ import annotations

import csv
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(slots=True)
class HistoricalDataService:
    base_dir: Path

    def load_csv(self, path: str | Path) -> pd.DataFrame:
        csv_path = Path(path)
        if not csv_path.exists():
            raise FileNotFoundError(str(csv_path))
        return pd.read_csv(csv_path)

    def load_geojson(self, path: str | Path) -> dict[str, Any]:
        geo_path = Path(path)
        if not geo_path.exists():
            raise FileNotFoundError(str(geo_path))
        return json.loads(geo_path.read_text(encoding="utf-8"))

    def ingest_zip_archive(self, path: str | Path, extract_to: str | Path | None = None) -> list[Path]:
        archive_path = Path(path)
        if not archive_path.exists():
            raise FileNotFoundError(str(archive_path))

        target_dir = Path(extract_to) if extract_to else self.base_dir / "data" / "historical_ingest"
        target_dir.mkdir(parents=True, exist_ok=True)
        extracted: list[Path] = []
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.namelist():
                if member.endswith((".csv", ".geojson", ".json")):
                    zf.extract(member, target_dir)
                    extracted.append(target_dir / member)
        return extracted

    def merge_sources(self, sources: list[pd.DataFrame]) -> pd.DataFrame:
        if not sources:
            return pd.DataFrame()
        merged = pd.concat(sources, ignore_index=True, sort=False)
        return merged
