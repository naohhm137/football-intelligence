from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from app.collector_schedule import due_checkpoints
from app.contracts import MatchQuery
from app.model_bridge import ModelBridge
from app.research import ResearchService
from app.resolver import FixtureResolver
from app.sources.api_football import ApiFootballClient
from app.sources.news import NewsClient
from app.sources.odds import OddsClient
from app.sources.team_context import TeamContextClient
from app.sources.weather import WeatherClient
from app.storage import Store


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required configuration: {name}")
    return value


def build_service(store: Store, api_key: str) -> ResearchService:
    fixture_client = ApiFootballClient(api_key, store=store, timeout_seconds=12)
    return ResearchService(
        resolver=FixtureResolver(fixture_client),
        weather=WeatherClient(store=store, timeout_seconds=12),
        news=NewsClient(store=store, timeout_seconds=12),
        team_context=TeamContextClient(api_key, store=store, timeout_seconds=12),
        odds=OddsClient(api_key, store=store, timeout_seconds=12),
        model=ModelBridge(),
        store=store,
        now=now_iso,
    )


def main() -> int:
    store = Store.connect(required_env("DATABASE_URL"))
    service = build_service(store, required_env("API_FOOTBALL_KEY"))
    current = now_iso()
    tracked = store.list_tracked_fixtures(now=current, horizon_hours=96)
    claimed = 0
    completed = 0
    failed = 0
    try:
        for fixture in tracked:
            for checkpoint in due_checkpoints(
                kickoff=fixture["kickoff_utc"], now=current
            ):
                if not store.claim_collection_job(
                    int(fixture["fixture_id"]), checkpoint, current
                ):
                    continue
                claimed += 1
                try:
                    service.analyze(
                        MatchQuery(
                            fixture["home_team"],
                            fixture["away_team"],
                            fixture["kickoff_utc"],
                        )
                    )
                    store.finish_collection_job(
                        int(fixture["fixture_id"]),
                        checkpoint,
                        completed_at=now_iso(),
                    )
                    completed += 1
                except Exception:
                    store.finish_collection_job(
                        int(fixture["fixture_id"]),
                        checkpoint,
                        completed_at=now_iso(),
                        error_code="COLLECTION_FAILED",
                    )
                    failed += 1
    finally:
        store.close()

    print(
        json.dumps(
            {
                "tracked": len(tracked),
                "claimed": claimed,
                "completed": completed,
                "failed": failed,
            },
            separators=(",", ":"),
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
