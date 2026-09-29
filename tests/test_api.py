import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.contracts import (
    AiExplanation,
    AmbiguousFixture,
    AnalysisReport,
    FixtureCandidate,
    MatchQuery,
    QuantitativeReport,
    ResolvedFixture,
)
from app.research import FixtureResolutionError
from app.storage import Store


QUERY_JSON = {
    "home_team": "Arsenal",
    "away_team": "Chelsea",
    "kickoff_local": "2026-10-03T20:00:00+08:00",
}
FIXTURE = ResolvedFixture(
    fixture_id=991,
    home_team="Arsenal",
    away_team="Chelsea",
    kickoff_utc="2026-10-03T12:00:00Z",
    competition="Premier League",
)


class FakeService:
    def __init__(self, store):
        self.store = store
        self.received = []

    def analyze(self, query):
        self.received.append(query)
        report = AnalysisReport(
            fixture=FIXTURE,
            quantitative=QuantitativeReport(
                result_probabilities={"home": 0.48, "draw": 0.29, "away": 0.23}
            ),
            action="NO_BET_NO_LIVE_ODDS",
            missing_sources=("odds",),
            data_completeness=0.55,
            analysis_id="analysis-123",
        )
        return report


class FakeAi:
    def explain(self, report):
        return AiExplanation(
            summary="证据不足，保持观察。",
            risk_notes=("缺少实时亚盘",),
            trusted_json=True,
        )


class AmbiguousService:
    def analyze(self, query):
        candidates = (
            FixtureCandidate(991, "Manchester United", "Manchester City", query.kickoff_utc, "Premier League"),
            FixtureCandidate(992, "Sheffield United", "Leicester City", query.kickoff_utc, "Championship"),
        )
        raise FixtureResolutionError(
            "AMBIGUOUS_FIXTURE", AmbiguousFixture(query=query, candidates=candidates)
        )


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = Store.connect(
            f"sqlite:///{Path(self.temp_dir.name) / 'api.db'}"
        )
        self.service = FakeService(self.store)
        self.app = create_app(
            service=self.service, store=self.store, ai_client=FakeAi(), testing=True
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_analyze_accepts_only_three_user_fields(self):
        response = self.client.post("/api/analyze", json=QUERY_JSON)

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["analysis_id"], "analysis-123")
        self.assertEqual(payload["fixture"]["home_team"], "Arsenal")
        self.assertEqual(payload["ai_explanation"]["summary"], "证据不足，保持观察。")
        self.assertEqual(self.service.received[0].kickoff_utc, "2026-10-03T12:00:00Z")

    def test_manual_odds_field_is_rejected(self):
        response = self.client.post(
            "/api/analyze", json={**QUERY_JSON, "home_odds": 2.0}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "INVALID_REQUEST")
        self.assertEqual(self.service.received, [])

    def test_ambiguous_fixture_returns_candidates_not_server_error(self):
        app = create_app(
            service=AmbiguousService(), store=self.store, ai_client=None, testing=True
        )
        response = app.test_client().post("/api/analyze", json=QUERY_JSON)

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertEqual(payload["error"]["code"], "AMBIGUOUS_FIXTURE")
        self.assertEqual([item["fixture_id"] for item in payload["candidates"]], [991, 992])

    def test_health_and_source_health_do_not_expose_secrets(self):
        response = self.client.get("/api/health")
        sources = self.client.get("/api/source-health")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["validated_for_betting"])
        self.assertEqual(sources.status_code, 200)
        self.assertNotIn("api_key", sources.get_data(as_text=True))

    def test_unknown_analysis_returns_stable_404(self):
        response = self.client.get("/api/analysis/not-found")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["code"], "ANALYSIS_NOT_FOUND")

    def test_root_serves_the_match_search_interface(self):
        with self.client.get("/") as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn('id="match-search"', response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
