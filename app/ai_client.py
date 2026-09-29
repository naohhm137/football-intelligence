from __future__ import annotations

import json
from typing import Any

import requests

from app.contracts import AiExplanation, AiHealth, AnalysisReport


class AilindoClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str | None,
        *,
        transport: Any | None = None,
        timeout_seconds: float = 45.0,
    ):
        if not base_url.strip():
            raise ValueError("AILINDO_BASE_URL 未配置")
        if not api_key.strip():
            raise ValueError("AILINDO_API_KEY 未配置")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._configured_model = model.strip() if model and model.strip() else None
        self._resolved_model = self._configured_model
        self._transport = transport or requests.Session()
        self._timeout_seconds = timeout_seconds

    def __repr__(self) -> str:
        return (
            "AilindoClient("
            f"base_url={self._base_url!r}, "
            f"api_key_configured={bool(self._api_key)}, "
            f"model={self._configured_model!r})"
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def verify_model(self) -> AiHealth:
        try:
            response = self._transport.get(
                f"{self._base_url}/models",
                headers=self._headers(),
                timeout=self._timeout_seconds,
            )
            if response.status_code >= 400:
                return AiHealth(
                    False,
                    self._configured_model,
                    error_code=f"MODELS_HTTP_{response.status_code}",
                )
            payload = response.json()
            models = tuple(
                str(item["id"])
                for item in payload.get("data", [])
                if isinstance(item, dict) and item.get("id")
            )
        except (requests.RequestException, TypeError, ValueError, KeyError):
            return AiHealth(
                False, self._configured_model, error_code="MODELS_REQUEST_FAILED"
            )

        selected = self._configured_model
        if selected:
            if models and selected not in models:
                return AiHealth(
                    False,
                    selected,
                    discovered_models=models,
                    error_code="CONFIGURED_MODEL_NOT_FOUND",
                )
        elif len(models) == 1:
            selected = models[0]
        else:
            return AiHealth(
                False,
                None,
                discovered_models=models,
                error_code="MODEL_SELECTION_REQUIRED",
            )

        try:
            chat_response = self._transport.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json={
                    "model": selected,
                    "messages": [{"role": "user", "content": "仅回复 ok"}],
                    "temperature": 0,
                    "max_tokens": 8,
                },
                timeout=self._timeout_seconds,
            )
            if chat_response.status_code >= 400:
                return AiHealth(
                    False,
                    selected,
                    discovered_models=models,
                    error_code=f"CHAT_HTTP_{chat_response.status_code}",
                )
            chat_payload = chat_response.json()
            if not chat_payload.get("choices"):
                return AiHealth(
                    False,
                    selected,
                    discovered_models=models,
                    error_code="CHAT_INVALID_RESPONSE",
                )
        except (requests.RequestException, TypeError, ValueError, KeyError):
            return AiHealth(
                False,
                selected,
                discovered_models=models,
                error_code="CHAT_REQUEST_FAILED",
            )

        self._resolved_model = selected
        return AiHealth(True, selected, discovered_models=models)

    def explain(self, report: AnalysisReport) -> AiExplanation:
        model = self._resolved_model
        if not model:
            health = self.verify_model()
            if not health.available or not health.configured_model:
                return AiExplanation(
                    summary="AI模型尚未完成配置，量化结果不受影响。",
                    risk_notes=(health.error_code or "AI_MODEL_UNAVAILABLE",),
                    trusted_json=False,
                )
            model = health.configured_model

        allowed_urls = {item.url for item in report.evidence}
        user_payload = {
            "analysis_id": report.analysis_id,
            "fixture": {
                "home_team": report.fixture.home_team,
                "away_team": report.fixture.away_team,
                "kickoff_utc": report.fixture.kickoff_utc,
                "competition": report.fixture.competition,
            },
            "quantitative": {
                "result_probabilities": dict(report.quantitative.result_probabilities),
                "asian_state_probabilities": dict(
                    report.quantitative.asian_state_probabilities
                ),
                "asian_ev": report.quantitative.asian_ev,
                "asian_line": report.quantitative.asian_line,
                "relative_direction": report.quantitative.relative_direction,
                "probability_basis": report.quantitative.probability_basis,
                "validated_for_betting": report.quantitative.validated_for_betting,
            },
            "action": report.action,
            "data_completeness": report.data_completeness,
            "missing_sources": list(report.missing_sources),
            "evidence": [
                {
                    "title": item.title,
                    "url": item.url,
                    "publisher": item.publisher,
                    "published_at": item.published_at,
                    "summary": item.summary,
                    "category": item.category,
                }
                for item in report.evidence
            ],
        }
        system_prompt = (
            "你是足球赛前研究报告编辑。只能使用用户消息中已保存的证据；"
            "禁止补充未提供的事实，禁止猜测伤停、首发、天气、赔率或投注量。"
            "每个事实性判断必须引用 evidence 中的原始 URL。"
            "不得改变数值概率，不得绕过 NO_BET_UNVALIDATED 或其他 NO_BET 状态。"
            "只输出JSON对象，字段必须是 summary、supporting_factors、"
            "opposing_factors、risk_notes、citations。"
        )
        try:
            response = self._transport.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(
                                user_payload, ensure_ascii=False, sort_keys=True
                            ),
                        },
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
                timeout=self._timeout_seconds,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"AI_HTTP_{response.status_code}")
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("AI_INVALID_CONTENT")
        except (requests.RequestException, RuntimeError, TypeError, ValueError, KeyError, IndexError):
            return AiExplanation(
                summary="AI解释暂时不可用，量化结果和来源仍然有效。",
                risk_notes=("AI_REQUEST_FAILED",),
                trusted_json=False,
            )

        try:
            document = json.loads(content)
            summary = str(document["summary"])
            supporting = self._string_tuple(document["supporting_factors"])
            opposing = self._string_tuple(document["opposing_factors"])
            risks = self._string_tuple(document["risk_notes"])
            citations = self._string_tuple(document["citations"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return AiExplanation(summary=content, citations=(), trusted_json=False)

        if any(url not in allowed_urls for url in citations):
            return AiExplanation(
                summary="AI解释引用了未保存的来源，已拒绝展示该结论。",
                risk_notes=("AI_CITATION_REJECTED",),
                citations=(),
                trusted_json=False,
            )
        return AiExplanation(
            summary=summary,
            supporting_factors=supporting,
            opposing_factors=opposing,
            risk_notes=risks,
            citations=citations,
            trusted_json=True,
        )

    @staticmethod
    def _string_tuple(value: Any) -> tuple[str, ...]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("AI field must be a string list")
        return tuple(value)
