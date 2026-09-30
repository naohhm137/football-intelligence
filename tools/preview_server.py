"""Run the interface against deterministic evidence for local visual review."""

from __future__ import annotations

import dataclasses
import atexit
import tempfile
from pathlib import Path

from app import create_app
from app.contracts import (
    AiExplanation,
    AnalysisReport,
    EvidenceItem,
    OddsSnapshot,
    QuantitativeReport,
    ResearchBundle,
    ResolvedFixture,
    SourceStatus,
)
from app.storage import Store


class PreviewService:
    def __init__(self, store: Store):
        self.store = store

    def analyze(self, query):
        fixture = ResolvedFixture(
                fixture_id=991,
                home_team=query.home_team,
                away_team=query.away_team,
                kickoff_utc=query.kickoff_utc,
                competition="Premier League",
                venue="North London",
            )
        evidence = (
            EvidenceItem(
                title="Official team update",
                url="https://example.com/team-update",
                publisher="Official club source",
                published_at="2026-10-03T08:00:00Z",
                fetched_at="2026-10-03T09:00:00Z",
                summary="Preview evidence",
            ),
        )
        odds = (
            OddsSnapshot("Company A", "Asian Handicap", -0.25, 1.94, 1.92, "2026-10-03T08:00:00Z", "https://example.com/a"),
            OddsSnapshot("Company B", "Asian Handicap", -0.25, 1.91, 1.95, "2026-10-03T08:00:00Z", "https://example.com/b"),
            OddsSnapshot("Company A", "Asian Handicap", -0.50, 2.02, 1.84, "2026-10-03T10:00:00Z", "https://example.com/a"),
        )
        report = AnalysisReport(
            fixture=fixture,
            quantitative=QuantitativeReport(
                result_probabilities={"home": 0.49, "draw": 0.28, "away": 0.23},
                asian_state_probabilities={
                    "full_loss": 0.22,
                    "half_loss": 0.08,
                    "push": 0.18,
                    "half_win": 0.12,
                    "full_win": 0.40,
                },
                asian_ev=0.037,
                asian_line=-0.25,
                relative_direction="home",
            ),
            action="NO_BET_UNVALIDATED",
            missing_sources=("weather",),
            evidence=evidence,
            odds=odds,
            source_statuses=(
                {"source": "weather", "status": "missing", "last_success_at": "2026-10-02T12:00:00Z"},
            ),
            data_completeness=0.85,
        )
        bundle = ResearchBundle(
            query=query,
            fixture=fixture,
            source_results={},
            evidence=evidence,
            odds=odds,
            created_at="2026-10-03T10:00:00Z",
            completeness=0.85,
        )
        analysis_id = self.store.save_analysis(bundle, report)
        return dataclasses.replace(report, analysis_id=analysis_id)


class PreviewAi:
    def explain(self, report):
        return AiExplanation(
            summary="主队近期状态略占优势，但样本仍不足以形成可执行投注建议。",
            supporting_factors=("主队近期表现更稳定", "多家公司盘口方向一致"),
            opposing_factors=("客队反击效率存在不确定性",),
            risk_notes=("模型尚未通过300场严格前瞻验证",),
            citations=("https://example.com/team-update",),
        )


def create_preview_app():
    temp_dir = tempfile.TemporaryDirectory()
    store = Store.connect(f"sqlite:///{Path(temp_dir.name) / 'preview.db'}")
    app = create_app(
        service=PreviewService(store), store=store, ai_client=PreviewAi(), testing=True
    )
    app.extensions["preview_temp_dir"] = temp_dir
    atexit.register(temp_dir.cleanup)
    atexit.register(store.close)
    return app


if __name__ == "__main__":
    app = create_preview_app()
    app.run(host="127.0.0.1", port=8765)
