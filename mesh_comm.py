"""mesh_comm.py

Bridgefy-style offline communication (Bluetooth mesh simulation).

Design goals:
- Pure Python, no external dependencies
- Optional: importing/using this module is required to activate it
- File-backed queues so messages survive restarts
- TTL decreases per hop, duplicate suppression prevents flooding
- Simulated discovery via a shared device registry file

Core API:
- send_mesh_alert(message: dict)
- receive_mesh_alert(message: dict)
- sync_mesh_network()
- get_pending_messages()

Environment variables (optional):
- MESH_DEVICE_ID: current device/node identifier
- MESH_STORAGE_DIR: directory for mesh state files
- MESH_LAT, MESH_LON: current device location (floats)
- MESH_RANGE_M: discovery range (meters)
- MESH_DEVICE_TTL_SEC: device registry entry TTL (seconds)
- MESH_DEFAULT_TTL: default message ttl hops when missing
"""

from __future__ import annotations

import json
import os
import socket
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_device_id() -> str:
    return os.getenv("MESH_DEVICE_ID") or socket.gethostname() or "unknown-device"


def _get_storage_dir() -> Path:
    configured = os.getenv("MESH_STORAGE_DIR")
    if configured:
        return Path(configured)

    # Default to a local folder next to this module; keeps it isolated.
    return Path(__file__).parent / "alerts" / "mesh"


def _get_device_location() -> Tuple[float, float]:
    try:
        lat = float(os.getenv("MESH_LAT", "0") or "0")
        lon = float(os.getenv("MESH_LON", "0") or "0")
        return lat, lon
    except Exception:
        return 0.0, 0.0


def _get_range_m() -> float:
    try:
        return float(os.getenv("MESH_RANGE_M", "120") or "120")
    except Exception:
        return 120.0


def _get_device_ttl_sec() -> int:
    try:
        return int(os.getenv("MESH_DEVICE_TTL_SEC", "90") or "90")
    except Exception:
        return 90


def _get_default_msg_ttl() -> int:
    try:
        return int(os.getenv("MESH_DEFAULT_TTL", "6") or "6")
    except Exception:
        return 6


_DEVICE_ID = _get_device_id()
_STORAGE_DIR = _get_storage_dir()
_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------------------------------------------------------
# Files
# -----------------------------------------------------------------------------


def _path_pending(device_id: str = _DEVICE_ID) -> Path:
    return _STORAGE_DIR / f"pending_{device_id}.json"


def _path_inbox(device_id: str) -> Path:
    return _STORAGE_DIR / f"inbox_{device_id}.jsonl"


def _path_seen(device_id: str = _DEVICE_ID) -> Path:
    return _STORAGE_DIR / f"seen_{device_id}.json"


def _path_sent_index(device_id: str = _DEVICE_ID) -> Path:
    return _STORAGE_DIR / f"sent_index_{device_id}.json"


def _path_received_log(device_id: str = _DEVICE_ID) -> Path:
    return _STORAGE_DIR / f"received_{device_id}.jsonl"


def _path_devices_registry() -> Path:
    return _STORAGE_DIR / "devices.json"


# -----------------------------------------------------------------------------
# Minimal, safe file IO helpers
# -----------------------------------------------------------------------------


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_atomic(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _read_jsonl_and_truncate(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        # truncate best-effort
        try:
            path.write_text("", encoding="utf-8")
        except Exception:
            pass
        out: List[Dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []


# -----------------------------------------------------------------------------
# Distance / discovery
# -----------------------------------------------------------------------------


def _haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    # Small dependency-free haversine
    import math

    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lon2 - lon1)
    dlmb = math.radians(lon2 - lon1)

    s = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2.0) ** 2
    )
    return 2.0 * r * math.asin(min(1.0, math.sqrt(s)))


def _update_registry() -> None:
    registry = _read_json(_path_devices_registry(), default={})
    lat, lon = _get_device_location()

    registry[_DEVICE_ID] = {
        "device_id": _DEVICE_ID,
        "timestamp": _now_iso(),
        "last_seen_epoch": time.time(),
        "location": [lat, lon],
        "range_m": _get_range_m(),
    }
    _write_json_atomic(_path_devices_registry(), registry)


def _discover_neighbors() -> List[str]:
    registry = _read_json(_path_devices_registry(), default={})
    my_loc = _get_device_location()
    now = time.time()

    neighbors: List[str] = []
    for device_id, info in registry.items():
        if device_id == _DEVICE_ID:
            continue

        try:
            last_seen = float(info.get("last_seen_epoch", 0.0))
        except Exception:
            last_seen = 0.0
        if now - last_seen > _get_device_ttl_sec():
            continue

        try:
            loc = info.get("location") or [0.0, 0.0]
            other_loc = (float(loc[0]), float(loc[1]))
        except Exception:
            other_loc = (0.0, 0.0)

        # effective range is conservative: min(self_range, other_range)
        try:
            other_range = float(info.get("range_m", _get_range_m()))
        except Exception:
            other_range = _get_range_m()

        effective_range = min(_get_range_m(), other_range)
        if _haversine_m(my_loc, other_loc) <= effective_range:
            neighbors.append(device_id)

    return neighbors


# -----------------------------------------------------------------------------
# Message normalization / duplicate suppression
# -----------------------------------------------------------------------------


_REQUIRED_KEYS = {"id", "timestamp", "location", "risk_level", "message", "ttl"}


def _normalize_message(message: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(message, dict):
        raise TypeError("message must be a dict")

    msg = dict(message)

    # Fill missing fields conservatively.
    msg.setdefault("id", str(uuid.uuid4()))
    msg.setdefault("timestamp", _now_iso())

    loc = msg.get("location", (0.0, 0.0))
    if isinstance(loc, (list, tuple)) and len(loc) == 2:
        try:
            msg["location"] = (float(loc[0]), float(loc[1]))
        except Exception:
            msg["location"] = (0.0, 0.0)
    else:
        msg["location"] = (0.0, 0.0)

    rl = str(msg.get("risk_level", "LOW") or "LOW").upper()
    if rl not in {"LOW", "MEDIUM", "HIGH"}:
        rl = "LOW"
    msg["risk_level"] = rl

    msg.setdefault("message", "")

    try:
        msg_ttl = int(msg.get("ttl", _get_default_msg_ttl()))
    except Exception:
        msg_ttl = _get_default_msg_ttl()
    msg["ttl"] = max(0, msg_ttl)

    return msg


def _load_seen() -> set[str]:
    raw = _read_json(_path_seen(), default=[])
    if isinstance(raw, list):
        return {str(x) for x in raw}
    return set()


def _save_seen(seen: set[str]) -> None:
    # Keep bounded to prevent unbounded growth
    seen_list = list(seen)
    if len(seen_list) > 5000:
        seen_list = seen_list[-5000:]
    _write_json_atomic(_path_seen(), seen_list)


def _load_pending() -> List[Dict[str, Any]]:
    raw = _read_json(_path_pending(), default=[])
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


def _save_pending(pending: List[Dict[str, Any]]) -> None:
    _write_json_atomic(_path_pending(), pending)


def _load_sent_index() -> Dict[str, List[str]]:
    raw = _read_json(_path_sent_index(), default={})
    if isinstance(raw, dict):
        out: Dict[str, List[str]] = {}
        for k, v in raw.items():
            if isinstance(v, list):
                out[str(k)] = [str(x) for x in v]
        return out
    return {}


def _save_sent_index(index: Dict[str, List[str]]) -> None:
    # bound size
    if len(index) > 5000:
        # drop oldest-ish by insertion order (py3.7+)
        for k in list(index.keys())[: len(index) - 5000]:
            index.pop(k, None)
    _write_json_atomic(_path_sent_index(), index)


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


def send_mesh_alert(message: Dict[str, Any]) -> None:
    """Queue a message for mesh propagation.

    This stores the message locally and will forward it to neighbors on the next
    sync. No network access is required.
    """
    msg = _normalize_message(message)

    seen = _load_seen()
    # Mark as seen on origin to avoid re-processing our own alert later.
    seen.add(str(msg["id"]))
    _save_seen(seen)

    pending = _load_pending()

    # Avoid queuing duplicates.
    existing_ids = {str(m.get("id")) for m in pending}
    if str(msg["id"]) not in existing_ids:
        pending.append(msg)
        _save_pending(pending)


def receive_mesh_alert(message: Dict[str, Any]) -> None:
    """Receive a mesh alert, store it, and queue it for forwarding if TTL>0."""
    msg = _normalize_message(message)
    msg_id = str(msg["id"])

    seen = _load_seen()
    if msg_id in seen:
        return

    seen.add(msg_id)
    _save_seen(seen)

    _append_jsonl(_path_received_log(), msg)

    # Queue for forwarding if it can still hop.
    if int(msg.get("ttl", 0)) > 0:
        pending = _load_pending()
        pending.append(msg)
        _save_pending(pending)


def sync_mesh_network() -> None:
    """Simulate discovery + message exchange.

    - Updates device registry entry for this node.
    - Pulls and processes messages delivered to our inbox.
    - Forwards pending messages to currently-discovered neighbors.

    Call this periodically to simulate motion/discovery.
    """

    # 1) refresh our presence
    _update_registry()

    # 2) process inbound messages delivered by peers
    inbox_path = _path_inbox(_DEVICE_ID)
    inbound = _read_jsonl_and_truncate(inbox_path)
    for msg in inbound:
        try:
            receive_mesh_alert(msg)
        except Exception:
            # Never allow mesh simulation to crash the host process
            continue

    # 3) forward our pending messages to neighbors
    neighbors = _discover_neighbors()
    if not neighbors:
        return

    pending = _load_pending()
    if not pending:
        return

    sent_index = _load_sent_index()

    new_pending: List[Dict[str, Any]] = []
    for msg in pending:
        if not isinstance(msg, dict):
            continue

        try:
            msg = _normalize_message(msg)
        except Exception:
            continue

        msg_id = str(msg["id"])
        ttl = int(msg.get("ttl", 0))

        already_sent_to = set(sent_index.get(msg_id, []))
        delivered_any = False

        # If TTL is exhausted, don't forward further.
        if ttl <= 0:
            continue

        # Forward with ttl-1 for each hop.
        forwarded = dict(msg)
        forwarded["ttl"] = max(0, ttl - 1)

        for neighbor_id in neighbors:
            if neighbor_id in already_sent_to:
                continue

            try:
                _append_jsonl(_path_inbox(neighbor_id), forwarded)
                already_sent_to.add(neighbor_id)
                delivered_any = True
            except Exception:
                # Best effort: if we couldn't write, we keep it pending.
                continue

        if already_sent_to:
            sent_index[msg_id] = sorted(already_sent_to)

        # Keep pending if it couldn't be delivered to anyone yet.
        # Once delivered to at least one neighbor, we drop it locally to avoid
        # repeated flooding; neighbors will forward if needed.
        if not delivered_any:
            new_pending.append(msg)

    _save_sent_index(sent_index)
    _save_pending(new_pending)


def get_pending_messages() -> List[Dict[str, Any]]:
    """Return the current device's queued messages awaiting forwarding."""
    return _load_pending()
