from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.contracts import EvidenceItem, ResolvedFixture, SourceResult, TeamContext
from app.sources.api_football import API_BASE_URL, ApiFootballClient, ApiFootballError
from app.storage import Store


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class TeamContextClient:
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

    def fetch(self, fixture: ResolvedFixture) -> SourceResult[TeamContext | None]:
        fetched = self._now().astimezone(timezone.utc)
        required = (fixture.home_team_id, fixture.away_team_id, fixture.league_id, fixture.season)
        if any(value is None for value in required):
            return SourceResult(
                value=None, status="missing", source="api-football-context",
                fetched_at=_iso(fetched), request_url=f"{API_BASE_URL}/fixtures",
                error_code="FIXTURE_IDENTIFIERS_MISSING"
            )
        cache_key = f"api-football:context:{fixture.fixture_id}"
        if self._store:
            cached = self._store.get_cache(cache_key, _iso(fetched))
            if cached:
                return self.parse(cached["payloads"], fixture, fetched_at=_to_datetime(cached["fetched_at"]))
        calls = {
            "standings": ("/standings", {"league": str(fixture.league_id), "season": str(fixture.season)}),
            "home_recent": ("/fixtures", {"team": str(fixture.home_team_id), "last": "5"}),
            "away_recent": ("/fixtures", {"team": str(fixture.away_team_id), "last": "5"}),
            "injuries": ("/injuries", {"fixture": str(fixture.fixture_id)}),
            "lineups": ("/fixtures/lineups", {"fixture": str(fixture.fixture_id)}),
        }
        payloads: dict[str, Any] = {}
        failed: list[str] = []
        for name, (path, params) in calls.items():
            try:
                payloads[name] = self._api.get_json(path, params=params)
            except ApiFootballError:
                payloads[name] = {"response": []}
                failed.append(name)
        if len(failed) == len(calls):
            return SourceResult(
                value=None, status="error", source="api-football-context",
                fetched_at=_iso(fetched), request_url=f"{API_BASE_URL}/fixtures",
                error_code="TEAM_CONTEXT_ALL_SOURCES_FAILED"
            )
        if self._store:
            self._store.put_cache(
                cache_key, {"payloads": payloads, "fetched_at": _iso(fetched)},
                _iso(fetched + timedelta(hours=3))
            )
        result = self.parse(payloads, fixture, fetched_at=fetched)
        if failed:
            return SourceResult(
                value=result.value, status="stale", source=result.source,
                fetched_at=result.fetched_at, fresh_until=result.fresh_until,
                request_url=result.request_url,
                error_code="PARTIAL_CONTEXT:" + ",".join(sorted(failed))
            )
        return result

    def parse(
        self, payloads: dict[str, Any], fixture: ResolvedFixture, *, fetched_at: datetime | None = None
    ) -> SourceResult[TeamContext]:
        fetched = (fetched_at or self._now()).astimezone(timezone.utc)
        ranks: dict[int, int] = {}
        for response in payloads.get("standings", {}).get("response", []):
            for group in response.get("league", {}).get("standings", []):
                for row in group:
                    try:
                        ranks[int(row["team"]["id"])] = int(row["rank"])
                    except (KeyError, TypeError, ValueError):
                        continue

        home_injuries: list[EvidenceItem] = []
        away_injuries: list[EvidenceItem] = []
        for injury in payloads.get("injuries", {}).get("response", []):
            try:
                team_id = int(injury["team"]["id"])
                player = str(injury["player"]["name"])
                reason = str(injury["player"].get("reason") or "未说明")
            except (KeyError, TypeError, ValueError):
                continue
            item = EvidenceItem(
                title=f"{player}: {reason}",
                url=f"{API_BASE_URL}/injuries?fixture={fixture.fixture_id}",
                publisher="API-Football",
                published_at=_iso(fetched),
                fetched_at=_iso(fetched),
                summary=f"API-Football 在抓取时列出的伤停：{player}（{reason}）",
                category="injury",
            )
            if team_id == fixture.home_team_id:
                home_injuries.append(item)
            elif team_id == fixture.away_team_id:
                away_injuries.append(item)

        lineup_ids = {
            int(item["team"]["id"])
            for item in payloads.get("lineups", {}).get("response", [])
            if item.get("team", {}).get("id") is not None
        }
        context = TeamContext(
            home_form=self._form(payloads.get("home_recent", {}), fixture.home_team_id),
            away_form=self._form(payloads.get("away_recent", {}), fixture.away_team_id),
            home_rank=ranks.get(fixture.home_team_id),
            away_rank=ranks.get(fixture.away_team_id),
            home_injuries=tuple(home_injuries),
            away_injuries=tuple(away_injuries),
            confirmed_lineups={fixture.home_team_id, fixture.away_team_id}.issubset(lineup_ids),
        )
        return SourceResult(
            value=context, status="ok", source="api-football-context",
            fetched_at=_iso(fetched), fresh_until=_iso(fetched + timedelta(hours=3)),
            request_url=f"{API_BASE_URL}/fixtures?id={fixture.fixture_id}"
        )

    @staticmethod
    def _form(payload: dict[str, Any], team_id: int | None) -> tuple[str, ...]:
        results: list[str] = []
        for match in payload.get("response", []):
            try:
                is_home = int(match["teams"]["home"]["id"]) == team_id
                own = int(match["goals"]["home"] if is_home else match["goals"]["away"])
                other = int(match["goals"]["away"] if is_home else match["goals"]["home"])
            except (KeyError, TypeError, ValueError):
                continue
            results.append("W" if own > other else "L" if own < other else "D")
        return tuple(results)


def _to_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)

