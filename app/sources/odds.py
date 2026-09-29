from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.contracts import OddsSnapshot, ResolvedFixture, SourceResult
from app.sources.api_football import API_BASE_URL, ApiFootballClient, ApiFootballError
from app.storage import Store


ASIAN_VALUE = re.compile(r"^(Home|Away)\s+([+-]?\d+(?:\.\d+)?)$", re.IGNORECASE)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _time(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class OddsClient:
    def __init__(
        self,
        api_key: str,
        *,
        store: Store | None = None,
        transport: Any | None = None,
        timeout_seconds: float = 12.0,
        now: Callable[[], datetime] | None = None,
    ):
        self._store = store
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._api = ApiFootballClient(
            api_key, transport=transport, timeout_seconds=timeout_seconds, now=self._now
        )

    def fetch(self, fixture: ResolvedFixture) -> SourceResult[list[OddsSnapshot]]:
        fetched = self._now().astimezone(timezone.utc)
        until_kickoff = (_time(fixture.kickoff_utc) - fetched).total_seconds()
        ttl_minutes = 5 if 0 <= until_kickoff <= 90 * 60 else 15
        cache_key = f"api-football:odds:{fixture.fixture_id}:asian"
        if self._store:
            cached = self._store.get_cache(cache_key, _iso(fetched))
            if cached:
                return self.parse(cached["payload"], fixture, fetched_at=_time(cached["fetched_at"]))
        try:
            payload = self._api.get_json("/odds", params={"fixture": str(fixture.fixture_id)})
        except ApiFootballError as exc:
            return SourceResult(
                value=[], status="error", source="api-football-odds",
                fetched_at=_iso(fetched), request_url=f"{API_BASE_URL}/odds",
                error_code=str(exc)
            )
        if self._store:
            self._store.put_cache(
                cache_key, {"payload": payload, "fetched_at": _iso(fetched)},
                _iso(fetched + timedelta(minutes=ttl_minutes))
            )
        return self.parse(payload, fixture, fetched_at=fetched, ttl_minutes=ttl_minutes)

    def parse(
        self,
        payload: dict[str, Any],
        fixture: ResolvedFixture,
        *,
        fetched_at: datetime | None = None,
        ttl_minutes: int = 15,
    ) -> SourceResult[list[OddsSnapshot]]:
        fetched = (fetched_at or self._now()).astimezone(timezone.utc)
        snapshots: list[OddsSnapshot] = []
        for response in payload.get("response", []) if isinstance(payload, dict) else []:
            captured_at = response.get("update") or _iso(fetched)
            try:
                captured_at = _iso(_time(str(captured_at)))
            except ValueError:
                captured_at = _iso(fetched)
            for bookmaker in response.get("bookmakers", []):
                name = str(bookmaker.get("name") or "Unknown")
                for bet in bookmaker.get("bets", []):
                    if str(bet.get("name") or "").casefold() != "asian handicap":
                        continue
                    homes: dict[float, float] = {}
                    aways: dict[float, float] = {}
                    for value in bet.get("values", []):
                        match = ASIAN_VALUE.match(str(value.get("value") or "").strip())
                        if not match:
                            continue
                        try:
                            line = float(match.group(2))
                            price = float(value["odd"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        if match.group(1).casefold() == "home":
                            homes[line] = price
                        else:
                            aways[-line] = price
                    for line in sorted(set(homes) & set(aways)):
                        snapshots.append(
                            OddsSnapshot(
                                bookmaker=name,
                                market="Asian Handicap",
                                line=line,
                                home_price=homes[line],
                                away_price=aways[line],
                                captured_at=captured_at,
                                source_url=f"{API_BASE_URL}/odds?fixture={fixture.fixture_id}",
                            )
                        )
        return SourceResult(
            value=snapshots,
            status="ok" if snapshots else "missing",
            source="api-football-odds",
            fetched_at=_iso(fetched),
            fresh_until=_iso(fetched + timedelta(minutes=ttl_minutes)),
            request_url=f"{API_BASE_URL}/odds?fixture={fixture.fixture_id}",
            error_code=None if snapshots else "ASIAN_ODDS_NOT_AVAILABLE",
        )
