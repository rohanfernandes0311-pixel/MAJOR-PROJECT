"""Offline-first cache and buffering utilities.

The service stores lightweight JSONL records locally and can mirror
important events into existing storage channels when available. It is
designed to be safe to import even when the surrounding application does
not enable offline synchronization.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class OfflineCacheService:
    storage_dir: Path
    namespace: str = "landsense"
    max_items: int = 2000
    _buffer: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    @property
    def cache_file(self) -> Path:
        return self.storage_dir / f"{self.namespace}_cache.jsonl"

    @property
    def sync_file(self) -> Path:
        return self.storage_dir / f"{self.namespace}_sync.jsonl"

    def record(self, event_type: str, payload: dict[str, Any], *, syncable: bool = True) -> dict[str, Any]:
        item = {
            "timestamp": _utc_iso(),
            "event_type": event_type,
            "syncable": bool(syncable),
            "payload": payload,
        }
        self._buffer.append(item)
        self._buffer = self._buffer[-self.max_items :]
        self._append_jsonl(self.cache_file, item)
        return item

    def persist_prediction(self, prediction: dict[str, Any], *, region: str | None = None) -> dict[str, Any]:
        item = self.record(
            "prediction",
            {"region": region, "prediction": prediction},
            syncable=True,
        )
        return item

    def persist_alert(self, alert: Any) -> dict[str, Any]:
        payload = asdict(alert) if hasattr(alert, "__dataclass_fields__") else dict(alert)
        return self.record("alert", payload, syncable=True)

    def flush(self) -> list[dict[str, Any]]:
        if not self._buffer:
            return []

        flushed = list(self._buffer)
        for item in flushed:
            self._append_jsonl(self.sync_file, item)
        self._buffer.clear()
        return flushed

    def load_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        path = self.cache_file
        if not path.exists():
            return []

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []

        recent: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                recent.append(json.loads(line))
            except Exception:
                continue
        return recent

    def _append_jsonl(self, path: Path, item: dict[str, Any]) -> None:
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception:
            # The cache must never block the primary workflow.
            return
