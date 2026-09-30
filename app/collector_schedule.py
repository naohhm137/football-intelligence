from __future__ import annotations

from datetime import datetime, timezone


CHECKPOINT_MINUTES = (4320, 1440, 360, 90, 30)
WINDOW_MINUTES = 8


def _utc(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def due_checkpoints(*, kickoff: str, now: str) -> list[int]:
    remaining = (_utc(kickoff) - _utc(now)).total_seconds() / 60
    if remaining < 0:
        return []
    return [
        checkpoint
        for checkpoint in CHECKPOINT_MINUTES
        if abs(remaining - checkpoint) <= WINDOW_MINUTES
    ]
