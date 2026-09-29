import dataclasses
import unittest

from app.config import Settings
from app.contracts import MatchQuery


class SettingsTests(unittest.TestCase):
    def test_secret_values_are_required_but_never_exposed(self):
        settings = Settings.from_env(
            {
                "AILINDO_BASE_URL": "https://example.test/v1",
                "AILINDO_API_KEY": "secret-value",
                "AILINDO_MODEL": "provider-model",
            }
        )

        self.assertEqual(settings.ai_model, "provider-model")
        self.assertNotIn("secret-value", repr(settings))
        self.assertIn("ai_api_key_configured=True", repr(settings))

    def test_missing_required_ai_setting_is_rejected(self):
        complete = {
            "AILINDO_BASE_URL": "https://example.test/v1",
            "AILINDO_API_KEY": "secret-value",
            "AILINDO_MODEL": "provider-model",
        }

        for missing in complete:
            with self.subTest(missing=missing):
                env = {key: value for key, value in complete.items() if key != missing}
                with self.assertRaisesRegex(ValueError, missing):
                    Settings.from_env(env)

    def test_optional_provider_and_database_values_have_safe_defaults(self):
        settings = Settings.from_env(
            {
                "AILINDO_BASE_URL": "https://example.test/v1/",
                "AILINDO_API_KEY": "secret-value",
                "AILINDO_MODEL": "provider-model",
            }
        )

        self.assertEqual(settings.ai_base_url, "https://example.test/v1")
        self.assertEqual(settings.database_url, "sqlite:///football_ai.sqlite3")
        self.assertIsNone(settings.api_football_key)
        self.assertEqual(settings.http_timeout_seconds, 12.0)


class MatchQueryTests(unittest.TestCase):
    def test_public_query_contains_only_three_user_fields_and_normalizes_utc(self):
        query = MatchQuery.from_json(
            {
                "home_team": " Arsenal ",
                "away_team": "Chelsea",
                "kickoff_local": "2026-10-03T20:00:00+08:00",
            }
        )

        self.assertEqual(query.home_team, "Arsenal")
        self.assertEqual(query.away_team, "Chelsea")
        self.assertEqual(query.kickoff_utc, "2026-10-03T12:00:00Z")
        self.assertTrue(dataclasses.is_dataclass(query))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            query.home_team = "Other"

    def test_unknown_public_field_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "不支持的字段"):
            MatchQuery.from_json(
                {
                    "home_team": "Arsenal",
                    "away_team": "Chelsea",
                    "kickoff_local": "2026-10-03T20:00:00+08:00",
                    "home_odds": 2.0,
                }
            )

    def test_blank_identical_and_offsetless_inputs_are_rejected(self):
        cases = [
            {
                "home_team": " ",
                "away_team": "Chelsea",
                "kickoff_local": "2026-10-03T20:00:00+08:00",
            },
            {
                "home_team": "Arsenal",
                "away_team": " arsenal ",
                "kickoff_local": "2026-10-03T20:00:00+08:00",
            },
            {
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "kickoff_local": "2026-10-03T20:00:00",
            },
        ]

        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    MatchQuery.from_json(payload)


if __name__ == "__main__":
    unittest.main()
