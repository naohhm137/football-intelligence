import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.contracts import AmbiguousFixture, MatchQuery, MissingFixture, ResolvedFixture
from app.resolver import FixtureResolver
from app.sources.api_football import ApiFootballClient, ApiFootballError
from app.storage import Store


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "api_football_fixtures.json"


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, *, params, headers, timeout):
        self.calls.append(
            {"url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class StaticClient:
    def __init__(self, candidates):
        self.candidates = candidates

    def find_fixtures(self, query):
        return list(self.candidates)


class ApiFootballClientTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.store = Store.connect("sqlite:///:memory:")
        self.now = lambda: datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.store.close()

    def test_official_response_is_parsed_and_cached_without_leaking_key(self):
        transport = FakeTransport([FakeResponse(self.payload)])
        client = ApiFootballClient(
            "provider-secret", store=self.store, transport=transport, now=self.now
        )
        query = MatchQuery("Man United", "Chelsea", "2026-10-03T12:30:00Z")

        first = client.find_fixtures(query)
        second = client.find_fixtures(query)

        self.assertEqual([item.fixture_id for item in first], [991, 992, 993])
        self.assertEqual(second, first)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0]["headers"]["x-apisports-key"], "provider-secret")
        self.assertNotIn("provider-secret", transport.calls[0]["url"])
        self.assertEqual(transport.calls[0]["params"]["timezone"], "UTC")
        self.assertEqual(first[0].venue, "Old Trafford, Manchester")

    def test_client_does_not_retry_4xx(self):
        transport = FakeTransport([FakeResponse({"errors": {"token": "bad"}}, 403)])
        client = ApiFootballClient("provider-secret", transport=transport, now=self.now)

        with self.assertRaises(ApiFootballError):
            client.find_fixtures(
                MatchQuery("Arsenal", "Chelsea", "2026-10-03T12:30:00Z")
            )
        self.assertEqual(len(transport.calls), 1)

    def test_client_retries_one_5xx_then_succeeds(self):
        transport = FakeTransport(
            [FakeResponse({}, 503), FakeResponse(self.payload, 200)]
        )
        client = ApiFootballClient("provider-secret", transport=transport, now=self.now)

        result = client.find_fixtures(
            MatchQuery("Arsenal", "Chelsea", "2026-10-03T12:30:00Z")
        )

        self.assertEqual(len(result), 3)
        self.assertEqual(len(transport.calls), 2)


class FixtureResolverTests(unittest.TestCase):
    def setUp(self):
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        parser = ApiFootballClient("unused", transport=FakeTransport([]))
        self.candidates = parser.parse_fixtures(payload)
        self.resolver = FixtureResolver(StaticClient(self.candidates))

    def test_resolver_matches_aliases_and_nearest_kickoff(self):
        result = self.resolver.resolve(
            MatchQuery("Man United", "Chelsea", "2026-10-03T12:30:00Z")
        )

        self.assertIsInstance(result, ResolvedFixture)
        self.assertEqual(result.fixture_id, 991)
        self.assertEqual(result.home_team, "Manchester United")

    def test_ambiguous_short_names_return_candidates_not_a_guess(self):
        result = self.resolver.resolve(
            MatchQuery("United", "City", "2026-10-03T12:30:00Z")
        )

        self.assertIsInstance(result, AmbiguousFixture)
        self.assertEqual([candidate.fixture_id for candidate in result.candidates], [992, 993])

    def test_candidate_outside_eighteen_hours_is_not_selected(self):
        result = self.resolver.resolve(
            MatchQuery("Man United", "Chelsea", "2026-10-04T07:00:01Z")
        )

        self.assertIsInstance(result, MissingFixture)


if __name__ == "__main__":
    unittest.main()
