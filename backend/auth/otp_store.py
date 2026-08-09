from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "auth_store.db"
OTP_PEPPER = os.getenv("OTP_HASH_PEPPER", os.getenv("JWT_SECRET", "change-this-in-production"))


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_schema() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS otp_sessions (
            session_id TEXT PRIMARY KEY,
            phone_number TEXT NOT NULL,
            phone_hash TEXT NOT NULL,
            otp_hash TEXT NOT NULL,
            otp_salt TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            verified INTEGER NOT NULL DEFAULT 0,
            revoked INTEGER NOT NULL DEFAULT 0,
            resend_count INTEGER NOT NULL DEFAULT 0,
            expires_at TEXT NOT NULL,
            resend_after_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_sent_at TEXT NOT NULL,
            last_ip TEXT,
            last_user_agent TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id TEXT PRIMARY KEY,
            phone_number TEXT NOT NULL,
            phone_hash TEXT NOT NULL,
            token_jti TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            last_seen_at TEXT NOT NULL,
            last_ip TEXT,
            last_user_agent TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS login_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            phone_hash TEXT NOT NULL,
            session_id TEXT NOT NULL,
            status TEXT NOT NULL,
            login_time TEXT NOT NULL,
            ip TEXT,
            user_agent TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def init_store() -> None:
    _init_schema()


def hash_phone(phone_number: str) -> str:
    data = f"{OTP_PEPPER}:{phone_number.strip()}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_otp(otp: str, otp_salt: str, phone_hash: str) -> str:
    digest = hmac.new(
        OTP_PEPPER.encode("utf-8"),
        f"{phone_hash}:{otp_salt}:{otp.strip()}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def create_otp_session(
    *,
    phone_number: str,
    otp_hash: str,
    otp_salt: str,
    expires_at: str,
    resend_after_at: str,
    last_ip: str,
    last_user_agent: str,
) -> dict[str, Any]:
    init_store()
    now = _utc_iso()
    session_id = str(uuid.uuid4())
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE otp_sessions
        SET revoked=1, updated_at=?
        WHERE phone_number=? AND verified=0 AND revoked=0
        """,
        (now, phone_number),
    )
    phone_hash = hash_phone(phone_number)
    cur.execute(
        """
        INSERT INTO otp_sessions(
            session_id, phone_number, phone_hash, otp_hash, otp_salt, attempts, verified,
            revoked, resend_count, expires_at, resend_after_at, created_at, updated_at,
            last_sent_at, last_ip, last_user_agent
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            session_id,
            phone_number,
            phone_hash,
            otp_hash,
            otp_salt,
            0,
            0,
            0,
            0,
            expires_at,
            resend_after_at,
            now,
            now,
            now,
            last_ip,
            last_user_agent,
        ),
    )
    conn.commit()
    conn.close()
    return get_otp_session(session_id=session_id) or {}


def get_active_otp_session(phone_number: str) -> dict[str, Any] | None:
    init_store()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM otp_sessions
        WHERE phone_number=? AND verified=0 AND revoked=0
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (phone_number,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_otp_session(*, session_id: str) -> dict[str, Any] | None:
    init_store()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM otp_sessions WHERE session_id=?", (session_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def increment_otp_attempts(session_id: str) -> dict[str, Any] | None:
    init_store()
    now = _utc_iso()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE otp_sessions SET attempts=attempts+1, updated_at=? WHERE session_id=?",
        (now, session_id),
    )
    conn.commit()
    conn.close()
    return get_otp_session(session_id=session_id)


def mark_otp_verified(session_id: str) -> dict[str, Any] | None:
    init_store()
    now = _utc_iso()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE otp_sessions SET verified=1, updated_at=? WHERE session_id=?",
        (now, session_id),
    )
    conn.commit()
    conn.close()
    return get_otp_session(session_id=session_id)


def revoke_otp_session(session_id: str) -> None:
    init_store()
    now = _utc_iso()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE otp_sessions SET revoked=1, updated_at=? WHERE session_id=?", (now, session_id))
    conn.commit()
    conn.close()


def delete_otp_session(session_id: str) -> None:
    init_store()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM otp_sessions WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()


def create_user_session(
    *,
    session_id: str,
    phone_number: str,
    token_jti: str,
    issued_at: str,
    expires_at: str,
    last_ip: str,
    last_user_agent: str,
) -> dict[str, Any]:
    init_store()
    phone_hash = hash_phone(phone_number)
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_sessions(
            session_id, phone_number, phone_hash, token_jti, issued_at, expires_at, revoked_at,
            last_seen_at, last_ip, last_user_agent
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (
            session_id,
            phone_number,
            phone_hash,
            token_jti,
            issued_at,
            expires_at,
            None,
            issued_at,
            last_ip,
            last_user_agent,
        ),
    )
    conn.commit()
    conn.close()
    return get_user_session_by_jti(token_jti)


def get_user_session_by_jti(token_jti: str) -> dict[str, Any] | None:
    init_store()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_sessions WHERE token_jti=?", (token_jti,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def revoke_user_session(token_jti: str) -> bool:
    init_store()
    now = _utc_iso()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE user_sessions SET revoked_at=?, last_seen_at=? WHERE token_jti=? AND revoked_at IS NULL",
        (now, now, token_jti),
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


def is_user_session_active(token_jti: str) -> bool:
    session = get_user_session_by_jti(token_jti)
    return bool(session) and not session.get("revoked_at")


def log_login_history(
    *,
    phone_number: str,
    session_id: str,
    status: str,
    ip: str,
    user_agent: str,
) -> None:
    init_store()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO login_history(phone_number, phone_hash, session_id, status, login_time, ip, user_agent)
        VALUES(?,?,?,?,?,?,?)
        """,
        (phone_number, hash_phone(phone_number), session_id, status, _utc_iso(), ip, user_agent),
    )
    conn.commit()
    conn.close()
