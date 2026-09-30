from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from app.contracts import AnalysisReport, ResearchBundle, ResolvedFixture, SourceStatus


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _parse_utc(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    return parsed.astimezone(timezone.utc)


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class Store:
    def __init__(self, connection: Any, dialect: str, reconnect=None):
        self._connection = connection
        self._dialect = dialect
        self._reconnect = reconnect
        self._lock = threading.RLock()

    @classmethod
    def connect(cls, database_url: str) -> "Store":
        if database_url.startswith("sqlite:///"):
            raw_path = unquote(database_url.removeprefix("sqlite:///"))
            path = ":memory:" if raw_path == ":memory:" else str(Path(raw_path))
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            store = cls(connection, "sqlite")
        elif urlparse(database_url).scheme in {"postgres", "postgresql"}:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError("PostgreSQL 需要安装 psycopg") from exc
            def reconnect():
                return psycopg.connect(database_url, row_factory=dict_row)

            connection = reconnect()
            store = cls(connection, "postgres", reconnect=reconnect)
        else:
            raise ValueError("DATABASE_URL 仅支持 sqlite:///、postgres:// 或 postgresql://")

        store._initialize_schema()
        return store

    def _initialize_schema(self) -> None:
        if self._dialect == "postgres":
            return
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        self._connection.executescript(schema)
        columns = {
            row[1] for row in self._connection.execute("PRAGMA table_info(source_health)")
        }
        if "last_success_at" not in columns:
            self._connection.execute(
                "ALTER TABLE source_health ADD COLUMN last_success_at TEXT"
            )
        self._connection.commit()

    def _placeholder(self) -> str:
        return "?" if self._dialect == "sqlite" else "%s"

    def _ensure_connection(self) -> None:
        if self._dialect != "postgres" or not self._connection.closed:
            return
        if self._reconnect is None:
            raise RuntimeError("PostgreSQL connection is closed")
        self._connection = self._reconnect()

    def _execute(self, sql: str, parameters: tuple[Any, ...] = ()):
        self._ensure_connection()
        cursor = self._connection.cursor()
        cursor.execute(sql, parameters)
        return cursor

    @staticmethod
    def _row_value(row: Any, key: str) -> Any:
        return row[key]

    def put_cache(self, key: str, value: Any, expires_at: str) -> None:
        if not key:
            raise ValueError("缓存键不能为空")
        _parse_utc(expires_at)
        payload = _canonical_json(value)
        marker = self._placeholder()
        if self._dialect == "sqlite":
            sql = (
                "INSERT INTO cache_entries "
                "(cache_key, payload_json, expires_at, created_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(cache_key) DO UPDATE SET "
                "payload_json=excluded.payload_json, expires_at=excluded.expires_at, "
                "created_at=excluded.created_at"
            )
        else:
            sql = (
                "INSERT INTO cache_entries "
                f"(cache_key, payload_json, expires_at, created_at) VALUES ({marker}, {marker}, {marker}, {marker}) "
                "ON CONFLICT(cache_key) DO UPDATE SET "
                "payload_json=EXCLUDED.payload_json, expires_at=EXCLUDED.expires_at, "
                "created_at=EXCLUDED.created_at"
            )
        with self._lock:
            self._execute(sql, (key, payload, expires_at, _now_utc())).close()
            self._connection.commit()

    def get_cache(self, key: str, now: str) -> Any | None:
        current_time = _parse_utc(now)
        marker = self._placeholder()
        with self._lock:
            cursor = self._execute(
                f"SELECT payload_json, expires_at FROM cache_entries WHERE cache_key={marker}",
                (key,),
            )
            row = cursor.fetchone()
            cursor.close()
        if row is None or _parse_utc(self._row_value(row, "expires_at")) <= current_time:
            return None
        return json.loads(self._row_value(row, "payload_json"))

    def record_source_status(self, status: SourceStatus) -> None:
        marker = self._placeholder()
        with self._lock:
            cursor = self._execute(
                f"SELECT last_success_at FROM source_health WHERE source={marker}",
                (status.source,),
            )
            previous = cursor.fetchone()
            cursor.close()
            last_success_at = (
                status.fetched_at
                if status.status in {"ok", "stale"}
                else (self._row_value(previous, "last_success_at") if previous else None)
            )
            values = (
                status.source,
                status.status,
                status.fetched_at,
                status.fresh_until,
                status.request_url,
                status.error_code,
                status.quota_remaining,
                last_success_at,
                _now_utc(),
            )
            names = (
                "source, status, fetched_at, fresh_until, request_url, error_code, "
                "quota_remaining, last_success_at, updated_at"
            )
            excluded = "excluded" if self._dialect == "sqlite" else "EXCLUDED"
            sql = (
                f"INSERT INTO source_health ({names}) "
                f"VALUES ({', '.join([marker] * 9)}) ON CONFLICT(source) DO UPDATE SET "
                f"status={excluded}.status, fetched_at={excluded}.fetched_at, "
                f"fresh_until={excluded}.fresh_until, request_url={excluded}.request_url, "
                f"error_code={excluded}.error_code, quota_remaining={excluded}.quota_remaining, "
                f"last_success_at={excluded}.last_success_at, updated_at={excluded}.updated_at"
            )
            self._execute(sql, values).close()
            self._connection.commit()

    def get_source_status(self, source: str) -> dict[str, Any] | None:
        marker = self._placeholder()
        with self._lock:
            cursor = self._execute(
                f"SELECT source, status, fetched_at, fresh_until, request_url, error_code, quota_remaining, last_success_at, updated_at "
                f"FROM source_health WHERE source={marker}",
                (source,),
            )
            row = cursor.fetchone()
            cursor.close()
        return dict(row) if row is not None else None

    def list_source_statuses(self) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self._execute(
                "SELECT source, status, fetched_at, fresh_until, request_url, "
                "error_code, quota_remaining, last_success_at, updated_at "
                "FROM source_health ORDER BY source"
            )
            rows = cursor.fetchall()
            cursor.close()
        return [dict(row) for row in rows]

    def health(self) -> dict[str, str]:
        with self._lock:
            cursor = self._execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            self._connection.commit()
        return {"status": "ok", "dialect": self._dialect}

    def claim_collection_job(
        self, fixture_id: int, checkpoint_minutes: int, claimed_at: str
    ) -> bool:
        claimed = _parse_utc(claimed_at)
        cutoff = (claimed - timedelta(minutes=15)).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
        marker = self._placeholder()
        insert = (
            "INSERT INTO collection_jobs "
            "(fixture_id, checkpoint_minutes, status, claimed_at) "
            f"VALUES ({marker}, {marker}, {marker}, {marker}) "
            "ON CONFLICT(fixture_id, checkpoint_minutes) DO NOTHING"
        )
        retry = (
            "UPDATE collection_jobs SET status='running', claimed_at="
            f"{marker}, completed_at=NULL, error_code=NULL "
            f"WHERE fixture_id={marker} AND checkpoint_minutes={marker} "
            f"AND status='failed' AND claimed_at<={marker}"
        )
        with self._lock:
            cursor = self._execute(
                insert, (fixture_id, checkpoint_minutes, "running", claimed_at)
            )
            inserted = cursor.rowcount == 1
            cursor.close()
            if not inserted:
                cursor = self._execute(
                    retry, (claimed_at, fixture_id, checkpoint_minutes, cutoff)
                )
                inserted = cursor.rowcount == 1
                cursor.close()
            self._connection.commit()
        return inserted

    def finish_collection_job(
        self,
        fixture_id: int,
        checkpoint_minutes: int,
        *,
        completed_at: str,
        error_code: str | None = None,
    ) -> None:
        _parse_utc(completed_at)
        marker = self._placeholder()
        status = "failed" if error_code else "success"
        with self._lock:
            self._execute(
                "UPDATE collection_jobs SET status="
                f"{marker}, completed_at={marker}, error_code={marker} "
                f"WHERE fixture_id={marker} AND checkpoint_minutes={marker}",
                (status, completed_at, error_code, fixture_id, checkpoint_minutes),
            ).close()
            self._connection.commit()

    def track_fixture(self, fixture: ResolvedFixture) -> None:
        payload = _canonical_json(fixture)
        marker = self._placeholder()
        excluded = "excluded" if self._dialect == "sqlite" else "EXCLUDED"
        sql = (
            "INSERT INTO tracked_fixtures "
            f"(fixture_id, kickoff_utc, payload_json, updated_at) VALUES ({', '.join([marker] * 4)}) "
            "ON CONFLICT(fixture_id) DO UPDATE SET "
            f"kickoff_utc={excluded}.kickoff_utc, payload_json={excluded}.payload_json, "
            f"updated_at={excluded}.updated_at"
        )
        with self._lock:
            self._execute(
                sql,
                (fixture.fixture_id, fixture.kickoff_utc, payload, _now_utc()),
            ).close()
            self._connection.commit()

    def list_tracked_fixtures(
        self, *, now: str, horizon_hours: int = 96
    ) -> list[dict[str, Any]]:
        start = _parse_utc(now)
        end = start + timedelta(hours=horizon_hours)
        start_iso = start.isoformat(timespec="seconds").replace("+00:00", "Z")
        end_iso = end.isoformat(timespec="seconds").replace("+00:00", "Z")
        marker = self._placeholder()
        with self._lock:
            cursor = self._execute(
                "SELECT payload_json FROM tracked_fixtures "
                f"WHERE kickoff_utc>={marker} AND kickoff_utc<={marker} "
                "ORDER BY kickoff_utc, fixture_id",
                (start_iso, end_iso),
            )
            rows = cursor.fetchall()
            cursor.close()
        return [json.loads(self._row_value(row, "payload_json")) for row in rows]

    def save_analysis(
        self, bundle: ResearchBundle, report: AnalysisReport
    ) -> str:
        document = {"bundle": _jsonable(bundle), "report": _jsonable(report)}
        payload = _canonical_json(document)
        analysis_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        marker = self._placeholder()
        sql = (
            "INSERT INTO analyses (analysis_id, payload_json, created_at) "
            f"VALUES ({marker}, {marker}, {marker}) ON CONFLICT(analysis_id) DO NOTHING"
        )
        with self._lock:
            self._execute(sql, (analysis_id, payload, _now_utc())).close()

            evidence_sql = (
                "INSERT INTO evidence (analysis_id, url, title, payload_json) "
                f"VALUES ({marker}, {marker}, {marker}, {marker}) "
                "ON CONFLICT(analysis_id, url, title) DO NOTHING"
            )
            for item in bundle.evidence:
                self._execute(
                    evidence_sql,
                    (analysis_id, item.url, item.title, _canonical_json(item)),
                ).close()

            odds_sql = (
                "INSERT INTO odds_snapshots "
                "(analysis_id, bookmaker, market, captured_at, payload_json) "
                f"VALUES ({marker}, {marker}, {marker}, {marker}, {marker}) "
                "ON CONFLICT(analysis_id, bookmaker, market, captured_at) DO NOTHING"
            )
            for snapshot in bundle.odds:
                self._execute(
                    odds_sql,
                    (
                        analysis_id,
                        snapshot.bookmaker,
                        snapshot.market,
                        snapshot.captured_at,
                        _canonical_json(snapshot),
                    ),
                ).close()

            self._connection.commit()
        return analysis_id

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        marker = self._placeholder()
        with self._lock:
            cursor = self._execute(
                f"SELECT payload_json FROM analyses WHERE analysis_id={marker}",
                (analysis_id,),
            )
            row = cursor.fetchone()
            cursor.close()
        if row is None:
            return None
        document = json.loads(self._row_value(row, "payload_json"))
        document["analysis_id"] = analysis_id
        return document

    def list_analysis_ids(self, limit: int = 100) -> list[str]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit 必须在 1 到 1000 之间")
        marker = self._placeholder()
        with self._lock:
            cursor = self._execute(
                f"SELECT analysis_id FROM analyses ORDER BY created_at DESC LIMIT {marker}",
                (limit,),
            )
            rows = cursor.fetchall()
            cursor.close()
        return [self._row_value(row, "analysis_id") for row in rows]

    def list_evidence(self, analysis_id: str) -> list[dict[str, Any]]:
        marker = self._placeholder()
        with self._lock:
            cursor = self._execute(
                f"SELECT payload_json FROM evidence WHERE analysis_id={marker} ORDER BY url, title",
                (analysis_id,),
            )
            rows = cursor.fetchall()
            cursor.close()
        return [json.loads(self._row_value(row, "payload_json")) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._reconnect = None
            self._connection.close()
