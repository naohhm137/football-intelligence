from __future__ import annotations

import dataclasses
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from app.contracts import (
    AmbiguousFixture,
    AnalysisReport,
    MatchQuery,
    MissingFixture,
    ResearchBundle,
    ResolvedFixture,
    SourceResult,
    TeamContext,
)
from app.model_bridge import ModelBridge
from app.storage import Store


class FixtureResolutionError(RuntimeError):
    def __init__(self, code: str, result: AmbiguousFixture | MissingFixture):
        super().__init__(code)
        self.code = code
        self.result = result


class ResearchService:
    def __init__(
        self,
        *,
        resolver: Any,
        weather: Any,
        news: Any,
        team_context: Any,
        odds: Any,
        model: ModelBridge,
        store: Store,
        now: Callable[[], str],
    ):
        self.resolver = resolver
        self.weather = weather
        self.news = news
        self.team_context = team_context
        self.odds = odds
        self.model = model
        self.store = store
        self.now = now

    def analyze(self, query: MatchQuery) -> AnalysisReport:
        fixture = self.resolver.resolve(query)
        if isinstance(fixture, AmbiguousFixture):
            raise FixtureResolutionError("AMBIGUOUS_FIXTURE", fixture)
        if isinstance(fixture, MissingFixture):
            raise FixtureResolutionError("FIXTURE_NOT_FOUND", fixture)
        if not isinstance(fixture, ResolvedFixture):
            raise RuntimeError("INVALID_FIXTURE_RESOLUTION")

        clients = {
            "weather": self.weather,
            "news": self.news,
            "team_context": self.team_context,
            "odds": self.odds,
        }
        results: dict[str, SourceResult[Any]] = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(client.fetch, fixture): name
                for name, client in clients.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()
                    if not isinstance(result, SourceResult):
                        raise TypeError("source returned invalid result")
                except Exception:
                    result = SourceResult(
                        value=[] if name in {"news", "odds"} else None,
                        status="error",
                        source=name,
                        fetched_at=self.now(),
                        error_code="SOURCE_EXCEPTION",
                    )
                results[name] = result
                self.store.record_source_status(result.to_status())

        evidence = []
        news_value = results["news"].value
        if isinstance(news_value, list):
            evidence.extend(news_value)
        context = results["team_context"].value
        if isinstance(context, TeamContext):
            evidence.extend(context.home_injuries)
            evidence.extend(context.away_injuries)
        odds_value = results["odds"].value
        odds = tuple(odds_value) if isinstance(odds_value, list) else ()
        completeness, missing = self._completeness(results)
        bundle = ResearchBundle(
            query=query,
            fixture=fixture,
            source_results=results,
            evidence=tuple(evidence),
            odds=odds,
            created_at=self.now(),
            completeness=completeness,
        )
        quantitative = self.model.predict(bundle)
        if not odds:
            action = "NO_BET_NO_LIVE_ODDS"
        elif quantitative.asian_ev is None:
            action = "NO_BET_INSUFFICIENT_MARKET"
        else:
            action = "NO_BET_UNVALIDATED"
        report = AnalysisReport(
            fixture=fixture,
            quantitative=quantitative,
            action=action,
            missing_sources=tuple(missing),
            evidence=tuple(evidence),
            odds=odds,
            data_completeness=completeness,
        )
        analysis_id = self.store.save_analysis(bundle, report)
        return dataclasses.replace(report, analysis_id=analysis_id)

    @staticmethod
    def _completeness(
        results: dict[str, SourceResult[Any]]
    ) -> tuple[float, list[str]]:
        checks = {
            "weather": lambda value: value is not None,
            "news": lambda value: isinstance(value, list) and bool(value),
            "team_context": lambda value: isinstance(value, TeamContext)
            and bool(value.home_form or value.away_form or value.home_rank or value.away_rank),
            "odds": lambda value: isinstance(value, list) and len(value) >= 2,
        }
        weights = {"weather": 0.15, "news": 0.15, "team_context": 0.40, "odds": 0.30}
        score = 0.0
        missing: list[str] = []
        for name, check in checks.items():
            result = results.get(name)
            available = bool(result and result.status in {"ok", "stale"} and check(result.value))
            if available:
                score += weights[name] * (0.5 if result.status == "stale" else 1.0)
            else:
                missing.append(name)
        return round(score, 4), missing
