from __future__ import annotations

import dataclasses
from typing import Any

from flask import Flask, jsonify, request

from app.contracts import AiExplanation, AmbiguousFixture, MatchQuery
from app.research import FixtureResolutionError


def _error(code: str, message: str, status: int, **extra: Any):
    payload = {"error": {"code": code, "message": message}, **extra}
    return jsonify(payload), status


def _report_json(report, explanation: AiExplanation | None) -> dict[str, Any]:
    payload = dataclasses.asdict(report)
    payload["ai_explanation"] = (
        dataclasses.asdict(explanation) if explanation is not None else None
    )
    payload["status"] = (
        "SOURCE_DEGRADED" if report.missing_sources else "ANALYSIS_COMPLETE"
    )
    return payload


def register_routes(app: Flask) -> None:
    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.post("/api/analyze")
    def analyze():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _error("INVALID_REQUEST", "请提交JSON格式的比赛信息。", 400)
        try:
            query = MatchQuery.from_json(payload)
        except (TypeError, ValueError) as exc:
            return _error("INVALID_REQUEST", str(exc), 400)

        service = app.extensions["research_service"]
        try:
            report = service.analyze(query)
        except FixtureResolutionError as exc:
            if exc.code == "AMBIGUOUS_FIXTURE" and isinstance(
                exc.result, AmbiguousFixture
            ):
                return _error(
                    "AMBIGUOUS_FIXTURE",
                    "找到多场相似比赛，请从候选中确认一场。",
                    409,
                    candidates=[
                        dataclasses.asdict(candidate)
                        for candidate in exc.result.candidates
                    ],
                )
            return _error(
                "FIXTURE_NOT_FOUND",
                "没有找到与队名和开赛时间匹配的比赛。",
                404,
            )
        except Exception:
            app.logger.exception("analysis failed")
            return _error(
                "ANALYSIS_FAILED",
                "分析暂时失败，请稍后重试；系统没有生成虚假结果。",
                500,
            )

        explanation = None
        ai_client = app.extensions.get("ailindo_client")
        if ai_client is not None:
            try:
                explanation = ai_client.explain(report)
            except Exception:
                explanation = AiExplanation(
                    summary="AI解释暂时不可用，量化结果和来源仍然有效。",
                    risk_notes=("AI_REQUEST_FAILED",),
                    trusted_json=False,
                )
        return jsonify(_report_json(report, explanation))

    @app.get("/api/analysis/<analysis_id>")
    def get_analysis(analysis_id: str):
        saved = app.extensions["research_store"].get_analysis(analysis_id)
        if saved is None:
            return _error("ANALYSIS_NOT_FOUND", "没有找到这份分析记录。", 404)
        return jsonify(saved)

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "model_version": "8.0.0-research",
                "validated_for_betting": False,
                "ai_configured": app.extensions.get("ailindo_client") is not None,
            }
        )

    @app.get("/api/source-health")
    def source_health():
        statuses = app.extensions["research_store"].list_source_statuses()
        return jsonify({"sources": statuses})

