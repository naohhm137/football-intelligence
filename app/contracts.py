from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, Literal, Mapping, TypeVar


SourceState = Literal["ok", "stale", "missing", "error"]
T = TypeVar("T")


def _parse_offset_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("开赛时间不能为空")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("开赛时间必须是有效的 ISO 8601 时间") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("开赛时间必须包含时区偏移")
    return parsed


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True)
class MatchQuery:
    home_team: str
    away_team: str
    kickoff_utc: str

    @classmethod
    def from_json(cls, payload: Mapping[str, object]) -> "MatchQuery":
        allowed = {"home_team", "away_team", "kickoff_local"}
        unknown = set(payload) - allowed
        missing = allowed - set(payload)
        if unknown:
            raise ValueError(f"不支持的字段: {', '.join(sorted(unknown))}")
        if missing:
            raise ValueError(f"缺少字段: {', '.join(sorted(missing))}")

        home = str(payload["home_team"]).strip()
        away = str(payload["away_team"]).strip()
        if not home or not away:
            raise ValueError("主队和客队不能为空")
        if home.casefold() == away.casefold():
            raise ValueError("主队和客队不能相同")

        kickoff = _parse_offset_timestamp(payload["kickoff_local"])
        return cls(home_team=home, away_team=away, kickoff_utc=_utc_iso(kickoff))


@dataclass(frozen=True)
class EvidenceItem:
    title: str
    url: str
    publisher: str
    published_at: str
    fetched_at: str
    summary: str
    category: str = "news"


@dataclass(frozen=True)
class SourceStatus:
    source: str
    status: SourceState
    fetched_at: str
    fresh_until: str | None = None
    request_url: str | None = None
    error_code: str | None = None
    quota_remaining: int | None = None


@dataclass(frozen=True)
class SourceResult(Generic[T]):
    value: T
    status: SourceStatus


@dataclass(frozen=True)
class FixtureCandidate:
    fixture_id: int
    home_team: str
    away_team: str
    kickoff_utc: str
    competition: str
    country: str | None = None
    venue: str | None = None
    venue_latitude: float | None = None
    venue_longitude: float | None = None
    source_url: str | None = None
    match_score: float = 0.0


@dataclass(frozen=True)
class ResolvedFixture(FixtureCandidate):
    pass


@dataclass(frozen=True)
class AmbiguousFixture:
    query: MatchQuery
    candidates: tuple[FixtureCandidate, ...]


@dataclass(frozen=True)
class MissingFixture:
    query: MatchQuery
    reason: str = "FIXTURE_NOT_FOUND"


@dataclass(frozen=True)
class WeatherEvidence:
    temperature_c: float | None
    precipitation_mm: float | None
    wind_kph: float | None
    humidity_percent: float | None
    forecast_for: str


@dataclass(frozen=True)
class TeamContext:
    home_form: tuple[str, ...] = ()
    away_form: tuple[str, ...] = ()
    home_rank: int | None = None
    away_rank: int | None = None
    home_injuries: tuple[EvidenceItem, ...] = ()
    away_injuries: tuple[EvidenceItem, ...] = ()
    confirmed_lineups: bool = False


@dataclass(frozen=True)
class OddsSnapshot:
    bookmaker: str
    market: str
    line: float | None
    home_price: float | None
    away_price: float | None
    captured_at: str
    source_url: str


@dataclass(frozen=True)
class ResearchBundle:
    query: MatchQuery
    fixture: ResolvedFixture
    source_results: Mapping[str, SourceResult[Any]]
    evidence: tuple[EvidenceItem, ...] = ()
    odds: tuple[OddsSnapshot, ...] = ()
    created_at: str = ""
    completeness: float = 0.0


@dataclass(frozen=True)
class QuantitativeReport:
    result_probabilities: Mapping[str, float]
    asian_state_probabilities: Mapping[str, float] = field(default_factory=dict)
    asian_ev: float | None = None
    relative_direction: str | None = None
    model_version: str = "v8"
    validated_for_betting: bool = False


@dataclass(frozen=True)
class AnalysisReport:
    fixture: ResolvedFixture
    quantitative: QuantitativeReport
    action: str
    missing_sources: tuple[str, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    data_completeness: float = 0.0
    analysis_id: str | None = None


@dataclass(frozen=True)
class AiHealth:
    available: bool
    configured_model: str
    discovered_models: tuple[str, ...] = ()
    error_code: str | None = None


@dataclass(frozen=True)
class AiExplanation:
    summary: str
    supporting_factors: tuple[str, ...] = ()
    opposing_factors: tuple[str, ...] = ()
    risk_notes: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()
    trusted_json: bool = True

