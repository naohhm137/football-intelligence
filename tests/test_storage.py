import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
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
        source_results={
            "news": SourceResult(
                value=[evidence],
                status="ok",
                source=status.source,
                fetched_at=status.fetched_at,
                fresh_until=status.fresh_until,
                request_url=status.request_url,
            )
        },
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


class _FakeCursor:
    def __init__(self):
        self.fetchone_calls = 0
        self.closed = False

    def execute(self, _sql, _parameters=()):
        return self

    def fetchone(self):
        self.fetchone_calls += 1
        return (1,)

    def close(self):
        self.closed = True


class _FakePostgresConnection:
    def __init__(self, *, closed):
        self.closed = closed
        self.cursor_calls = 0
        self.cursor_instance = _FakeCursor()

    def cursor(self):
        self.cursor_calls += 1
        if self.closed:
            raise RuntimeError("closed connection must not be used")
        return self.cursor_instance


class _LockSensitivePostgresConnection:
    def __init__(self):
        self.closed = False
        self.pending_statement = False
        self.commit_calls = 0

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return False

    def execute(self, _sql, _parameters=()):
        if self.pending_statement:
            raise RuntimeError("statement timeout waiting for an unreleased DDL lock")
        self.pending_statement = True
        return self

    def commit(self):
        self.commit_calls += 1
        self.pending_statement = False


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

    def test_parallel_source_workers_can_share_the_store(self):
        def write(index):
            self.store.put_cache(
                f"parallel:{index}",
                {"index": index},
                "2026-09-29T02:00:00Z",
            )

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(write, range(12)))

        self.assertEqual(
            self.store.get_cache("parallel:11", now="2026-09-29T01:00:00Z"),
            {"index": 11},
        )

    def test_source_failure_preserves_last_successful_fetch_time(self):
        _, _, healthy = make_bundle_and_report()
        self.store.record_source_status(healthy)
        self.store.record_source_status(
            SourceStatus(
                source=healthy.source,
                status="error",
                fetched_at="2026-10-03T10:00:00Z",
                error_code="SOURCE_TIMEOUT",
            )
        )

        status = self.store.get_source_status(healthy.source)
        self.assertEqual(status["status"], "error")
        self.assertEqual(status["last_success_at"], "2026-10-03T09:00:00Z")

    def test_postgres_store_reconnects_before_querying_a_closed_connection(self):
        closed_connection = _FakePostgresConnection(closed=True)
        replacement = _FakePostgresConnection(closed=False)
        reconnect_calls = []
        store = Store(
            closed_connection,
            "postgres",
            reconnect=lambda: reconnect_calls.append(True) or replacement,
        )

        self.assertEqual(store.health(), {"status": "ok", "dialect": "postgres"})
        self.assertEqual(reconnect_calls, [True])
        self.assertEqual(closed_connection.cursor_calls, 0)
        self.assertEqual(replacement.cursor_calls, 1)
        self.assertTrue(replacement.cursor_instance.closed)

    def test_postgres_schema_setup_releases_each_ddl_lock_before_continuing(self):
        connection = _LockSensitivePostgresConnection()
        store = Store(connection, "postgres")

        store._initialize_schema()

        self.assertGreater(connection.commit_calls, 1)
        self.assertFalse(connection.pending_statement)


if __name__ == "__main__":
    unittest.main()
