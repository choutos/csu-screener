"""
Investment Process App — Database Layer
SQLite backend for portfolio, watchlist, and scan management.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "invest.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolio (
    ticker TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    buy_price REAL,
    buy_date TEXT,
    shares REAL DEFAULT 0,
    thesis TEXT,
    kill_signals TEXT,
    status TEXT DEFAULT 'HOLD',  -- HOLD, SELL, BUY_MORE
    notes TEXT,
    last_kill_check TEXT,
    score INTEGER DEFAULT 0,
    max_score INTEGER DEFAULT 24,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS watchlist (
    ticker TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    buy_under REAL,
    score INTEGER DEFAULT 0,
    max_score INTEGER DEFAULT 24,
    thesis TEXT,
    kill_signals TEXT,
    priority TEXT DEFAULT 'MEDIUM',  -- HIGH, MEDIUM, LOW
    source TEXT,  -- how we found it
    first_tracked TEXT DEFAULT (datetime('now')),
    last_checked TEXT DEFAULT (datetime('now')),
    last_price REAL,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scan_results (
    ticker TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    market_cap_m REAL,
    gross_margin REAL,
    fcf_margin REAL,
    fcf_yield REAL,
    debt_to_equity REAL,
    revenue_growth_3y REAL,
    revenue_volatility REAL,
    score INTEGER DEFAULT 0,
    max_score INTEGER DEFAULT 24,
    csu_fit TEXT,
    price REAL,
    currency TEXT DEFAULT 'USD',
    in_portfolio INTEGER DEFAULT 0,
    in_watchlist INTEGER DEFAULT 0,
    scanned_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS kill_signal_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    check_date TEXT DEFAULT (datetime('now')),
    signal_type TEXT,  -- RETENTION_DROP, FCF_COMPRESS, VOLATILITY_SPIKE, THESIS_CHANGE, MGMT_TURNOVER, OTHER
    severity TEXT DEFAULT 'WARNING',  -- OK, WARNING, CRITICAL
    details TEXT,
    action TEXT,  -- HOLD, SELL, BUY_MORE, WATCH
    current_price REAL
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    price REAL,
    captured_at TEXT DEFAULT (datetime('now'))
);
"""


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    # Migrations for existing DBs
    try:
        conn.execute("ALTER TABLE watchlist ADD COLUMN last_price REAL")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE watchlist ADD COLUMN score_breakdown TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE portfolio ADD COLUMN score_breakdown TEXT")
    except Exception:
        pass
    conn.close()


def upsert_scan(conn, data: dict):
    conn.execute("""
        INSERT INTO scan_results (ticker, name, sector, industry, market_cap_m,
            gross_margin, fcf_margin, fcf_yield, debt_to_equity,
            revenue_growth_3y, revenue_volatility, score, max_score, csu_fit,
            price, currency, in_portfolio, in_watchlist, scanned_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
            (SELECT COUNT(*) FROM portfolio WHERE ticker=?),
            (SELECT COUNT(*) FROM watchlist WHERE ticker=?),
            ?)
        ON CONFLICT(ticker) DO UPDATE SET
            name=excluded.name, sector=excluded.sector, industry=excluded.industry,
            market_cap_m=excluded.market_cap_m, gross_margin=excluded.gross_margin,
            fcf_margin=excluded.fcf_margin, fcf_yield=excluded.fcf_yield,
            debt_to_equity=excluded.debt_to_equity,
            revenue_growth_3y=excluded.revenue_growth_3y,
            revenue_volatility=excluded.revenue_volatility,
            score=excluded.score, max_score=excluded.max_score,
            csu_fit=excluded.csu_fit, price=excluded.price,
            currency=excluded.currency, in_portfolio=excluded.in_portfolio,
            in_watchlist=excluded.in_watchlist, scanned_at=excluded.scanned_at
    """, (
        data["ticker"], data.get("name", ""), data.get("sector", ""),
        data.get("industry", ""), data.get("market_cap_m"),
        data.get("gross_margin"), data.get("fcf_margin"), data.get("fcf_yield"),
        data.get("debt_to_equity"), data.get("revenue_growth_3y"),
        data.get("revenue_volatility"), data.get("total_score", 0),
        data.get("max_score", 24), data.get("csu_fit", ""),
        data.get("price"), data.get("currency", "USD"),
        data["ticker"], data["ticker"],
        datetime.now().isoformat(),
    ))


def add_to_watchlist(conn, ticker: str, name: str = "", buy_under: float = None,
                     score: int = 0, max_score: int = 24, thesis: str = "",
                     kill_signals: str = "", priority: str = "MEDIUM",
                     source: str = "", notes: str = "", sector: str = "", industry: str = ""):
    conn.execute("""
        INSERT OR REPLACE INTO watchlist 
        (ticker, name, sector, industry, buy_under, score, max_score, thesis, kill_signals, 
         priority, source, last_checked, notes, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, datetime('now'))
    """, (ticker, name, sector, industry, buy_under, score, max_score,
          thesis, kill_signals, priority, source, notes))


def add_to_portfolio(conn, ticker: str, name: str = "", buy_price: float = None,
                     buy_date: str = None, shares: float = 0, thesis: str = "",
                     kill_signals: str = "", score: int = 0, max_score: int = 24,
                     notes: str = "", sector: str = "", industry: str = ""):
    conn.execute("""
        INSERT OR REPLACE INTO portfolio
        (ticker, name, sector, industry, buy_price, buy_date, shares, thesis, kill_signals,
         status, score, max_score, notes, last_kill_check, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'HOLD', ?, ?, ?, datetime('now'), datetime('now'))
    """, (ticker, name, sector, industry, buy_price, buy_date, shares,
          thesis, kill_signals, score, max_score, notes))
    # Mark in scan_results
    conn.execute("UPDATE scan_results SET in_portfolio=1 WHERE ticker=?", (ticker,))
    conn.execute("UPDATE scan_results SET in_watchlist=0 WHERE ticker=?", (ticker,))


def log_kill_signal(conn, ticker: str, signal_type: str, severity: str,
                    details: str, action: str, current_price: float = None):
    conn.execute("""
        INSERT INTO kill_signal_log (ticker, signal_type, severity, details, action, current_price)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (ticker, signal_type, severity, details, action, current_price))


def update_portfolio_status(conn, ticker: str, status: str):
    conn.execute("UPDATE portfolio SET status=?, updated_at=datetime('now') WHERE ticker=?",
                 (status, ticker))


def add_to_position(conn, ticker: str, additional_shares: float, price_per_share: float):
    """Record an additional lot. Increments shares and recomputes weighted-average buy_price."""
    row = conn.execute("SELECT shares, buy_price FROM portfolio WHERE ticker=?", (ticker,)).fetchone()
    if not row:
        return
    cur_shares = row["shares"] or 0
    cur_price = row["buy_price"] or 0
    new_shares = cur_shares + additional_shares
    if new_shares <= 0:
        return
    if cur_shares > 0 and cur_price > 0:
        new_avg = ((cur_shares * cur_price) + (additional_shares * price_per_share)) / new_shares
    else:
        new_avg = price_per_share
    conn.execute(
        "UPDATE portfolio SET shares=?, buy_price=?, updated_at=datetime('now') WHERE ticker=?",
        (new_shares, new_avg, ticker),
    )


def update_position_cost_basis(conn, ticker: str, shares: float, buy_price: float):
    """Overwrite shares and buy_price directly (corrections / manual edits)."""
    conn.execute(
        "UPDATE portfolio SET shares=?, buy_price=?, updated_at=datetime('now') WHERE ticker=?",
        (shares, buy_price, ticker),
    )


def remove_from_watchlist(conn, ticker: str):
    conn.execute("DELETE FROM watchlist WHERE ticker=?", (ticker,))
    conn.execute("UPDATE scan_results SET in_watchlist=0 WHERE ticker=?", (ticker,))


def remove_from_portfolio(conn, ticker: str):
    conn.execute("DELETE FROM portfolio WHERE ticker=?", (ticker,))
    conn.execute("UPDATE scan_results SET in_portfolio=0 WHERE ticker=?", (ticker,))


def move_to_portfolio(conn, ticker: str, buy_price: float = None, shares: float = 0):
    row = conn.execute("SELECT * FROM watchlist WHERE ticker=?", (ticker,)).fetchone()
    if row:
        add_to_portfolio(conn, ticker, row["name"], buy_price,
                         datetime.now().strftime("%Y-%m-%d"), shares,
                         row["thesis"], row["kill_signals"],
                         row["score"], row["max_score"], row["notes"],
                         row["sector"], row["industry"])
        remove_from_watchlist(conn, ticker)


def move_to_watchlist(conn, ticker: str, buy_under: float = None):
    row = conn.execute("SELECT * FROM scan_results WHERE ticker=?", (ticker,)).fetchone()
    if row:
        add_to_watchlist(conn, ticker, row["name"], buy_under,
                         row["score"], row["max_score"], source="scan",
                         sector=row["sector"], industry=row["industry"])
        conn.execute("UPDATE scan_results SET in_watchlist=1 WHERE ticker=?", (ticker,))


# Initialize on import
init_db()
