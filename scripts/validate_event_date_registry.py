"""Validate that recovered timing evidence is explicit and traceable."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = (
    ROOT
    / "data"
    / "research"
    / "south_india_environmental_features"
    / "event_date_registry.json"
)


def main() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assignments = registry["record_level_assignments"]
    for inventory, summary in assignments.items():
        assert summary["exact_dates"] == 0
        assert summary["bounded_intervals"] == 0
        assert summary["records"] == summary["unknown_dates"]
        assert inventory

    for evidence in registry["inventory_level_evidence"]:
        assert evidence["source_record_id"] is None
        assert evidence["date_start"] <= evidence["date_end"]
        assert evidence["precision"]
        assert evidence["source_url"].startswith(("https://", "http://"))
        assert evidence["supporting_references"]
        assert evidence["review_status"] == "inventory_only_not_record_level"

    assert registry["interpretation"]["rainfall_matching_allowed"] is False
    print("event date registry validation passed")


if __name__ == "__main__":
    main()
