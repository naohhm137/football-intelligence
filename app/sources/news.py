from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import requests

from app.contracts import EvidenceItem, ResolvedFixture, SourceResult
from app.storage import Store


GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _publication_time(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        if len(raw) == 16 and raw.endswith("Z") and "T" in raw:
            return _iso(datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc))
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return None
        return _iso(parsed)
    except ValueError:
        return None


class NewsClient:
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

    def fetch(self, fixture: ResolvedFixture) -> SourceResult[list[EvidenceItem]]:
        fetched = self._now().astimezone(timezone.utc)
        cache_key = f"gdelt:{fixture.fixture_id}"
        if self._store:
            cached = self._store.get_cache(cache_key, _iso(fetched))
            if cached:
                return self.parse(cached["payload"], fetched_at=_publication_datetime(cached["fetched_at"]))

        params = {
            "query": f'"{fixture.home_team}" OR "{fixture.away_team}"',
            "mode": "ArtList",
            "maxrecords": 50,
            "format": "json",
            "sort": "DateDesc",
        }
        try:
            response = self._transport.get(
                GDELT_DOC_URL, params=params, timeout=self._timeout_seconds
            )
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP_{response.status_code}")
            payload = response.json()
        except (requests.RequestException, RuntimeError, TypeError, ValueError) as exc:
            return SourceResult(
                value=[], status="error", source="gdelt", fetched_at=_iso(fetched),
                request_url=GDELT_DOC_URL, error_code=type(exc).__name__.upper()
            )
        if self._store:
            self._store.put_cache(
                cache_key,
                {"payload": payload, "fetched_at": _iso(fetched)},
                _iso(fetched + timedelta(minutes=30)),
            )
        return self.parse(payload, fetched_at=fetched)

    def parse(
        self, payload: dict[str, Any], *, fetched_at: datetime | None = None
    ) -> SourceResult[list[EvidenceItem]]:
        fetched = (fetched_at or self._now()).astimezone(timezone.utc)
        items: list[EvidenceItem] = []
        for article in payload.get("articles", []) if isinstance(payload, dict) else []:
            url = str(article.get("url") or "").strip()
            published = _publication_time(article.get("seendate"))
            title = str(article.get("title") or "").strip()
            if not url or not published or not title:
                continue
            publisher = str(article.get("domain") or "GDELT").strip()
            items.append(
                EvidenceItem(
                    title=title,
                    url=url,
                    publisher=publisher,
                    published_at=published,
                    fetched_at=_iso(fetched),
                    summary=title,
                    category="news",
                )
            )
        return SourceResult(
            value=items,
            status="ok" if items else "missing",
            source="gdelt",
            fetched_at=_iso(fetched),
            fresh_until=_iso(fetched + timedelta(minutes=30)),
            request_url=GDELT_DOC_URL,
            error_code=None if items else "NEWS_NOT_AVAILABLE",
        )


def _publication_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)

