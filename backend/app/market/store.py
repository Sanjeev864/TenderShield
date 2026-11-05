"""Market intelligence store: real historical awards, bids and supplier profiles.

Kept in its own SQLite file (``market.db``) so resetting the demo tender never wipes the real
datasets. Every row records the dataset it came from (``source_id``), and every dataset records
its origin URL, licence, file SHA-256 and import time, so any supplier match can be traced back to
the published record that supports it.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

from ..config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_sources (
    source_id TEXT PRIMARY KEY,
    adapter TEXT NOT NULL,
    title TEXT NOT NULL,
    origin_url TEXT,
    licence TEXT,
    country_scope TEXT,
    file_sha256 TEXT,
    rows_awards INTEGER NOT NULL DEFAULT 0,
    rows_bids INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT NOT NULL,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS market_awards (
    award_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    tender_ref TEXT,
    lot_ref TEXT,
    project_id TEXT,
    buyer TEXT,
    title TEXT,
    description TEXT,
    cpv TEXT,
    capability TEXT NOT NULL,
    capability_basis TEXT NOT NULL,
    category TEXT,
    method TEXT,
    country TEXT,
    region TEXT,
    signed_on TEXT,
    supplier_key TEXT NOT NULL,
    supplier_name TEXT NOT NULL,
    supplier_country TEXT,
    amount REAL,
    currency TEXT,
    amount_inr_cr REAL,
    n_bidders INTEGER
);
CREATE INDEX IF NOT EXISTS idx_awards_supplier ON market_awards(supplier_key);
CREATE INDEX IF NOT EXISTS idx_awards_capability ON market_awards(capability);
CREATE INDEX IF NOT EXISTS idx_awards_source ON market_awards(source_id);
CREATE TABLE IF NOT EXISTS market_bids (
    bid_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    tender_ref TEXT NOT NULL,
    lot_ref TEXT,
    supplier_key TEXT NOT NULL,
    supplier_name TEXT NOT NULL,
    amount REAL,
    currency TEXT,
    won INTEGER,
    rank INTEGER,
    bid_date TEXT,
    capability TEXT
);
CREATE INDEX IF NOT EXISTS idx_bids_tender ON market_bids(tender_ref, lot_ref);
CREATE INDEX IF NOT EXISTS idx_bids_supplier ON market_bids(supplier_key);
CREATE TABLE IF NOT EXISTS market_suppliers (
    supplier_key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT,
    sources TEXT NOT NULL,
    n_awards INTEGER NOT NULL,
    total_inr_cr REAL,
    max_inr_cr REAL,
    median_inr_cr REAL,
    first_award TEXT,
    last_award TEXT,
    capabilities TEXT NOT NULL,
    capability_values TEXT NOT NULL,
    n_bids INTEGER NOT NULL DEFAULT 0,
    msme_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    msme_evidence TEXT,
    identifiers TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_suppliers_name ON market_suppliers(name);
"""

JSON_COLUMNS = {"sources", "capabilities", "capability_values", "identifiers", "msme_evidence"}


def market_db_path() -> Path:
    override = os.environ.get("TS_MARKET_DB")
    return Path(override) if override else get_settings().data_dir / "market.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or market_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def market_session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    out = dict(r)
    for key in JSON_COLUMNS & out.keys():
        if isinstance(out[key], str):
            out[key] = json.loads(out[key])
    return out


def rows(cursor: Iterable[sqlite3.Row]) -> list[dict]:
    return [row(r) for r in cursor]  # type: ignore[misc]


def drop_source(conn: sqlite3.Connection, source_id: str) -> None:
    for table in ("market_awards", "market_bids", "market_sources"):
        conn.execute(f"DELETE FROM {table} WHERE source_id = ?", (source_id,))


def status(conn: sqlite3.Connection) -> dict:
    sources = rows(conn.execute("SELECT * FROM market_sources ORDER BY imported_at"))
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("market_awards", "market_bids", "market_suppliers")}
    by_cap = {r[0]: r[1] for r in conn.execute(
        "SELECT capability, COUNT(*) FROM market_awards GROUP BY capability ORDER BY 2 DESC")}
    return {"sources": sources, "counts": counts, "awards_by_capability": by_cap,
            "real_data_loaded": counts["market_awards"] > 0}
