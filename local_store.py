from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import sqlite3


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "local_store.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_schema() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            uid TEXT PRIMARY KEY,
            phone_number TEXT NOT NULL,
            phone_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT NOT NULL,
            alert_enabled INTEGER NOT NULL,
            last_device_hash TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS locations (
            user_id TEXT PRIMARY KEY,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            last_updated TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            delivered_status TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


@lru_cache
def init_store() -> None:
    _init_schema()


def upsert_user(
    uid: str,
    phone_number: str,
    phone_hash: str,
    name: str | None,
    device_hash: str,
) -> dict[str, Any]:
    now = _utc_iso()

    init_store()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE uid = ?", (uid,))
    row = cur.fetchone()

    if row:
        existing = dict(row)
        payload = {
            "uid": uid,
            "phone_number": phone_number,
            "phone_hash": phone_hash,
            "name": (name or existing.get("name") or ""),
            "created_at": existing.get("created_at") or now,
            "last_login": now,
            "alert_enabled": int(existing.get("alert_enabled", 1)),
            "last_device_hash": device_hash,
        }
        cur.execute(
            """
            UPDATE users
            SET phone_number=?, phone_hash=?, name=?, last_login=?, last_device_hash=?
            WHERE uid=?
            """,
            (
                payload["phone_number"],
                payload["phone_hash"],
                payload["name"],
                payload["last_login"],
                payload["last_device_hash"],
                uid,
            ),
        )
        conn.commit()
        conn.close()
        return payload

    payload = {
        "uid": uid,
        "phone_number": phone_number,
        "phone_hash": phone_hash,
        "name": name or "",
        "created_at": now,
        "last_login": now,
        "alert_enabled": 1,
        "last_device_hash": device_hash,
    }
    cur.execute(
        """
        INSERT INTO users(uid, phone_number, phone_hash, name, created_at, last_login, alert_enabled, last_device_hash)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            payload["uid"],
            payload["phone_number"],
            payload["phone_hash"],
            payload["name"],
            payload["created_at"],
            payload["last_login"],
            payload["alert_enabled"],
            payload["last_device_hash"],
        ),
    )
    conn.commit()
    conn.close()
    return payload


def get_user(uid: str) -> dict[str, Any] | None:
    init_store()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE uid = ?", (uid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def set_alert_subscription(uid: str, enabled: bool) -> None:
    init_store()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET alert_enabled=?, last_login=? WHERE uid=?",
        (1 if enabled else 0, _utc_iso(), uid),
    )
    conn.commit()
    conn.close()


def store_location(uid: str, latitude: float, longitude: float) -> None:
    init_store()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM locations WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE locations SET latitude=?, longitude=?, last_updated=? WHERE user_id=?",
            (latitude, longitude, _utc_iso(), uid),
        )
    else:
        cur.execute(
            "INSERT INTO locations(user_id, latitude, longitude, last_updated) VALUES(?,?,?,?)",
            (uid, latitude, longitude, _utc_iso()),
        )
    conn.commit()
    conn.close()


def create_alert(user_id: str, risk_level: str, message: str, delivered_status: str) -> None:
    init_store()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO alerts(user_id, risk_level, message, timestamp, delivered_status) VALUES(?,?,?,?,?)",
        (user_id, risk_level, message, _utc_iso(), delivered_status),
    )
    conn.commit()
    conn.close()


def list_alerts(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    init_store()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, risk_level, message, timestamp, delivered_status FROM alerts WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
