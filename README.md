# CSU Screener — Investment Process App

A self-hosted investment tracking and screening tool built with Streamlit + SQLite. Designed for a disciplined, thesis-driven investment process focused on quality compounders and deep value opportunities.

## Quick Start

```bash
# Clone and set up
git clone https://github.com/choutos/csu-screener.git
cd csu-screener
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

The app opens at `http://localhost:8501` by default.

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  app.py  —  Streamlit UI (4 pages + sidebar)        │
│  Uses @st.cache_resource DB singleton               │
├────────────┬────────────┬────────────────┬──────────┤
│ Portfolio  │ Watchlist  │ Discovery      │ Settings │
│            │            │ (Manual + Index)          │
└────┬───────┴──────┬─────┴───────┬────────┴─────┬────┘
     │              │             │              │
┌────▼──────────────▼─────────────▼──────────────▼────┐
│  db.py  —  SQLite layer (5 tables, WAL mode)        │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│  Data Sources                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │smart_fetcher │  │  discovery   │  │ fetcher    │ │
│  │(yfinance +   │  │ (FMP API +   │  │(yfinance + │ │
│  │ IBKR fallback)│  │ Wikipedia +  │  │ scoring)   │ │
│  │              │  │ ETF holdings) │  │            │ │
│  └──────────────┘  └──────────────┘  └────────────┘ │
└──────────────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│  llm_advisor.py  —  LLM-powered analysis            │
│  (ollama / any OpenAI-compatible API)               │
└──────────────────────────────────────────────────────┘
```

## File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `app.py` | ~940 | Streamlit UI — 4 dashboards, sidebar navigation, manual scan merged into Discovery |
| `db.py` | ~220 | SQLite database layer — schema, CRUD, migrations |
| `fetcher.py` | ~173 | Yahoo Finance fetcher + 8-KPI quality scoring engine |
| `smart_fetcher.py` | ~452 | Dual-source fetcher (yfinance default, IBKR opt-in), batch fetch, buy-under calculator |
| `discovery.py` | ~421 | Market discovery — index/ETF screening, FMP API, preset scans |
| `llm_advisor.py` | ~387 | LLM integration — thesis generation, health checks, config |
| `kill_signal_scanner.py` | ~360 | Standalone kill signal scanner (CLI/Telegram), baseline tracking |

## The 4 Dashboards

### 📊 Portfolio
Track current holdings. Each position has:
- Buy price, date, shares, sector/industry
- Investment thesis (free text)
- Kill signals (what would make you sell)
- Status: HOLD / SELL / BUY MORE
- **🩺 Health Check** — LLM evaluates your thesis against current metrics, checks if kill signals are triggered, recommends action
- Kill signal history log (auditable trail)

### 👀 Watchlist
Companies you're tracking but haven't bought yet. Each entry has:
- Buy-under price (max price you'd pay)
- Priority (HIGH / MEDIUM / LOW)
- Score from last scan
- **🧠 Analyze** — LLM generates thesis, kill signals, and buy-under price
- **📈 Buy →** — Two-step inline form to move to Portfolio (pre-fills buy price from last price)
- **🔄 Refresh** — Update price and metrics from data source

### 🧭 Discovery
Batch screening and manual ticker scans in one place. Features:
- **Two tabs:** **✏️ Manual Scan** for ad-hoc ticker checks and **🧭 Index Discovery** for batch screening
- **Previous Scan Results** expander above the tabs for reviewing cached results regardless of active mode
- **10 presets** (quality_compounders, deep_value, wide_moat, small_cap_quality, europe_quality, europe_small_cap, canada_quality, canada_small_cap, asia_pacific, full_universe)
- **17 index sources** spanning the US, Europe, Canada, and Asia-Pacific (S&P 500/400/600, FTSE 100/250, DAX, MDAX, CAC, AEX, IBEX, FTSE MIB, SMI, OMX, Nikkei, ASX, TSX 60, TSX Composite)
- **18 ETF sources** including Canadian ETFs
- FMP API key for enhanced screening (optional, works without)
- Auto-analyzes and generates thesis when adding to watchlist

### ⚙️ Settings
- LLM Advisor configuration (provider, base URL, model, API key)
- Connection test for LLM
- Data source indicator (yfinance / IBKR)

## Database Schema

SQLite with WAL mode. Auto-migrates on app startup via `init_db()`.

### `portfolio` — Current Holdings
| Column | Type | Notes |
|--------|------|-------|
| ticker | TEXT PK | Stock symbol |
| name | TEXT | Company name |
| sector / industry | TEXT | Classification |
| buy_price | REAL | Entry price |
| buy_date | TEXT | ISO date |
| shares | REAL | Position size |
| thesis | TEXT | Investment thesis |
| kill_signals | TEXT | What would make you sell |
| status | TEXT | HOLD / SELL / BUY_MORE |
| last_kill_check | TEXT | Last health check timestamp |
| score / max_score | INTEGER | Quality score (0–24) |

### `watchlist` — Tracked Companies
| Column | Type | Notes |
|--------|------|-------|
| ticker | TEXT PK | Stock symbol |
| buy_under | REAL | Max price to pay |
| priority | TEXT | HIGH / MEDIUM / LOW |
| last_price | REAL | Last fetched price |
| last_checked | TEXT | Last data refresh |
| thesis / kill_signals | TEXT | From LLM or manual |

### `scan_results` — Screener Cache
Stores the latest scan metrics per ticker. Updated on each scan/refresh.

### `kill_signal_log` — Audit Trail
| Column | Type | Notes |
|--------|------|-------|
| signal_type | TEXT | RETENTION_DROP, FCF_COMPRESS, VOLATILITY_SPIKE, THESIS_CHANGE, MGMT_TURNOVER, OTHER |
| severity | TEXT | OK / WARNING / CRITICAL |
| action | TEXT | HOLD / SELL / BUY_MORE / WATCH |

### `price_snapshots` — Historical Prices
Time-series price data for charting and analysis.

## Data Sources

### yfinance (default)
- Free, no API key needed
- Fetches price, margins, growth, debt, market cap
- Works for US, European, and Asian tickers
- Sometimes slow or missing data for small-caps

### IBKR (opt-in)
- Set `CSU_USE_IBKR=1` environment variable to enable
- Requires IB Gateway or TWS running
- Better real-time data and fundamentals **with paid subscriptions**
- Without paid subs: returns errors 10358 (no fundamentals) and 10089 (no market data)
- Fallback to yfinance is automatic

### FMP API (optional)
- Used by Discovery for enhanced screening
- API key stored in `fmp_api_key.txt` (gitignored)
- Works without it (falls back to Wikipedia + yfinance)

## LLM Advisor

The app can use any OpenAI-compatible LLM API to:
1. **Generate investment theses** — analyzes company metrics, writes thesis + kill signals + buy-under
2. **Portfolio health checks** — evaluates whether your thesis is still valid, checks kill signals

### Configuration
Stored in `llm_config.json` (auto-created on first use):
```json
{
  "provider": "ollama",
  "base_url": "http://localhost:11434/v1",
  "model": "glm-5.1:cloud",
  "api_key": "",
  "enabled": true
}
```

**Works with:**
- [ollama](https://ollama.ai) — local inference (default)
- [LiteLLM Proxy](https://github.com/BerriAI/litellm) — cloud model routing
- Any OpenAI-compatible API (OpenAI, Together, Fireworks, etc.)

Just change `base_url`, `model`, and `api_key` in Settings.

## Quality Scoring (0–24)

8 KPIs, each scored 0–3:

| KPI | 3 pts | 2 pts | 1 pt | Pass threshold |
|-----|-------|-------|------|----------------|
| FCF Margin | ≥20% | ≥10% | ≥5% | ≥10% |
| Gross Margin | ≥70% | ≥50% | ≥30% | ≥40% |
| Revenue Stability | ≤10% vol | ≤20% | ≤30% | ≤25% |
| Growth Profile | 2–15% | ≤2% | ≤25% | -5% to 25% |
| FCF Yield | ≥5% | ≥3% | ≥2% | ≥2% |
| Debt Discipline | ≤0.5 D/E | ≤1.0 | ≤2.0 | ≤2.0 |
| Size Fit | $500M–$10B | $200–500M or $10–50B | other | ≥$200M |
| Moat Quality | ≥60% GM | ≥40% GM | sector-aware | ≥40% GM or capital-intensive |

**Score tiers:**
- **MODERATE FIT**: 5–7 passes, score 14–18
- **STRONG FIT**: 8 passes, score 18–24

## The Investment Process

### Weekly
1. 🧭 Discovery: run a preset scan
2. 👀 Watchlist: refresh prices, review new entries
3. ✏️ Discovery → Manual Scan: deep-dive 2–3 interesting tickers

### Monthly
1. 📊 Portfolio: run 🩺 Health Check on all positions
2. Review triggered kill signals
3. Update buy-under prices if thesis changes

### Quarterly ("Universities")
1. Review full kill signal log
2. Update scoring weights if needed
3. Purge stale watchlist entries
4. Write quarterly review

## Development Notes

### Adding or Changing a Dashboard Section
1. Update the sidebar options in the `# ─── Sidebar` section of `app.py`
2. Add or edit the relevant rendering block in `app.py` (the UI is still a single-file script)
3. If the change belongs in Discovery, decide whether it fits **✏️ Manual Scan**, **🧭 Index Discovery**, or the shared **Previous Scan Results** area
4. Use `conn = _get_shared_db()` (the `@st.cache_resource` singleton) — never call `get_db()` directly

### Streamlit Gotchas
- **`st.rerun()` destroys all local variables** — persist data in `st.session_state` if it needs to survive
- **Use `@st.cache_resource` for the DB connection** — creating new connections per rerun causes "database is locked" errors
- **Single-element tuples need a trailing comma** — `(val,)` not `(val)` or SQLite sees N bindings instead of 1
- **Always `conn.commit()` after writes** — SQLite doesn't auto-commit

### LLM Response Parsing
- The parser uses a brace-depth tracker to find the outermost JSON object
- Handles nested objects (e.g., `kill_signals_triggered: [{...}]`)
- If JSON parse fails, shows raw LLM output in the summary field for debugging
- `max_tokens` must be generous (3000+) — complex JSON gets cut off mid-response

### Database Migrations
- Add new columns to the `SCHEMA` string in `db.py`
- Add migration logic in `init_db()` after `conn.executescript(SCHEMA)`
- Migrations run automatically on app startup

### IBKR Integration
- Lives in `smart_fetcher.py` — dual-fetcher pattern
- `_should_try_ibkr()` checks env var + availability
- `_fetch_from_ibkr()` handles async IB API via `ib_insync`
- `_fetch_from_yfinance()` is the reliable fallback
- `fetch_company()` tries IBKR first (if enabled), falls back to yfinance

## Tech Stack

- **Frontend**: Streamlit (Python)
- **Database**: SQLite (WAL mode)
- **Data**: yfinance, FMP API, IBKR (optional)
- **LLM**: OpenAI-compatible API (ollama, LiteLLM, etc.)
- **Language**: Python 3.12+
