"""Five-state helpers copied from model/v8/ahv8/model.py."""

from __future__ import annotations

import numpy as np

from .settlement import settle_home_profit


def settlement_class(goal_diff: int, home_line: float) -> int:
    """Map a home result to full loss, half loss, push, half win, or full win."""
    profit = settle_home_profit(goal_diff, home_line, 2.0)
    if profit <= -0.75:
        return 0
    if profit < -1e-9:
        return 1
    if abs(profit) <= 1e-9:
        return 2
    if profit < 0.75:
        return 3
    return 4


def expected_side_values(
    state_probabilities: np.ndarray,
    home_odds: np.ndarray,
    away_odds: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    p = np.asarray(state_probabilities, dtype=float)
    home_odds = np.asarray(home_odds, dtype=float)
    away_odds = np.asarray(away_odds, dtype=float)
    home = (
        -p[:, 0]
        - 0.5 * p[:, 1]
        + 0.5 * (home_odds - 1) * p[:, 3]
        + (home_odds - 1) * p[:, 4]
    )
    away = (
        (away_odds - 1) * p[:, 0]
        + 0.5 * (away_odds - 1) * p[:, 1]
        - 0.5 * p[:, 3]
        - p[:, 4]
    )
    return home, away

