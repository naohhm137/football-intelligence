from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ValueError(f"缺少必需环境变量 {name}")
    return value


def _positive_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是数字") from exc
    if value <= 0:
        raise ValueError(f"{name} 必须大于 0")
    return value


@dataclass(frozen=True, repr=False)
class Settings:
    ai_base_url: str
    ai_api_key: str
    ai_model: str
    api_football_key: str | None
    database_url: str
    http_timeout_seconds: float
    ai_timeout_seconds: float

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        base_url = _required(env, "AILINDO_BASE_URL").rstrip("/")
        return cls(
            ai_base_url=base_url,
            ai_api_key=_required(env, "AILINDO_API_KEY"),
            ai_model=_required(env, "AILINDO_MODEL"),
            api_football_key=env.get("API_FOOTBALL_KEY", "").strip() or None,
            database_url=(
                env.get("DATABASE_URL", "").strip()
                or "sqlite:///football_ai.sqlite3"
            ),
            http_timeout_seconds=_positive_float(
                env, "HTTP_TIMEOUT_SECONDS", 12.0
            ),
            ai_timeout_seconds=_positive_float(env, "AI_TIMEOUT_SECONDS", 45.0),
        )

    def __repr__(self) -> str:
        return (
            "Settings("
            f"ai_base_url={self.ai_base_url!r}, "
            f"ai_api_key_configured={bool(self.ai_api_key)}, "
            f"ai_model={self.ai_model!r}, "
            f"api_football_key_configured={bool(self.api_football_key)}, "
            f"database_url_configured={bool(self.database_url)}, "
            f"http_timeout_seconds={self.http_timeout_seconds!r}, "
            f"ai_timeout_seconds={self.ai_timeout_seconds!r}"
            ")"
        )

