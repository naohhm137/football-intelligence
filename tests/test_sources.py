import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.contracts import ResolvedFixture
from app.sources.news import NewsClient
from app.sources.odds import OddsClient
from app.sources.team_context import TeamContextClient
from app.sources.weather import WeatherClient


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "source_responses"
FETCHED_AT = datetime(2026, 10, 3, 10, 56, tzinfo=timezone.utc)


def load_fixture(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def resolved_fixture(**overrides):
    values = {
        "fixture_id": 991,
        "home_team": "Manchester United",
        "away_team": "Chelsea",
        "kickoff_utc": "2026-10-03T12:30:00Z",
        "competition": "Premier League",
        "country": "England",
        "venue": "Old Trafford, Manchester",
        "venue_latitude": 53.4631,
        "venue_longitude": -2.2913,
        "home_team_id": 33,
        "away_team_id": 49,
        "league_id": 39,
        "season": 2026,
    }
    values.update(overrides)
    return ResolvedFixture(**values)


class NoCallTransport:
    def __init__(self):
        self.calls = []

    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("transport must not be called")


class WeatherTests(unittest.TestCase):
    def test_weather_is_rejected_when_venue_coordinates_are_unknown(self):
        transport = NoCallTransport()
        client = WeatherClient(transport=transport, now=lambda: FETCHED_AT)

        result = client.fetch(
            resolved_fixture(venue_latitude=None, venue_longitude=None)
        )

        self.assertEqual(result.status, "missing")
        self.assertIsNone(result.value)
        self.assertEqual(result.error_code, "VENUE_COORDINATES_MISSING")
        self.assertEqual(transport.calls, [])

    def test_weather_uses_nearest_forecast_hour(self):
        client = WeatherClient(now=lambda: FETCHED_AT)

        result = client.parse(load_fixture("open_meteo.json"), resolved_fixture())

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.value.temperature_c, 13.0)
        self.assertEqual(result.value.wind_kph, 20.1)
        self.assertEqual(result.value.forecast_for, "2026-10-03T13:00:00Z")


class NewsTests(unittest.TestCase):
    def test_news_drops_items_without_url_or_publication_time(self):
        client = NewsClient(now=lambda: FETCHED_AT)

        result = client.parse(load_fixture("gdelt.json"))

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.value), 1)
        self.assertTrue(all(item.url and item.published_at for item in result.value))
        self.assertEqual(result.value[0].publisher, "club.test")


class TeamContextTests(unittest.TestCase):
    def test_context_parses_rank_form_injuries_and_confirmed_lineups(self):
        client = TeamContextClient("provider-key", now=lambda: FETCHED_AT)

        result = client.parse(
            load_fixture("api_football_team_context.json"), resolved_fixture()
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.value.home_rank, 4)
        self.assertEqual(result.value.away_rank, 8)
        self.assertEqual(result.value.home_form, ("W", "D"))
        self.assertEqual(result.value.away_form, ("L", "W"))
        self.assertEqual(len(result.value.home_injuries), 1)
        self.assertTrue(result.value.confirmed_lineups)


class OddsTests(unittest.TestCase):
    def test_odds_absence_is_missing_not_default_price(self):
        client = OddsClient("provider-key", now=lambda: FETCHED_AT)

        result = client.parse({"response": []}, resolved_fixture())

        self.assertEqual(result.status, "missing")
        self.assertEqual(result.value, [])
        self.assertEqual(result.error_code, "ASIAN_ODDS_NOT_AVAILABLE")

    def test_asian_home_and_away_prices_are_paired_by_line(self):
        client = OddsClient("provider-key", now=lambda: FETCHED_AT)

        result = client.parse(load_fixture("api_football_odds.json"), resolved_fixture())

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.value), 1)
        snapshot = result.value[0]
        self.assertEqual(snapshot.bookmaker, "Book One")
        self.assertEqual(snapshot.line, -0.5)
        self.assertEqual(snapshot.home_price, 1.93)
        self.assertEqual(snapshot.away_price, 1.95)


if __name__ == "__main__":
    unittest.main()
