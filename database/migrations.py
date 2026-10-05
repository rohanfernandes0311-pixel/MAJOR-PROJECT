import sqlite3
from pathlib import Path

from database.connection import (
    migration_engine,
    MigrationSessionLocal,
)
from database.models import (
    User,
    Location,
    Alert,
    LocationEvent,
    LoginHistory,
    OTPSession,
    AuditEvent,
)
from database.connection import Base


# =========================================================
# SOURCE DATABASES
# =========================================================

SOURCE_DATABASES = {
    "auth": Path("data/auth_store.db"),
    "local": Path("data/local_store.db"),
    "events": Path("data/location_events.db"),
}


# =========================================================
# CREATE TARGET TABLES
# =========================================================

def create_target_tables():
    print("Creating unified database tables...")

    Base.metadata.create_all(
        bind=migration_engine
    )

    print("Target tables created.")


# =========================================================
# READ SQLITE ROWS
# =========================================================

def read_rows(db_path, table_name):
    conn = sqlite3.connect(db_path)

    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        f"SELECT * FROM {table_name}"
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# MIGRATION
# =========================================================

def migrate():

    create_target_tables()

    db = MigrationSessionLocal()

    try:

        # -------------------------------------------------
        # USERS
        # -------------------------------------------------

        print("\nMigrating users...")

        users = read_rows(
            SOURCE_DATABASES["local"],
            "users"
        )

        for row in users:

            db.add(
                User(
                    uid=row["uid"],
                    phone_number=row["phone_number"],
                    phone_hash=row["phone_hash"],
                    name=row["name"],
                    created_at=row["created_at"],
                    last_login=row["last_login"],
                    alert_enabled=row["alert_enabled"],
                    last_device_hash=row["last_device_hash"],
                )
            )

        print(f"Users found: {len(users)}")


        # -------------------------------------------------
        # LOCATIONS
        # -------------------------------------------------

        print("\nMigrating locations...")

        locations = read_rows(
            SOURCE_DATABASES["local"],
            "locations"
        )

        for row in locations:

            db.add(
                Location(
                    user_id=row["user_id"],
                    latitude=row["latitude"],
                    longitude=row["longitude"],
                    last_updated=row["last_updated"],
                )
            )

        print(f"Locations found: {len(locations)}")


        # -------------------------------------------------
        # ALERTS
        # -------------------------------------------------

        print("\nMigrating alerts...")

        alerts = read_rows(
            SOURCE_DATABASES["local"],
            "alerts"
        )

        for row in alerts:

            db.add(
                Alert(
                    id=row["id"],
                    user_id=row["user_id"],
                    risk_level=row["risk_level"],
                    message=row["message"],
                    timestamp=row["timestamp"],
                    delivered_status=row["delivered_status"],
                )
            )

        print(f"Alerts found: {len(alerts)}")


        # -------------------------------------------------
        # LOCATION EVENTS
        # -------------------------------------------------

        print("\nMigrating location events...")

        events = read_rows(
            SOURCE_DATABASES["events"],
            "location_events"
        )

        for row in events:

            db.add(
                LocationEvent(
                    id=row["id"],
                    user_id=row["user_id"],
                    timestamp_utc=row["timestamp_utc"],
                    latitude=row["latitude"],
                    longitude=row["longitude"],
                    rainfall_mm=row["rainfall_mm"],
                    ml_risk=row["ml_risk"],
                    zone_risk=row["zone_risk"],
                    final_risk=row["final_risk"],
                    geofence_event=row["geofence_event"],
                    active_zone_id=row["active_zone_id"],
                )
            )

        print(f"Location events found: {len(events)}")


        # -------------------------------------------------
        # LOGIN HISTORY
        # -------------------------------------------------

        print("\nMigrating login history...")

        login_history = read_rows(
            SOURCE_DATABASES["auth"],
            "login_history"
        )

        for row in login_history:

            db.add(
                LoginHistory(
                    id=row["id"],
                    phone_number=row["phone_number"],
                    phone_hash=row["phone_hash"],
                    session_id=row["session_id"],
                    status=row["status"],
                    login_time=row["login_time"],
                    ip=row["ip"],
                    user_agent=row["user_agent"],
                )
            )

        print(
            f"Login records found: {len(login_history)}"
        )


        # -------------------------------------------------
        # OTP SESSIONS
        # -------------------------------------------------

        print("\nMigrating OTP sessions...")

        otp_sessions = read_rows(
            SOURCE_DATABASES["auth"],
            "otp_sessions"
        )

        for row in otp_sessions:

            db.add(
                OTPSession(
                    session_id=row["session_id"],
                    phone_number=row["phone_number"],
                    phone_hash=row["phone_hash"],
                    otp_hash=row["otp_hash"],
                    otp_salt=row["otp_salt"],
                    attempts=row["attempts"],
                    verified=row["verified"],
                    revoked=row["revoked"],
                    resend_count=row["resend_count"],
                    expires_at=row["expires_at"],
                    resend_after_at=row["resend_after_at"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    last_sent_at=row["last_sent_at"],
                    last_ip=row["last_ip"],
                    last_user_agent=row["last_user_agent"],
                )
            )

        print(
            f"OTP sessions found: {len(otp_sessions)}"
        )


        # -------------------------------------------------
        # COMMIT
        # -------------------------------------------------

        db.commit()

        print("\n========================================")
        print("MIGRATION COMPLETED SUCCESSFULLY")
        print("========================================")


    except Exception:

        db.rollback()

        print("\nMIGRATION FAILED.")
        print("Target database changes were rolled back.")

        raise


    finally:

        db.close()


# =========================================================
# RUN MIGRATION
# =========================================================

if __name__ == "__main__":
    migrate()
