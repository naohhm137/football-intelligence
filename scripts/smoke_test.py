from __future__ import annotations

import argparse
import json
import re
import time
from typing import Any

import requests


SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{12,}")
DEFAULT_QUERY = {
    "home_team": "Arsenal",
    "away_team": "Chelsea",
    "kickoff_local": "2026-10-03T20:00:00+08:00",
}


def _json(response, expected_status: int) -> dict[str, Any]:
    if response.status_code != expected_status:
        raise AssertionError(f"unexpected HTTP status: {response.status_code}")
    payload = response.json()
    if SECRET_PATTERN.search(json.dumps(payload)):
        raise AssertionError("secret-shaped text found in response")
    return payload


def run_smoke(base_url: str, *, session=requests, query=None) -> dict[str, Any]:
    base = base_url.rstrip("/")
    started = time.perf_counter()
    health = _json(session.get(f"{base}/api/health", timeout=20), 200)
    if health.get("status") != "ok" or health.get("database", {}).get("status") != "ok":
        raise AssertionError("health check is not ready")

    public_query = dict(query or DEFAULT_QUERY)
    if set(public_query) != {"home_team", "away_team", "kickoff_local"}:
        raise AssertionError("smoke query must contain exactly three public fields")
    analysis = _json(
        session.post(f"{base}/api/analyze", json=public_query, timeout=90), 200
    )
    analysis_id = analysis.get("analysis_id")
    if not analysis_id:
        raise AssertionError("analysis id missing")

    saved = _json(
        session.get(f"{base}/api/analysis/{analysis_id}", timeout=20), 200
    )
    if saved.get("analysis_id") != analysis_id:
        raise AssertionError("persisted analysis id mismatch")

    return {
        "health": health["status"],
        "analysis": analysis.get("action"),
        "persistence": "ok",
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--home", default=DEFAULT_QUERY["home_team"])
    parser.add_argument("--away", default=DEFAULT_QUERY["away_team"])
    parser.add_argument("--kickoff", default=DEFAULT_QUERY["kickoff_local"])
    args = parser.parse_args()
    report = run_smoke(
        args.base_url,
        query={
            "home_team": args.home,
            "away_team": args.away,
            "kickoff_local": args.kickoff,
        },
    )
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
