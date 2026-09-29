from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from app.ahv8.model import expected_side_values, settlement_class
from app.contracts import (
    OddsSnapshot,
    QuantitativeReport,
    ResearchBundle,
    TeamContext,
)


STATE_NAMES = ("full_loss", "half_loss", "push", "half_win", "full_win")


def _form_strength(form: tuple[str, ...]) -> float:
    values = {"W": 1.0, "D": 0.0, "L": -1.0}
    known = [values[item] for item in form if item in values]
    return sum(known) / len(known) if known else 0.0


def _poisson_probability(goals: int, expected_goals: float) -> float:
    return math.exp(-expected_goals) * expected_goals**goals / math.factorial(goals)


class ModelBridge:
    """Transparent research proxy around v8 settlement rules.

    The score-rate layer is deliberately labelled as an unvalidated contextual proxy;
    it must not be represented as the fitted five-state model passing validation.
    """

    def predict(self, bundle: ResearchBundle) -> QuantitativeReport:
        context = self._team_context(bundle)
        home_rate, away_rate = self._expected_goals(context)
        score_grid = self._score_grid(home_rate, away_rate)
        home = sum(prob for (h, a), prob in score_grid.items() if h > a)
        draw = sum(prob for (h, a), prob in score_grid.items() if h == a)
        away = sum(prob for (h, a), prob in score_grid.items() if h < a)
        result_probabilities = {"home": home, "draw": draw, "away": away}

        current_market = self._current_market(bundle.odds)
        if current_market is None:
            return QuantitativeReport(result_probabilities=result_probabilities)

        line, snapshots = current_market
        states = [0.0] * 5
        for (home_goals, away_goals), probability in score_grid.items():
            states[settlement_class(home_goals - away_goals, line)] += probability
        best_home = max(item.home_price for item in snapshots if item.home_price)
        best_away = max(item.away_price for item in snapshots if item.away_price)
        home_values, away_values = expected_side_values(
            np.asarray([states]), np.asarray([best_home]), np.asarray([best_away])
        )
        home_ev = float(home_values[0])
        away_ev = float(away_values[0])
        direction = "home" if home_ev >= away_ev else "away"
        return QuantitativeReport(
            result_probabilities=result_probabilities,
            asian_state_probabilities=dict(zip(STATE_NAMES, states)),
            asian_ev=max(home_ev, away_ev),
            asian_line=line,
            home_ev=home_ev,
            away_ev=away_ev,
            relative_direction=direction,
            validated_for_betting=False,
        )

    @staticmethod
    def _team_context(bundle: ResearchBundle) -> TeamContext:
        result = bundle.source_results.get("team_context")
        if result and isinstance(result.value, TeamContext):
            return result.value
        return TeamContext()

    @staticmethod
    def _expected_goals(context: TeamContext) -> tuple[float, float]:
        form_delta = _form_strength(context.home_form) - _form_strength(context.away_form)
        rank_delta = 0.0
        if context.home_rank and context.away_rank:
            rank_delta = max(-20.0, min(20.0, context.away_rank - context.home_rank)) / 20.0
        strength = max(-0.8, min(0.8, 0.25 * form_delta + 0.30 * rank_delta))
        return 1.45 * math.exp(strength / 2), 1.20 * math.exp(-strength / 2)

    @staticmethod
    def _score_grid(home_rate: float, away_rate: float) -> dict[tuple[int, int], float]:
        grid = {
            (home, away): _poisson_probability(home, home_rate)
            * _poisson_probability(away, away_rate)
            for home in range(11)
            for away in range(11)
        }
        total = sum(grid.values())
        return {score: probability / total for score, probability in grid.items()}

    @staticmethod
    def _current_market(
        odds: tuple[OddsSnapshot, ...]
    ) -> tuple[float, list[OddsSnapshot]] | None:
        usable = [
            item
            for item in odds
            if item.line is not None
            and item.home_price is not None
            and item.away_price is not None
            and item.home_price > 1
            and item.away_price > 1
        ]
        if not usable:
            return None
        latest_time = max(item.captured_at for item in usable)
        latest = [item for item in usable if item.captured_at == latest_time]
        by_line: dict[float, list[OddsSnapshot]] = defaultdict(list)
        for item in latest:
            by_line[float(item.line)].append(item)
        line, snapshots = max(
            by_line.items(),
            key=lambda pair: (len({item.bookmaker for item in pair[1]}), -abs(pair[0])),
        )
        if len({item.bookmaker for item in snapshots}) < 2:
            return None
        return line, snapshots

