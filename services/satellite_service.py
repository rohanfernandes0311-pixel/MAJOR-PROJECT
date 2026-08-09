"""Optional satellite data integration layer.

The service combines optional Sentinel-1 / SNAP / Earth Engine / raster
adapters while preserving the simulated InSAR stack as a safe fallback.
No existing processing path is modified; this layer is only used when
explicitly invoked by future extensions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from insar_processing import simulate_insar_stack


class SatelliteAdapter(Protocol):
    name: str

    def fetch(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        ...


@dataclass(slots=True)
class SatelliteFeatureBundle:
    displacement: np.ndarray
    coherence: np.ndarray
    dates: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SatelliteFeatureService:
    adapters: list[SatelliteAdapter] = field(default_factory=list)
    fallback_pixels: int = 200
    fallback_dates: int = 24

    def load_stack(self, *, master_path: str | None = None, slave_path: str | None = None, geotiff_path: str | None = None) -> SatelliteFeatureBundle:
        for adapter in self.adapters:
            try:
                result = adapter.fetch(master_path=master_path, slave_path=slave_path, geotiff_path=geotiff_path)
                if result and "displacement" in result and "coherence" in result and "dates" in result:
                    return SatelliteFeatureBundle(
                        displacement=np.asarray(result["displacement"]),
                        coherence=np.asarray(result["coherence"]),
                        dates=result["dates"],
                        metadata={k: v for k, v in result.items() if k not in {"displacement", "coherence", "dates"}},
                    )
            except Exception:
                continue

        disp, coh, dates = simulate_insar_stack(n_pixels=self.fallback_pixels, n_dates=self.fallback_dates)
        return SatelliteFeatureBundle(displacement=disp, coherence=coh, dates=dates, metadata={"source": "simulated"})

    def feature_from_geotiff(self, geotiff_path: str | Path) -> dict[str, Any]:
        path = Path(geotiff_path)
        if not path.exists():
            return {"source": "missing", "path": str(path), "available": False}
        return {"source": "geotiff", "path": str(path), "available": True}
