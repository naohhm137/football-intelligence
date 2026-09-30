CREATE TABLE IF NOT EXISTS cache_entries (
    cache_key TEXT PRIMARY KEY,
    payload_json JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS source_health (
    source TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    fresh_until TIMESTAMPTZ,
    request_url TEXT,
    error_code TEXT,
    quota_remaining INTEGER,
    last_success_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS fixture_aliases (
    alias TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    fixture_id BIGINT,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (alias, canonical_name)
);

CREATE TABLE IF NOT EXISTS analyses (
    analysis_id TEXT PRIMARY KEY,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    analysis_id TEXT NOT NULL REFERENCES analyses(analysis_id),
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    PRIMARY KEY (analysis_id, url, title)
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    analysis_id TEXT NOT NULL REFERENCES analyses(analysis_id),
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    payload_json JSONB NOT NULL,
    PRIMARY KEY (analysis_id, bookmaker, market, captured_at)
);

CREATE TABLE IF NOT EXISTS results (
    fixture_id BIGINT PRIMARY KEY,
    payload_json JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_jobs (
    fixture_id BIGINT NOT NULL,
    checkpoint_minutes INTEGER NOT NULL,
    status TEXT NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    error_code TEXT,
    PRIMARY KEY (fixture_id, checkpoint_minutes)
);

CREATE TABLE IF NOT EXISTS tracked_fixtures (
    fixture_id BIGINT PRIMARY KEY,
    kickoff_utc TIMESTAMPTZ NOT NULL,
    payload_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fixture_aliases_fixture_id
    ON fixture_aliases(fixture_id);
CREATE INDEX IF NOT EXISTS idx_source_health_updated_at
    ON source_health(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_created_at
    ON analyses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_captured_at
    ON odds_snapshots(captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_collection_jobs_status
    ON collection_jobs(status, claimed_at);
CREATE INDEX IF NOT EXISTS idx_tracked_fixtures_kickoff
    ON tracked_fixtures(kickoff_utc);
