import unittest

from scripts.smoke_test import run_smoke


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.posted = None

    def get(self, url, timeout):
        if url.endswith("/api/health"):
            return FakeResponse(200, {"status": "ok", "database": {"status": "ok"}})
        return FakeResponse(200, {"analysis_id": "analysis-1", "report": {"action": "NO_BET_UNVALIDATED"}})

    def post(self, url, json, timeout):
        self.posted = json
        return FakeResponse(200, {"analysis_id": "analysis-1", "action": "NO_BET_UNVALIDATED"})


class SmokeTestTests(unittest.TestCase):
    def test_smoke_posts_exactly_three_fields_and_checks_persistence(self):
        session = FakeSession()

        report = run_smoke("https://app.test", session=session)

        self.assertEqual(
            set(session.posted), {"home_team", "away_team", "kickoff_local"}
        )
        self.assertEqual(report["health"], "ok")
        self.assertEqual(report["analysis"], "NO_BET_UNVALIDATED")
        self.assertEqual(report["persistence"], "ok")


if __name__ == "__main__":
    unittest.main()
