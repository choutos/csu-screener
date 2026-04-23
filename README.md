# Investment Process App

Three-dashboard investment tracking app built with Streamlit + SQLite.

## Quick Start

```bash
cd ~/clawd/invest-app
source ~/clawd/.venvs/screener/bin/activate
streamlit run app.py
```

## Dashboards

### 📊 Portfolio
- Track positions with buy price, shares, thesis, kill signals
- Status: HOLD / SELL / BUY MORE
- Log kill signal checks over time
- View kill signal history per position

### 👀 Watchlist
- Track companies with "buy under" target prices
- Priority levels (HIGH / MEDIUM / LOW)
- Quick refresh data, move to portfolio when buying
- Thesis and kill signals stored for each entry

### 🔍 Scanner
- Quick scan any tickers via Yahoo Finance
- Broader than CSU — any sector with durable competitive advantages
- 8-KPI quality scoring (not just software)
- Filter results, move to watchlist or portfolio

## Architecture

- **app.py** — Streamlit UI (3 dashboards + settings)
- **db.py** — SQLite database layer (5 tables)
- **fetcher.py** — Yahoo Finance fetcher + scoring engine

### Database Tables
- `portfolio` — Current holdings
- `watchlist` — Tracked companies
- `scan_results` — Screener results cache
- `kill_signal_log` — Audit trail of kill signal checks
- `price_snapshots` — Historical price data

## The Investment Process

### Weekly
1. Scanner: scan 5-10 new tickers
2. Watchlist: refresh data on existing entries
3. Review any new STRONG/MODERATE fits

### Monthly
1. Portfolio: run kill signal checks on all positions
2. Deep-dive one company from watchlist
3. Update buy-under prices if thesis changes

### Quarterly ("Universities")
1. Review all kill signal logs
2. Update scoring weights
3. Write quarterly letter
4. Purge watchlist of stale entries
