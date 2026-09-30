import json
import tempfile
import unittest
from pathlib import Path

import yaml

from app import create_app
from app.storage import Store


ROOT = Path(__file__).parents[1]


class EmptyService:
    def __init__(self, store):
        self.store = store


class ProductionConfigTests(unittest.TestCase):
    def test_render_blueprint_declares_secrets_without_values(self):
        blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
        service = blueprint["services"][0]
        env = service["envVars"]

        self.assertEqual(service["healthCheckPath"], "/api/health")
        self.assertIn("gunicorn", service["startCommand"])
        self.assertGreaterEqual(
            {item["key"] for item in env},
            {
                "DATABASE_URL",
                "AILINDO_BASE_URL",
                "AILINDO_API_KEY",
                "AILINDO_MODEL",
                "API_FOOTBALL_KEY",
            },
        )
        for item in env:
            if item["key"].endswith(("KEY", "URL", "MODEL")):
                self.assertNotIn("value", item)
                self.assertFalse(item.get("generateValue", False))

    def test_postgres_migration_is_idempotent_and_uses_jsonb(self):
        sql = (ROOT / "app" / "migrations" / "001_initial.sql").read_text(
            encoding="utf-8"
        ).lower()

        self.assertGreaterEqual(sql.count("create table if not exists"), 7)
        self.assertIn("jsonb", sql)
        self.assertIn("timestamptz", sql)
        self.assertNotIn("drop table", sql)

    def test_health_reports_components_without_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store.connect(f"sqlite:///{Path(directory) / 'health.db'}")
            try:
                app = create_app(
                    service=EmptyService(store), store=store, ai_client=None, testing=True
                )
                payload = app.test_client().get("/api/health").get_json()
            finally:
                store.close()

        self.assertEqual(set(payload), {"status", "version", "database", "ai", "sources"})
        self.assertEqual(payload["database"]["status"], "ok")
        self.assertFalse(payload["ai"]["configured"])
        self.assertNotIn("sk-", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
