from __future__ import annotations

import dataclasses
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Mapping, Protocol

from app.contracts import (
    AmbiguousFixture,
    FixtureCandidate,
    MatchQuery,
    MissingFixture,
    ResolvedFixture,
)


DEFAULT_ALIASES = {
    "man united": "manchester united",
    "man utd": "manchester united",
    "man city": "manchester city",
    "psg": "paris saint germain",
    "inter": "inter milan",
    "bayern": "bayern munich",
}


class FixtureSource(Protocol):
    def find_fixtures(self, query: MatchQuery) -> list[FixtureCandidate]: ...


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text.casefold()))


def _parse_utc(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("fixture time lacks timezone")
    return parsed.astimezone(timezone.utc)


class FixtureResolver:
    def __init__(
        self,
        source: FixtureSource,
        aliases: Mapping[str, str] | None = None,
        *,
        minimum_score: float = 0.90,
        maximum_kickoff_delta_hours: float = 18.0,
    ):
        self._source = source
        merged = dict(DEFAULT_ALIASES)
        if aliases:
            merged.update({_normalize(key): _normalize(value) for key, value in aliases.items()})
        self._aliases = merged
        self._minimum_score = minimum_score
        self._maximum_delta_seconds = maximum_kickoff_delta_hours * 3600

    def resolve(
        self, query: MatchQuery
    ) -> ResolvedFixture | AmbiguousFixture | MissingFixture:
        query_time = _parse_utc(query.kickoff_utc)
        matches: list[FixtureCandidate] = []

        for candidate in self._source.find_fixtures(query):
            delta = abs((_parse_utc(candidate.kickoff_utc) - query_time).total_seconds())
            if delta > self._maximum_delta_seconds:
                continue
            home_score = self._team_score(query.home_team, candidate.home_team)
            away_score = self._team_score(query.away_team, candidate.away_team)
            pair_score = min(home_score, away_score)
            if pair_score >= self._minimum_score:
                matches.append(dataclasses.replace(candidate, match_score=pair_score))

        matches.sort(
            key=lambda item: (
                abs((_parse_utc(item.kickoff_utc) - query_time).total_seconds()),
                item.fixture_id,
            )
        )
        if not matches:
            return MissingFixture(query=query)
        if len(matches) > 1:
            return AmbiguousFixture(query=query, candidates=tuple(matches))
        return ResolvedFixture(**dataclasses.asdict(matches[0]))

    def _team_score(self, query_name: str, candidate_name: str) -> float:
        query = _normalize(query_name)
        candidate = _normalize(candidate_name)
        if query == candidate:
            return 1.0
        if self._aliases.get(query) == candidate:
            return 0.99
        query_tokens = set(query.split())
        candidate_tokens = set(candidate.split())
        if query_tokens and query_tokens < candidate_tokens:
            return 0.92
        return SequenceMatcher(None, query, candidate).ratio()
