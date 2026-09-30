import tempfile
import unittest
from pathlib import Path

from app.collector_schedule import due_checkpoints
from app.contracts import ResolvedFixture
from app.storage import Store


class CollectorScheduleTests(unittest.TestCase):
    def test_due_windows_match_the_fifteen_minute_schedule(self):
        self.assertEqual(
            due_checkpoints(
                kickoff="2026-10-03T20:00:00Z",
                now="2026-10-02T20:02:00Z",
            ),
            [1440],
        )
        self.assertEqual(
            due_checkpoints(
                kickoff="2026-10-03T20:00:00Z",
                now="2026-10-02T20:20:00Z",
            ),
            [],
        )

    def test_collection_claim_is_unique_and_failed_job_retries_after_fifteen_minutes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store.connect(f"sqlite:///{Path(directory) / 'jobs.db'}")
            try:
                self.assertTrue(
                    store.claim_collection_job(991, 1440, "2026-10-02T20:02:00Z")
                )
                self.assertFalse(
                    store.claim_collection_job(991, 1440, "2026-10-02T20:03:00Z")
                )
                store.finish_collection_job(
                    991,
                    1440,
                    completed_at="2026-10-02T20:04:00Z",
                    error_code="SOURCE_TIMEOUT",
                )
                self.assertFalse(
                    store.claim_collection_job(991, 1440, "2026-10-02T20:14:00Z")
                )
                self.assertTrue(
                    store.claim_collection_job(991, 1440, "2026-10-02T20:20:00Z")
                )
            finally:
                store.close()

    def test_tracking_a_fixture_is_idempotent_and_keeps_provider_ids(self):
        fixture = ResolvedFixture(
            fixture_id=991,
            home_team="Arsenal",
            away_team="Chelsea",
            kickoff_utc="2026-10-03T20:00:00Z",
            competition="Premier League",
            home_team_id=42,
            away_team_id=49,
            league_id=39,
            season=2026,
        )
        with tempfile.TemporaryDirectory() as directory:
            store = Store.connect(f"sqlite:///{Path(directory) / 'fixtures.db'}")
            try:
                store.track_fixture(fixture)
                store.track_fixture(fixture)
                tracked = store.list_tracked_fixtures(
                    now="2026-10-01T00:00:00Z", horizon_hours=96
                )
            finally:
                store.close()

        self.assertEqual(len(tracked), 1)
        self.assertEqual(tracked[0]["fixture_id"], 991)
        self.assertEqual(tracked[0]["league_id"], 39)


if __name__ == "__main__":
    unittest.main()
