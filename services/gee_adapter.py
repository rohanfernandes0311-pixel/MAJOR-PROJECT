"""Google Earth Engine adapter stub.

This adapter only becomes active when the Earth Engine client libraries
and credentials are available. Otherwise it returns None and the caller
falls back to the existing simulated or local raster workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GEEAdapter:
    name: str = "google_earth_engine"

    def is_available(self) -> bool:
        try:
            import ee  # type: ignore
            return True
        except Exception:
            return False

    def fetch(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        if not self.is_available():
            return None

        try:
            import ee  # type: ignore
        except Exception:
            return None

        # Intentionally minimal: this is an injectable adapter hook.
        # Concrete Earth Engine export logic can be bound later without
        # changing the core project structure.
        return {"source": self.name, "available": True}
