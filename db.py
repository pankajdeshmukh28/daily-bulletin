"""Turso (hosted libSQL/SQLite) persistence layer.

Replaces the old git-commit-back JSONL/JSON files: run history, the day's
market snapshot (index/movers/ETFs), picks (for performance tracking + the
self-calibration feedback loop), and the full digest content all live in a
private, token-gated database instead of the repo itself — safe even if the
repo is public.

Talks to Turso's plain HTTP pipeline API directly via `requests` rather than
the `libsql-client` package: that package's sync wrapper hangs/fails its
websocket handshake against current Turso servers (tested live — a raw HTTPS
request to the same endpoint succeeds in <1s), so this avoids the extra
dependency and the bug.

Needs TURSO_DATABASE_URL + TURSO_AUTH_TOKEN (from .env locally, from repo
secrets in CI). `config` is imported for its load_dotenv side effect so this
works regardless of import order.
"""

import os

import requests

import config  # noqa: F401 - triggers .env loading

_SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        market TEXT NOT NULL,
        status TEXT NOT NULL,              -- 'success' | 'failed'
        num_picks INTEGER,
        num_etf_picks INTEGER,
        error TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(date, market)
    )""",
    """CREATE TABLE IF NOT EXISTS market_snapshot (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        market TEXT NOT NULL,
        ticker TEXT NOT NULL,
        name TEXT,
        role TEXT NOT NULL,                -- 'index' | 'mover' | 'etf'
        close REAL,
        pct_1d REAL,
        pct_5d REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(date, market, ticker, role)
    )""",
    """CREATE TABLE IF NOT EXISTS picks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        market TEXT NOT NULL,
        ticker TEXT NOT NULL,
        name TEXT,
        kind TEXT NOT NULL,                -- 'stock' | 'etf'
        conviction INTEGER,
        signal_type TEXT,
        entry_close REAL,
        index_entry_close REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(date, market, ticker)
    )""",
    """CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        market TEXT NOT NULL,
        analysis_json TEXT NOT NULL,       -- full Claude output: picks, etf_picks, watchlist, avoid
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(date, market)
    )""",
]

_schema_ready = False


def _pipeline_url() -> str:
    url = os.environ["TURSO_DATABASE_URL"]
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    return url.rstrip("/") + "/v2/pipeline"


def _execute_many(statements: list[tuple[str, list]]) -> list[dict]:
    """Run one or more SQL statements in a single HTTP round-trip.
    statements: [(sql, [params...]), ...]. Returns each statement's result dict.
    """
    def _bind(v):
        if v is None:
            return {"type": "null"}
        if isinstance(v, bool):
            return {"type": "integer", "value": str(int(v))}
        if isinstance(v, int):
            return {"type": "integer", "value": str(v)}
        if isinstance(v, float):
            return {"type": "float", "value": v}
        return {"type": "text", "value": str(v)}

    body = {
        "requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": [_bind(p) for p in params]}}
            for sql, params in statements
        ] + [{"type": "close"}]
    }
    resp = requests.post(
        _pipeline_url(),
        headers={"Authorization": f"Bearer {os.environ['TURSO_AUTH_TOKEN']}"},
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json()["results"]
    for r in results:
        if r["type"] == "error":
            raise RuntimeError(f"Turso query failed: {r['error']}")
    return results[:-1]  # drop the trailing 'close' ack


def _execute(sql: str, params: list | None = None) -> dict:
    return _execute_many([(sql, params or [])])[0]


def _cell_value(cell: dict):
    # Hrana sends integers as strings (to preserve 64-bit precision beyond
    # JS's safe-integer range) but floats as real JSON numbers — cast
    # integers back so callers get proper Python ints, not '"4"'.
    if cell["type"] == "null":
        return None
    if cell["type"] == "integer":
        return int(cell["value"])
    return cell["value"]


def _rows_as_dicts(result: dict) -> list[dict]:
    cols = [c["name"] for c in result["response"]["result"]["cols"]]
    return [
        {col: _cell_value(cell) for col, cell in zip(cols, row)}
        for row in result["response"]["result"]["rows"]
    ]


def ensure_schema():
    global _schema_ready
    if not _schema_ready:
        _execute_many([(s, []) for s in _SCHEMA_STATEMENTS])
        _schema_ready = True


def record_run(market: str, date: str, status: str, *, num_picks: int = 0,
                num_etf_picks: int = 0, error: str | None = None):
    ensure_schema()
    _execute(
        """INSERT INTO runs (date, market, status, num_picks, num_etf_picks, error)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(date, market) DO UPDATE SET
             status=excluded.status, num_picks=excluded.num_picks,
             num_etf_picks=excluded.num_etf_picks, error=excluded.error""",
        [date, market, status, num_picks, num_etf_picks, error],
    )


def save_market_snapshot(market: str, date: str, rows: list[dict]):
    """rows: [{ticker, name, role, close, pct_1d, pct_5d}, ...]"""
    if not rows:
        return
    ensure_schema()
    stmts = [
        ("""INSERT INTO market_snapshot (date, market, ticker, name, role, close, pct_1d, pct_5d)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, market, ticker, role) DO UPDATE SET
              close=excluded.close, pct_1d=excluded.pct_1d, pct_5d=excluded.pct_5d""",
         [date, market, r["ticker"], r.get("name", ""), r["role"],
          r["close"], r["pct_1d"], r["pct_5d"]])
        for r in rows
    ]
    _execute_many(stmts)


def save_picks(market: str, date: str, rows: list[dict]):
    """rows: [{ticker, name, kind, conviction, signal_type, entry_close, index_entry_close}, ...]
    Idempotent: a same-day re-run updates rather than duplicates (UNIQUE on date+market+ticker).
    """
    if not rows:
        return
    ensure_schema()
    stmts = [
        ("""INSERT INTO picks (date, market, ticker, name, kind, conviction, signal_type,
                                entry_close, index_entry_close)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, market, ticker) DO UPDATE SET
              conviction=excluded.conviction, signal_type=excluded.signal_type""",
         [date, market, r["ticker"], r.get("name", ""), r["kind"],
          r["conviction"], r["signal_type"], r["entry_close"], r.get("index_entry_close")])
        for r in rows
    ]
    _execute_many(stmts)


def load_picks(market: str | None = None) -> list[dict]:
    ensure_schema()
    if market:
        result = _execute("SELECT * FROM picks WHERE market = ? ORDER BY date", [market])
    else:
        result = _execute("SELECT * FROM picks ORDER BY date")
    return _rows_as_dicts(result)


def save_report(market: str, date: str, analysis: dict):
    import json
    ensure_schema()
    _execute(
        """INSERT INTO reports (date, market, analysis_json) VALUES (?, ?, ?)
           ON CONFLICT(date, market) DO UPDATE SET analysis_json=excluded.analysis_json""",
        [date, market, json.dumps(analysis)],
    )


def load_report(market: str, date: str) -> dict | None:
    import json
    ensure_schema()
    result = _execute(
        "SELECT analysis_json FROM reports WHERE market = ? AND date = ?", [market, date]
    )
    rows = _rows_as_dicts(result)
    return json.loads(rows[0]["analysis_json"]) if rows else None


def load_runs(limit: int = 20) -> list[dict]:
    ensure_schema()
    result = _execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", [limit])
    return _rows_as_dicts(result)
