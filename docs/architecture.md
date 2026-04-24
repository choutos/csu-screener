# Architecture

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | Streamlit |
| Data source | yfinance (default), IBKR Gateway (optional) |
| Database | SQLite (WAL mode) |
| LLM advisor | OpenAI-compatible API (ollama, litellm, etc.) |
| Language | Python 3.9+ |

## File Reference

```
csu-screener/
├── app.py                  # Streamlit UI — all pages
├── fetcher.py              # Data fetching + scoring logic
├── smart_fetcher.py        # Smart data fetching (IBKR/yfinance) + buy-under calc
├── discovery.py            # Index/ETF sources, presets, batch scanning
├── llm_advisor.py          # LLM-powered thesis, kill signals, health checks
├── db.py                   # SQLite schema, migrations, connection management
├── llm_config.json         # LLM provider/model/API key config
├── requirements.txt        # Python dependencies
├── AGENTS.md               # AI agent guidance (coding conventions, gotchas)
├── README.md               # Project overview + setup instructions
└── docs/
    ├── README.md            # This documentation index
    ├── framework.md         # CSU compounder framework
    ├── scoring.md           # 8-KPI scoring system
    ├── valuation.md         # Reverse DCF + buy-under methodology
    ├── health-checks.md     # Kill signals & portfolio health
    ├── discovery.md         # Scanning presets & index sources
    └── architecture.md      # This file
```

## Database Schema

### `portfolio`

| Column | Type | Description |
|--------|------|-------------|
| `ticker` | TEXT PK | Stock ticker |
| `name` | TEXT | Company name |
| `sector` | TEXT | Business sector |
| `industry` | TEXT | Business industry |
| `buy_price` | REAL | Purchase price |
| `buy_date` | TEXT | Purchase date |
| `shares` | REAL | Number of shares |
| `thesis` | TEXT | Investment thesis (LLM-generated or manual) |
| `kill_signals` | TEXT | Pre-defined sell triggers |
| `status` | TEXT | HOLD / WATCH / SELL / SOLD |
| `notes` | TEXT | Free-form notes |
| `last_kill_check` | TEXT | Date of last health check |
| `score` | INTEGER | Current total score (from health check) |
| `max_score` | INTEGER | Maximum possible score |
| `score_breakdown` | TEXT | JSON: per-KPI scores and pass/fail |
| `created_at` | TEXT | Record creation timestamp |
| `updated_at` | TEXT | Last update timestamp |

### `watchlist`

| Column | Type | Description |
|--------|------|-------------|
| `ticker` | TEXT PK | Stock ticker |
| `name` | TEXT | Company name |
| `buy_under` | REAL | Maximum buy price |
| `priority` | TEXT | HIGH / MEDIUM / LOW |
| `source` | TEXT | How the ticker was discovered |
| `sector` | TEXT | Business sector |
| `industry` | TEXT | Business industry |
| `thesis` | TEXT | Investment thesis |
| `kill_signals` | TEXT | Pre-defined sell triggers |
| `score` | INTEGER | Total quality score |
| `max_score` | INTEGER | Maximum possible score |
| `score_breakdown` | TEXT | JSON: per-KPI scores and pass/fail |
| `created_at` | TEXT | Record creation timestamp |
| `updated_at` | TEXT | Last update timestamp |

### `scan_results`

| Column | Type | Description |
|--------|------|-------------|
| `ticker` | TEXT PK | Stock ticker |
| `name` | TEXT | Company name |
| `sector` | TEXT | Business sector |
| `industry` | TEXT | Business industry |
| `score` | INTEGER | Total quality score |
| `max_score` | INTEGER | Maximum possible score |
| `csu_fit` | TEXT | STRONG / MODERATE / WEAK / NOT FIT |
| `price` | REAL | Last known price |
| `fcf_yield` | REAL | Free cash flow yield |
| `gross_margin` | REAL | Gross margin |
| `in_portfolio` | INTEGER | 1 if also in portfolio table |
| `in_watchlist` | INTEGER | 1 if also in watchlist table |
| `scanned_at` | TEXT | When last scanned |

### `kill_signal_log`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `ticker` | TEXT | Stock ticker |
| `check_date` | TEXT | ISO datetime of check |
| `signal_type` | TEXT | Which signal was evaluated |
| `severity` | TEXT | OK / WARNING / CRITICAL |
| `details` | TEXT | What was found |
| `action` | TEXT | HOLD / SELL / BUY_MORE / WATCH |
| `current_price` | REAL | Price at time of check |

### `price_snapshots`

| Column | Type | Description |
|--------|------|-------------|
| `ticker` | TEXT | Stock ticker |
| `price` | REAL | Snapshot price |
| `date` | TEXT | Snapshot date |

## Key Functions

| Function | File | Purpose |
|----------|------|---------|
| `fetch_company()` | `fetcher.py` | Fetch raw financial data from yfinance |
| `score_company()` | `fetcher.py` | Score a company against 8 KPIs |
| `smart_fetch()` | `smart_fetcher.py` | Fetch via IBKR or yfinance with fallback |
| `calculate_buy_under()` | `smart_fetcher.py` | Reverse DCF valuation |
| `run_discovery()` | `discovery.py` | Batch scan across indexes/ETFs |
| `generate_analysis()` | `llm_advisor.py` | LLM thesis + kill signals + buy-under |
| `check_thesis()` | `llm_advisor.py` | Evaluate thesis validity + signal triggers |
| `check_portfolio_health()` | `llm_advisor.py` | Portfolio-wide health check |
| `init_db()` | `db.py` | Create tables + run migrations |
| `load_config()` / `save_config()` | `llm_advisor.py` | LLM provider config management |

## Data Flow

```
User Input (ticker / preset / manual)
        │
        ▼
   smart_fetch()  ──── IBKR Gateway (if CSU_USE_IBKR=1)
        │                  │
        │                  ▼ (fallback)
        │              yfinance API
        │
        ▼
   score_company()  ──── 8 KPI scores + fit classification
        │
        ├──► scan_results table
        ├──► watchlist table (if "Add to Watchlist")
        ├──► portfolio table (if "Add to Portfolio")
        │
        ▼ (if LLM enabled)
   generate_analysis()  ──── thesis + kill_signals + buy_under
        │
        ▼
   watchlist/portfolio updated with analysis
```

## LLM Configuration

The LLM advisor is configured via `llm_config.json` (auto-created on first run):

```json
{
  "provider": "ollama",
  "base_url": "http://localhost:11434/v1",
  "model": "glm-5.1:cloud",
  "api_key": "",
  "enabled": true
}
```

### Supported Providers

| Provider | Base URL | Notes |
|----------|----------|-------|
| `ollama` | `http://localhost:11434/v1` | Local, free |
| `litellm` | Custom | Cloud proxy (GLM-5.1, Kimi 2.6) |
| `openai` | `https://api.openai.com/v1` | Requires API key |
| `custom` | Custom | Any OpenAI-compatible endpoint |

### LLM System Prompt

The LLM is instructed to act as "an investment analyst specializing in quality compounders" with the CSU framework. It must respond only in valid JSON. Responses are parsed with a brace-depth tracker (not regex) to handle nested JSON structures.

## Known Gotchas

### Streamlit
- `st.rerun()` destroys local variables — persist in `st.session_state`
- Widget keys must be globally unique across the app
- `@st.cache_resource` for DB singleton (not `@st.cache_data`)

### SQLite
- `check_same_thread=False` for Streamlit (multi-threaded)
- WAL mode for concurrent reads
- `timeout=30` + `PRAGMA busy_timeout=30000` to avoid "database is locked"
- Migrations run automatically on startup via `init_db()`

### yfinance
- FCF data keys vary by ticker — always check for `None`
- Rate limiting on batch requests — add small delays between fetches
- European tickers may have `.L`, `.PA`, `.DE` suffixes

### LLM
- `max_tokens` should be 3000+ for nested JSON responses
- JSON parsers need brace-depth tracking, not regex
- LLM ignores brevity constraints — constrain sentence/word counts explicitly
- Buy-under from LLM is sanity-checked against current price (±50%)

## Deployment

```bash
# On the server
cd /path/to/csu-screener
git pull
# Restart Streamlit (Ctrl+C and re-run)
streamlit run app.py
```

No build step. No Docker. Just Python + pip + git.
