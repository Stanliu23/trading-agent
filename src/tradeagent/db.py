"""SQLite store for snapshots, triggers, recommendations, emails and review items."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tradeagent.config import PROJECT_ROOT

DEFAULT_DB = PROJECT_ROOT / "data" / "agent.db"
SCHEMA_VERSION = 2

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
    status    TEXT NOT NULL CHECK (status IN ('ok','rejected','error','capped','off'))
);

-- Keys of alerts and macro stories already sent, so nothing is emailed twice.
CREATE TABLE IF NOT EXISTS sent_keys (
    key     TEXT PRIMARY KEY,
    sent_at TEXT NOT NULL
);

-- Alpaca paper test: why the agent placed each order (Alpaca keeps the order itself).
CREATE TABLE IF NOT EXISTS paper_intents (
    client_order_id  TEXT PRIMARY KEY,
    placed_at        TEXT NOT NULL,
    session          TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    side             TEXT NOT NULL CHECK (side IN ('buy','sell')),
    purpose          TEXT NOT NULL CHECK (purpose IN ('entry','stop','target','signal','time')),
    setup_id         TEXT,
    bucket           TEXT,
    stop             REAL,
    target           REAL,
    max_hold         INTEGER,
    lot_ref          TEXT,
    dollars          REAL,
    qty              REAL,
    status           TEXT NOT NULL CHECK (status IN ('sent','failed')),
    detail           TEXT
);

-- Fill tracker (docs/LEARNING.md): every filled agent order with the price the simulator assumed for it.
CREATE TABLE IF NOT EXISTS fill_log (
    order_id         TEXT PRIMARY KEY,
    account          TEXT NOT NULL,              -- main | MOM | LOWV
    client_order_id  TEXT,
    symbol           TEXT NOT NULL,
    side             TEXT NOT NULL,
    purpose          TEXT,
    submitted_at     TEXT,
    filled_at        TEXT,
    day              TEXT,
    qty              REAL,
    fill             REAL,
    assumed          REAL,
    basis            TEXT,
    cost_pct         REAL,                       -- positive = worse for us than assumed
    question         TEXT,                       -- Q1 | Q2 | Q5 | ''
    lot_entry        REAL,
    lot_stop         REAL
);

-- Learning questions (docs/LEARNING.md): every weekly answer, so what was learned and when is kept.
CREATE TABLE IF NOT EXISTS learning_log (
    scored_at  TEXT NOT NULL,
    qid        TEXT NOT NULL,
    n          INTEGER,
    need       INTEGER,
    status     TEXT NOT NULL,
    text       TEXT NOT NULL,
    PRIMARY KEY (scored_at, qid)
);

-- Strategy experiments (each in its own Alpaca paper account): why the agent placed each order.
CREATE TABLE IF NOT EXISTS exp_intents (
    client_order_id  TEXT PRIMARY KEY,
    exp_id           TEXT NOT NULL,
    cycle            TEXT NOT NULL,
    placed_at        TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    side             TEXT NOT NULL CHECK (side IN ('buy','sell')),
    dollars          REAL,
    qty              REAL,
    status           TEXT NOT NULL CHECK (status IN ('sent','failed')),
    detail           TEXT
);

-- Strategy experiments: each account at each close.
CREATE TABLE IF NOT EXISTS exp_daily (
    exp_id    TEXT NOT NULL,
    day       TEXT NOT NULL,
    equity    REAL NOT NULL,
    cash      REAL NOT NULL,
    PRIMARY KEY (exp_id, day)
);

-- Alpaca paper test: the account at each close (value history for the emails).
CREATE TABLE IF NOT EXISTS paper_daily (
    day       TEXT PRIMARY KEY,
    value     REAL NOT NULL,
    cash_lt   REAL NOT NULL,
    cash_st   REAL NOT NULL,
    lt_value  REAL NOT NULL,
    st_value  REAL NOT NULL
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
        _migrate(conn)
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


def _migrate(conn: sqlite3.Connection) -> None:
    """v1 -> v2: the ai_runs log changed its status values; it only holds a run log, so it is rebuilt."""
    has_meta = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
    if not has_meta:
        return
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row and int(row[0]) < 2:
        conn.execute("DROP TABLE IF EXISTS ai_runs")
        conn.execute("UPDATE meta SET value='2' WHERE key='schema_version'")


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
