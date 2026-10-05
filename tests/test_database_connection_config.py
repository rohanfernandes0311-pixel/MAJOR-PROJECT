import unittest

from database.connection import CONNECT_TIMEOUT_SECONDS, engine


class DatabaseConnectionConfigTests(unittest.TestCase):
    def test_neon_engine_has_safe_connection_lifecycle_settings(self) -> None:
        self.assertEqual(engine.url.drivername, "postgresql+psycopg")
        self.assertEqual(engine.url.query.get("sslmode"), "require")
        self.assertEqual(engine.url.query.get("channel_binding"), "require")
        self.assertIn("-pooler", engine.url.host or "")

        self.assertTrue(engine.pool._pre_ping)
        self.assertEqual(engine.pool._recycle, 300)
        self.assertEqual(engine.pool.size(), 5)
        self.assertEqual(engine.pool._max_overflow, 10)
        self.assertEqual(CONNECT_TIMEOUT_SECONDS, 10)


if __name__ == "__main__":
    unittest.main()
