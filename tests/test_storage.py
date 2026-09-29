import json
import tempfile
import unittest
from pathlib import Path

from app.contracts import (
    AnalysisReport,
    EvidenceItem,
    FixtureCandidate,
    MatchQuery,
    QuantitativeReport,
    ResearchBundle,
    ResolvedFixture,
    SourceResult,
    SourceStatus,
)
from app.storage import Store


def make_bundle_and_report():
    query = MatchQuery("Arsenal", "Chelsea", "2026-10-03T12:00:00Z")
    fixture = ResolvedFixture(
        fixture_id=991,
        home_team="Arsenal",
        away_team="Chelsea",
        kickoff_utc="2026-10-03T12:00:00Z",
        competition="Premier League",
        country="England",
    )
    evidence = EvidenceItem(
        title="Official team update",
        url="https://club.test/news/1",
        publisher="Club",
        published_at="2026-10-03T08:00:00Z",
        fetched_at="2026-10-03T09:00:00Z",
        summary="An official update.",
    )
    status = SourceStatus(
        source="official-news",
        status="ok",
        fetched_at="2026-10-03T09:00:00Z",
        fresh_until="2026-10-03T09:30:00Z",
        request_url="https://club.test/news",
    )
    bundle = ResearchBundle(
        query=query,
        fixture=fixture,
        source_results={"news": SourceResult(value=[evidence], status=status)},
        evidence=(evidence,),
        created_at="2026-10-03T09:00:00Z",
        completeness=0.8,
    )
    quantitative = QuantitativeReport(
        result_probabilities={"home": 0.45, "draw": 0.30, "away": 0.25}
    )
    report = AnalysisReport(
        fixture=fixture,
        quantitative=quantitative,
        action="NO_BET_UNVALIDATED",
        evidence=(evidence,),
        data_completeness=0.8,
    )
    return bundle, report, status


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.db"
        self.store = Store.connect(f"sqlite:///{self.database_path}")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_cache_expires_at_boundary_and_returns_copied_json(self):
        value = {"id": 7, "nested": ["original"]}
        self.store.put_cache(
            "fixture:a", value, expires_at="2026-09-29T01:00:00Z"
        )
        value["nested"].append("mutated")

        hit = self.store.get_cache("fixture:a", now="2026-09-29T00:59:00Z")
        self.assertEqual(hit, {"id": 7, "nested": ["original"]})
        self.assertIsNone(
            self.store.get_cache("fixture:a", now="2026-09-29T01:00:00Z")
        )

    def test_analysis_is_idempotent_and_preserves_original_payload(self):
        bundle, report, _ = make_bundle_and_report()

        first = self.store.save_analysis(bundle, report)
        second = self.store.save_analysis(bundle, report)

        self.assertEqual(first, second)
        saved = self.store.get_analysis(first)
        self.assertEqual(saved["analysis_id"], first)
        self.assertEqual(saved["report"]["action"], "NO_BET_UNVALIDATED")
        self.assertEqual(len(self.store.list_evidence(first)), 1)
        self.assertEqual(self.store.list_analysis_ids().count(first), 1)

    def test_cache_and_source_health_survive_reopening_database(self):
        _, _, status = make_bundle_and_report()
        self.store.put_cache(
            "fixture:persistent", {"id": 42}, "2026-09-29T02:00:00Z"
        )
        self.store.record_source_status(status)
        self.store.close()

        self.store = Store.connect(f"sqlite:///{self.database_path}")
        self.assertEqual(
            self.store.get_cache(
                "fixture:persistent", now="2026-09-29T01:00:00Z"
            ),
            {"id": 42},
        )
        health = self.store.get_source_status("official-news")
        self.assertEqual(health["status"], "ok")
        self.assertNotIn("api_key", json.dumps(health))


if __name__ == "__main__":
    unittest.main()
