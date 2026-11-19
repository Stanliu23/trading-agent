"""SQLite store for snapshots, triggers, recommendations, emails and review items."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tradeagent.config import PROJECT_ROOT

DEFAULT_DB = PROJECT_ROOT / "data" / "agent.db"
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row per scheduled run; doubles as the heartbeat.
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('intraday','premarket','close','weekly','manual')),
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL CHECK (status IN ('running','ok','quiet','error')),
    detail      TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    id                INTEGER PRIMARY KEY,
    taken_at          TEXT NOT NULL,
    source            TEXT NOT NULL CHECK (source IN ('schwab_api','csv')),
    account_value     REAL NOT NULL,
    cash              REAL NOT NULL,
    long_term_value   REAL NOT NULL,
    short_term_value  REAL NOT NULL,
    stale_since       TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    snapshot_id   INTEGER NOT NULL REFERENCES snapshots(id),
    symbol        TEXT NOT NULL,
    quantity      REAL NOT NULL,          -- fractional shares allowed
    price         REAL NOT NULL,
    market_value  REAL NOT NULL,
    bucket        TEXT CHECK (bucket IN ('long_term','short_term')),
    PRIMARY KEY (snapshot_id, symbol)
);

CREATE TABLE IF NOT EXISTS bucket_tags (
    symbol     TEXT PRIMARY KEY,
    bucket     TEXT NOT NULL CHECK (bucket IN ('long_term','short_term')),
    tagged_at  TEXT NOT NULL,
    source     TEXT NOT NULL CHECK (source IN ('recommendation','you'))
);

CREATE TABLE IF NOT EXISTS triggers (
    id        INTEGER PRIMARY KEY,
    fired_at  TEXT NOT NULL,
    run_id    INTEGER REFERENCES runs(id),
    rule      TEXT NOT NULL,
    symbol    TEXT,
    urgent    INTEGER NOT NULL DEFAULT 0,
    detail    TEXT NOT NULL               -- JSON
);

CREATE TABLE IF NOT EXISTS recommendations (
    id            INTEGER PRIMARY KEY,
    created_at    TEXT NOT NULL,
    profile       TEXT NOT NULL CHECK (profile IN ('aggressive','moderate')),
    symbol        TEXT NOT NULL,
    action        TEXT NOT NULL CHECK (action IN ('buy','add','trim','sell','hold')),
    bucket        TEXT NOT NULL CHECK (bucket IN ('long_term','short_term')),
    tier          INTEGER NOT NULL CHECK (tier IN (1,2,3)),
    stars         INTEGER NOT NULL CHECK (stars BETWEEN 0 AND 5),
    setup_id      TEXT NOT NULL,
    size_usd      REAL NOT NULL,
    entry         REAL,
    stop          REAL,
    target        REAL,
    max_loss_usd  REAL NOT NULL,
    evidence      TEXT NOT NULL,          -- JSON: source tags for every number
    acted         INTEGER,                -- filled from later Schwab transactions
    outcome_pct   REAL
);

CREATE TABLE IF NOT EXISTS emails (
    id         INTEGER PRIMARY KEY,
    sent_at    TEXT NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('urgent','premarket','digest','weekly','reminder')),
    subject    TEXT NOT NULL,
    shadow     INTEGER NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('sent','failed','suppressed')),
    body_hash  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_runs (
    id        INTEGER PRIMARY KEY,
    run_at    TEXT NOT NULL,
    purpose   TEXT NOT NULL,
    status    TEXT NOT NULL CHECK (status IN ('ok','fallback','error','capped'))
);

CREATE TABLE IF NOT EXISTS review_items (
    id                 INTEGER PRIMARY KEY,
    week_start         TEXT NOT NULL,
    outcome            TEXT NOT NULL CHECK (outcome IN ('well','wrong')),
    cause              TEXT CHECK (cause IN ('calculation','decision','system','expected_variance')),
    step               TEXT,
    detail             TEXT NOT NULL,
    recommendation_id  INTEGER REFERENCES recommendations(id)
);
"""


def connect(path: Path = DEFAULT_DB) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path = DEFAULT_DB) -> Path:
    """Create tables if missing. Safe to run repeatedly."""
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT(key) DO NOTHING",
            (str(SCHEMA_VERSION),),
        )
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('ever_reached_switch', '0') "
            "ON CONFLICT(key) DO NOTHING"
        )
    return path


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else row["value"]


def ever_reached_switch(conn: sqlite3.Connection) -> bool:
    return get_meta(conn, "ever_reached_switch") == "1"


def mark_reached_switch(conn: sqlite3.Connection) -> None:
    """One-way latch: once the account reaches the switch level, it stays moderate."""
    conn.execute("UPDATE meta SET value = '1' WHERE key = 'ever_reached_switch'")
    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('reached_switch_at', ?) ON CONFLICT(key) DO NOTHING",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
    )
