"""Automatic football research and forecasting service."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from flask import Flask

from app.ai_client import AilindoClient
from app.config import Settings
from app.model_bridge import ModelBridge
from app.research import ResearchService
from app.resolver import FixtureResolver
from app.routes import register_routes
from app.sources.api_football import ApiFootballClient
from app.sources.news import NewsClient
from app.sources.odds import OddsClient
from app.sources.team_context import TeamContextClient
from app.sources.weather import WeatherClient
from app.storage import Store


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def create_app(
    *,
    service: Any | None = None,
    store: Store | None = None,
    ai_client: Any | None = None,
    settings: Settings | None = None,
    testing: bool = False,
) -> Flask:
    app = Flask(__name__)
    app.config.update(TESTING=testing, JSON_AS_ASCII=False)

    if service is None:
        settings = settings or Settings.from_env(os.environ)
        if not settings.api_football_key:
            raise ValueError("缺少必需环境变量 API_FOOTBALL_KEY")
        store = store or Store.connect(settings.database_url)
        fixture_client = ApiFootballClient(
            settings.api_football_key,
            store=store,
            timeout_seconds=settings.http_timeout_seconds,
        )
        service = ResearchService(
            resolver=FixtureResolver(fixture_client),
            weather=WeatherClient(
                store=store, timeout_seconds=settings.http_timeout_seconds
            ),
            news=NewsClient(store=store, timeout_seconds=settings.http_timeout_seconds),
            team_context=TeamContextClient(
                settings.api_football_key,
                store=store,
                timeout_seconds=settings.http_timeout_seconds,
            ),
            odds=OddsClient(
                settings.api_football_key,
                store=store,
                timeout_seconds=settings.http_timeout_seconds,
            ),
            model=ModelBridge(),
            store=store,
            now=_now_iso,
        )
        if ai_client is None:
            ai_client = AilindoClient(
                settings.ai_base_url,
                settings.ai_api_key,
                settings.ai_model,
                timeout_seconds=settings.ai_timeout_seconds,
            )

    if store is None:
        store = getattr(service, "store", None)
    if store is None:
        raise ValueError("Store is required")

    app.extensions["research_service"] = service
    app.extensions["research_store"] = store
    app.extensions["ailindo_client"] = ai_client
    register_routes(app)
    return app


__all__ = ["create_app"]

