CREATE TABLE IF NOT EXISTS cache_entries (
    cache_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_health (
    source TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    fresh_until TEXT,
    request_url TEXT,
    error_code TEXT,
    quota_remaining INTEGER,
    last_success_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fixture_aliases (
    alias TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    fixture_id INTEGER,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (alias, canonical_name)
);

CREATE TABLE IF NOT EXISTS analyses (
    analysis_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    analysis_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (analysis_id, url, title)
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    analysis_id TEXT NOT NULL,
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (analysis_id, bookmaker, market, captured_at)
);

CREATE TABLE IF NOT EXISTS results (
    fixture_id INTEGER PRIMARY KEY,
    payload_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
