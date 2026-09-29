from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import requests

from app.contracts import ResolvedFixture, SourceResult, WeatherEvidence
from app.storage import Store


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _parse_time(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class WeatherClient:
    def __init__(
        self,
        *,
        store: Store | None = None,
        transport: Any | None = None,
        timeout_seconds: float = 12.0,
        now: Callable[[], datetime] | None = None,
    ):
        self._store = store
        self._transport = transport or requests.Session()
        self._timeout_seconds = timeout_seconds
        self._now = now or (lambda: datetime.now(timezone.utc))

    def fetch(self, fixture: ResolvedFixture) -> SourceResult[WeatherEvidence | None]:
        fetched = self._now().astimezone(timezone.utc)
        if fixture.venue_latitude is None or fixture.venue_longitude is None:
            return SourceResult(
                value=None,
                status="missing",
                source="open-meteo",
                fetched_at=_iso(fetched),
                request_url=OPEN_METEO_URL,
                error_code="VENUE_COORDINATES_MISSING",
            )

        kickoff = _parse_time(fixture.kickoff_utc)
        cache_key = (
            f"open-meteo:{fixture.venue_latitude:.4f}:"
            f"{fixture.venue_longitude:.4f}:{kickoff.date().isoformat()}"
        )
        if self._store:
            cached = self._store.get_cache(cache_key, _iso(fetched))
            if cached:
                return self.parse(
                    cached["payload"], fixture, fetched_at=_parse_time(cached["fetched_at"])
                )

        params = {
            "latitude": fixture.venue_latitude,
            "longitude": fixture.venue_longitude,
            "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
            "timezone": "UTC",
            "start_date": kickoff.date().isoformat(),
            "end_date": kickoff.date().isoformat(),
        }
        try:
            response = self._transport.get(
                OPEN_METEO_URL, params=params, timeout=self._timeout_seconds
            )
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP_{response.status_code}")
            payload = response.json()
        except (requests.RequestException, RuntimeError, TypeError, ValueError) as exc:
            return SourceResult(
                value=None,
                status="error",
                source="open-meteo",
                fetched_at=_iso(fetched),
                request_url=OPEN_METEO_URL,
                error_code=type(exc).__name__.upper(),
            )

        if self._store:
            self._store.put_cache(
                cache_key,
                {"payload": payload, "fetched_at": _iso(fetched)},
                _iso(fetched + timedelta(hours=1)),
            )
        return self.parse(payload, fixture, fetched_at=fetched)

    def parse(
        self,
        payload: dict[str, Any],
        fixture: ResolvedFixture,
        *,
        fetched_at: datetime | None = None,
    ) -> SourceResult[WeatherEvidence | None]:
        fetched = (fetched_at or self._now()).astimezone(timezone.utc)
        hourly = payload.get("hourly") if isinstance(payload, dict) else None
        times = hourly.get("time", []) if isinstance(hourly, dict) else []
        kickoff = _parse_time(fixture.kickoff_utc)
        if not times:
            return SourceResult(
                value=None,
                status="missing",
                source="open-meteo",
                fetched_at=_iso(fetched),
                request_url=OPEN_METEO_URL,
                error_code="FORECAST_NOT_AVAILABLE",
            )
        try:
            index = min(
                range(len(times)),
                key=lambda item: (
                    abs((_parse_time(times[item]) - kickoff).total_seconds()),
                    -_parse_time(times[item]).timestamp(),
                ),
            )
            evidence = WeatherEvidence(
                temperature_c=float(hourly["temperature_2m"][index]),
                precipitation_mm=float(hourly["precipitation"][index]),
                wind_kph=float(hourly["wind_speed_10m"][index]),
                humidity_percent=float(hourly["relative_humidity_2m"][index]),
                forecast_for=_iso(_parse_time(times[index])),
            )
        except (KeyError, IndexError, TypeError, ValueError):
            return SourceResult(
                value=None,
                status="error",
                source="open-meteo",
                fetched_at=_iso(fetched),
                request_url=OPEN_METEO_URL,
                error_code="FORECAST_SCHEMA_INVALID",
            )
        return SourceResult(
            value=evidence,
            status="ok",
            source="open-meteo",
            fetched_at=_iso(fetched),
            fresh_until=_iso(fetched + timedelta(hours=1)),
            request_url=OPEN_METEO_URL,
        )

