"""Read-only Neon connectivity check; never prints credentials."""

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from database.connection import CONNECT_TIMEOUT_SECONDS, engine


def _run_queries(label: str, candidate_engine, attempts: int) -> bool:
    try:
        for attempt in range(1, attempts + 1):
            with candidate_engine.connect() as connection:
                assert connection.execute(text("SELECT 1")).scalar_one() == 1
                database, schema = connection.execute(
                    text("SELECT current_database(), current_schema()")
                ).one()
                user_count = connection.execute(
                    text("SELECT COUNT(*) FROM users")
                ).scalar_one()
            print(
                f"{label} connection {attempt}: PASS "
                f"(database={database}, schema={schema}, users={user_count})"
            )
        print(f"{label}: PASS")
        return True
    except Exception as exc:
        print(f"{label}: FAIL ({type(exc).__name__}: {exc})")
        return False


def main() -> None:
    print(
        f"DB host: {engine.url.host}\n"
        f"DB name: {engine.url.database}\n"
        f"Pooler: {bool(engine.url.host and '-pooler' in engine.url.host)}"
    )

    pooled_ok = _run_queries("POOLER", engine, attempts=5)

    pooled_host = engine.url.host or ""
    if "-pooler" not in pooled_host:
        print("UNPOOLED: FAIL (the configured host is not a Neon pooler hostname)")
        raise SystemExit(1)

    unpooled_url = engine.url.set(host=pooled_host.replace("-pooler", "", 1))
    unpooled_engine = create_engine(
        unpooled_url,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
        poolclass=NullPool,
    )
    try:
        unpooled_ok = _run_queries("UNPOOLED", unpooled_engine, attempts=1)
    finally:
        unpooled_engine.dispose()

    if not pooled_ok or not unpooled_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
