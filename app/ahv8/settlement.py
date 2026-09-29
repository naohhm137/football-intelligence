"""Exact Asian-handicap settlement copied from model/v8/ahv8/settlement.py."""

from __future__ import annotations

from math import isclose


def split_line(line: float) -> tuple[float, ...]:
    """Return the component half-lines for an Asian handicap."""
    doubled = line * 2
    if isclose(doubled, round(doubled), abs_tol=1e-9):
        return (float(line),)
    quartered = line * 4
    if not isclose(quartered, round(quartered), abs_tol=1e-9):
        raise ValueError(f"unsupported Asian handicap line: {line}")
    lower = int(quartered // 2) / 2
    return (float(lower), float(lower + 0.5))


def _component_profit(adjusted_margin: float, decimal_odds: float) -> float:
    if adjusted_margin > 1e-9:
        return decimal_odds - 1.0
    if adjusted_margin < -1e-9:
        return -1.0
    return 0.0


def settle_home_profit(
    goal_diff: int, home_line: float, home_decimal_odds: float
) -> float:
    if home_decimal_odds <= 1.0:
        raise ValueError("decimal odds must be greater than 1.0")
    components = split_line(float(home_line))
    stake = 1.0 / len(components)
    return sum(
        stake * _component_profit(goal_diff + component, home_decimal_odds)
        for component in components
    )


def settle_profit(
    goal_diff: int, line: float, decimal_odds: float, side: str
) -> float:
    side_normalized = side.strip().lower()
    if side_normalized == "home":
        return settle_home_profit(goal_diff, line, decimal_odds)
    if side_normalized == "away":
        return settle_home_profit(-goal_diff, -line, decimal_odds)
    raise ValueError("side must be 'home' or 'away'")

