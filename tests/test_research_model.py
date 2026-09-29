import tempfile
import unittest
from pathlib import Path

from app.ahv8.settlement import settle_home_profit
from app.contracts import (
    AmbiguousFixture,
    MatchQuery,
    OddsSnapshot,
    ResearchBundle,
    ResolvedFixture,
    SourceResult,
    TeamContext,
    WeatherEvidence,
)
from app.model_bridge import ModelBridge
from app.research import ResearchService
from app.storage import Store


QUERY = MatchQuery("Arsenal", "Chelsea", "2026-10-03T12:00:00Z")
FIXTURE = ResolvedFixture(
    fixture_id=991,
    home_team="Arsenal",
    away_team="Chelsea",
    kickoff_utc="2026-10-03T12:00:00Z",
    competition="Premier League",
    country="England",
    home_team_id=42,
    away_team_id=49,
    league_id=39,
    season=2026,
)


def source_result(name, value, status="ok", error_code=None):
    return SourceResult(
        value=value,
        status=status,
        source=name,
        fetched_at="2026-10-03T09:00:00Z",
        fresh_until="2026-10-03T10:00:00Z",
        request_url=f"https://source.test/{name}",
        error_code=error_code,
    )


class StaticResolver:
    def resolve(self, query):
        return FIXTURE


class StaticSource:
    def __init__(self, result):
        self.result = result

    def fetch(self, fixture):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def service_with_odds(odds):
    temp_dir = tempfile.TemporaryDirectory()
    store = Store.connect(f"sqlite:///{Path(temp_dir.name) / 'research.db'}")
    service = ResearchService(
        resolver=StaticResolver(),
        weather=StaticSource(
            source_result(
                "weather",
                WeatherEvidence(12.0, 0.0, 10.0, 70.0, "2026-10-03T12:00:00Z"),
            )
        ),
        news=StaticSource(source_result("news", [])),
        team_context=StaticSource(
            source_result(
                "team_context",
                TeamContext(
                    home_form=("W", "W", "D", "L", "W"),
                    away_form=("L", "D", "W", "L", "D"),
                    home_rank=3,
                    away_rank=9,
                ),
            )
        ),
        odds=StaticSource(odds),
        model=ModelBridge(),
        store=store,
        now=lambda: "2026-10-03T09:00:00Z",
    )
    return temp_dir, store, service


class ModelBridgeTests(unittest.TestCase):
    def test_quarter_line_settlement_is_exact(self):
        self.assertEqual(settle_home_profit(0, -0.25, 2.0), -0.5)
        self.assertAlmostEqual(settle_home_profit(1, -0.75, 1.9), 0.45)

    def test_context_probabilities_are_normalized_without_live_odds(self):
        bundle = ResearchBundle(
            query=QUERY,
            fixture=FIXTURE,
            source_results={
                "team_context": source_result(
                    "team_context",
                    TeamContext(
                        home_form=("W", "W", "D", "L", "W"),
                        away_form=("L", "D", "W", "L", "D"),
                        home_rank=3,
                        away_rank=9,
                    ),
                ),
                "odds": source_result(
                    "odds", [], status="missing", error_code="ASIAN_ODDS_NOT_AVAILABLE"
                ),
            },
            created_at="2026-10-03T09:00:00Z",
        )

        report = ModelBridge().predict(bundle)

        self.assertAlmostEqual(sum(report.result_probabilities.values()), 1.0, places=8)
        self.assertIsNone(report.asian_ev)
        self.assertEqual(report.asian_state_probabilities, {})
        self.assertFalse(report.validated_for_betting)
        self.assertEqual(report.probability_basis, "contextual_poisson_research_proxy")


class ResearchServiceTests(unittest.TestCase):
    def test_three_fields_produce_report_and_explicit_missing_odds(self):
        odds = source_result(
            "odds", [], status="missing", error_code="ASIAN_ODDS_NOT_AVAILABLE"
        )
        temp_dir, store, service = service_with_odds(odds)
        self.addCleanup(temp_dir.cleanup)
        self.addCleanup(store.close)

        report = service.analyze(QUERY)

        self.assertEqual(report.fixture.home_team, "Arsenal")
        self.assertTrue(report.quantitative.result_probabilities)
        self.assertIsNone(report.quantitative.asian_ev)
        self.assertIn("odds", report.missing_sources)
        self.assertEqual(report.action, "NO_BET_NO_LIVE_ODDS")
        self.assertIsNotNone(report.analysis_id)
        self.assertIsNotNone(store.get_analysis(report.analysis_id))

    def test_unvalidated_v8_never_returns_bet_now(self):
        odds = source_result(
            "odds",
            [
                OddsSnapshot(
                    "Book A", "Asian Handicap", -0.5, 2.02, 1.88,
                    "2026-10-03T09:00:00Z", "https://odds.test/a"
                ),
                OddsSnapshot(
                    "Book B", "Asian Handicap", -0.5, 2.00, 1.90,
                    "2026-10-03T09:00:00Z", "https://odds.test/b"
                ),
            ],
        )
        temp_dir, store, service = service_with_odds(odds)
        self.addCleanup(temp_dir.cleanup)
        self.addCleanup(store.close)

        report = service.analyze(QUERY)

        self.assertEqual(report.action, "NO_BET_UNVALIDATED")
        self.assertFalse(report.quantitative.validated_for_betting)
        self.assertEqual(set(report.quantitative.asian_state_probabilities), {
            "full_loss", "half_loss", "push", "half_win", "full_win"
        })

    def test_one_source_crash_does_not_discard_other_results(self):
        odds = source_result(
            "odds", [], status="missing", error_code="ASIAN_ODDS_NOT_AVAILABLE"
        )
        temp_dir, store, service = service_with_odds(odds)
        self.addCleanup(temp_dir.cleanup)
        self.addCleanup(store.close)
        service.news = StaticSource(RuntimeError("provider down"))

        report = service.analyze(QUERY)

        self.assertIn("news", report.missing_sources)
        self.assertGreater(report.quantitative.result_probabilities["home"], 0)
        health = store.get_source_status("news")
        self.assertEqual(health["status"], "error")


if __name__ == "__main__":
    unittest.main()
