"""ESA SNAP adapter.

This module exposes a safe wrapper around SNAP/GPT processing so any
future real Sentinel-1 products can be processed without touching the
current simulation pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from insar_processing import run_snap_graph


@dataclass(slots=True)
class SNAPAdapter:
    name: str = "esa_snap"

    def fetch(self, master_path: str | None = None, slave_path: str | None = None, output_dir: str | None = None, **_: Any) -> dict[str, Any] | None:
        if not master_path or not slave_path or not output_dir:
            return None

        try:
            output = run_snap_graph(master_path, slave_path, output_dir)
            if not output:
                return None
            return {"source": self.name, "output_path": output, "available": True}
        except Exception:
            return None

    def parse_unwrapped_phase(self, phase_path: str | Path) -> dict[str, Any]:
        # The current project does not expose a public SNAPHU parser helper.
        # This method remains as an extension hook and degrades safely.
        return {"available": False, "path": str(phase_path), "source": self.name}
