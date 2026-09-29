from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import requests

from app.contracts import FixtureCandidate, MatchQuery
from app.storage import Store


API_BASE_URL = "https://v3.football.api-sports.io"


class ApiFootballError(RuntimeError):
    """A safe provider error that never embeds credentials or response bodies."""


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _parse_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("API-Football fixture time lacks timezone")
    return parsed.astimezone(timezone.utc)


class ApiFootballClient:
    def __init__(
        self,
        api_key: str,
        *,
        store: Store | None = None,
        transport: Any | None = None,
        timeout_seconds: float = 12.0,
        now: Callable[[], datetime] | None = None,
    ):
        if not api_key:
            raise ValueError("API_FOOTBALL_KEY 未配置")
        self._api_key = api_key
        self._store = store
        self._transport = transport or requests.Session()
        self._timeout_seconds = timeout_seconds
        self._now = now or (lambda: datetime.now(timezone.utc))

    def find_fixtures(self, query: MatchQuery) -> list[FixtureCandidate]:
        kickoff = _parse_datetime(query.kickoff_utc)
        first_day = (kickoff - timedelta(days=1)).date().isoformat()
        last_day = (kickoff + timedelta(days=1)).date().isoformat()
        cache_key = f"api-football:fixtures:{first_day}:{last_day}:UTC"
        now = self._now().astimezone(timezone.utc)

        if self._store is not None:
            cached = self._store.get_cache(cache_key, now=_utc_iso(now))
            if cached is not None:
                return self.parse_fixtures(cached)

        payload = self._request_json(
            "/fixtures",
            params={"from": first_day, "to": last_day, "timezone": "UTC"},
        )
        if self._store is not None:
            self._store.put_cache(
                cache_key,
                payload,
                expires_at=_utc_iso(now + timedelta(hours=6)),
            )
        return self.parse_fixtures(payload)

    def _request_json(self, path: str, *, params: dict[str, str]) -> dict[str, Any]:
        url = f"{API_BASE_URL}{path}"
        headers = {"x-apisports-key": self._api_key, "Accept": "application/json"}
        last_error: Exception | None = None

        for attempt in range(2):
            try:
                response = self._transport.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                if attempt == 0:
                    continue
                raise ApiFootballError("API_FOOTBALL_CONNECTION_FAILED") from None
            except requests.RequestException as exc:
                raise ApiFootballError("API_FOOTBALL_REQUEST_FAILED") from exc

            if 500 <= response.status_code <= 599 and attempt == 0:
                continue
            if response.status_code >= 400:
                raise ApiFootballError(f"API_FOOTBALL_HTTP_{response.status_code}")

            try:
                payload = response.json()
            except (TypeError, ValueError) as exc:
                raise ApiFootballError("API_FOOTBALL_INVALID_JSON") from exc
            if not isinstance(payload, dict):
                raise ApiFootballError("API_FOOTBALL_INVALID_SCHEMA")
            if payload.get("errors"):
                raise ApiFootballError("API_FOOTBALL_PROVIDER_ERROR")
            return payload

        raise ApiFootballError("API_FOOTBALL_CONNECTION_FAILED") from last_error

    def get_json(self, path: str, *, params: dict[str, str]) -> dict[str, Any]:
        return self._request_json(path, params=params)

    @staticmethod
    def parse_fixtures(payload: dict[str, Any]) -> list[FixtureCandidate]:
        response = payload.get("response")
        if not isinstance(response, list):
            raise ApiFootballError("API_FOOTBALL_INVALID_SCHEMA")

        candidates: list[FixtureCandidate] = []
        for item in response:
            try:
                fixture = item["fixture"]
                league = item["league"]
                teams = item["teams"]
                venue_data = fixture.get("venue") or {}
                venue_parts = [
                    str(value).strip()
                    for value in (venue_data.get("name"), venue_data.get("city"))
                    if value and str(value).strip()
                ]
                candidates.append(
                    FixtureCandidate(
                        fixture_id=int(fixture["id"]),
                        home_team=str(teams["home"]["name"]).strip(),
                        away_team=str(teams["away"]["name"]).strip(),
                        kickoff_utc=_utc_iso(_parse_datetime(str(fixture["date"]))),
                        competition=str(league["name"]).strip(),
                        country=(str(league.get("country")).strip() if league.get("country") else None),
                        venue=", ".join(venue_parts) or None,
                        source_url=f"{API_BASE_URL}/fixtures?id={int(fixture['id'])}",
                        home_team_id=int(teams["home"]["id"]),
                        away_team_id=int(teams["away"]["id"]),
                        league_id=int(league["id"]),
                        season=int(league["season"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ApiFootballError("API_FOOTBALL_INVALID_FIXTURE") from exc
        return candidates

