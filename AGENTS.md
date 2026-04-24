# AGENTS.md — CSU Screener

Project guidance for coding agents working on this codebase.

## What This Is

A Streamlit-based investment process app for tracking quality compounder stocks. Think of it as a structured workflow: **Scan → Watch → Buy → Monitor → Sell**, powered by yfinance data and an LLM advisor.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  app.py  — thin Streamlit entrypoint / router        │
│  page config, sidebar, dispatch to pages/*           │
├──────────────────────────────────────────────────────┤
│  pages/                                              │
│  portfolio.py | watchlist.py | discovery.py | settings.py │
│  helpers.py — shared DB singleton + UI helpers       │
└────┬───────────────────────┬───────────────────────┬─┘
     │                       │                       │
┌────▼───────┐      ┌────────▼────────┐     ┌────────▼────────┐
│ db.py      │      │ smart_fetcher.py│     │ llm_advisor.py  │
│ SQLite     │      │ data access     │     │ LLM integration │
└────┬───────┘      └────────┬────────┘     └─────────────────┘
     │                       │
┌────▼───────────────────────▼───────────────┐
│ fetcher.py — scoring engine                │
└────────────────────────────────────────────┘
```

**Data flow:** `smart_fetcher` → `fetcher` (scoring) → `db` (persistence) → `pages/*` → `app`
**LLM flow:** `llm_advisor` wraps any OpenAI-compatible API (ollama, litellm proxy)

## Files

| File | Purpose | Key Functions |
|------|---------|---------------|
| `app.py` | Thin Streamlit entrypoint and router | sidebar selection + page dispatch |
| `pages/portfolio.py` | Portfolio dashboard UI | `render()` |
| `pages/watchlist.py` | Watchlist dashboard UI | `render()` |
| `pages/discovery.py` | Discovery dashboard UI | `render()` |
| `pages/settings.py` | Settings dashboard UI | `render()` |
| `pages/helpers.py` | Shared page helpers | `get_shared_db()`, `render_score_breakdown()` |
| `db.py` | SQLite CRUD + migrations | `get_db()`, `init_db()`, `upsert_scan()`, `add_to_watchlist()`, `add_to_portfolio()`, `move_to_portfolio()`, `move_to_watchlist()`, `log_kill_signal()`, `update_portfolio_status()` |
| `fetcher.py` | Data fetching + scoring | `fetch_company()` → raw data, `score_company()` → scored data with KPI breakdown |
| `smart_fetcher.py` | yfinance/IBKR abstraction | `smart_fetch()`, `fetch_company()`, `fetch_companies_batch()`, `calculate_buy_under()` |
| `discovery.py` | Batch screening engine across indices | `refresh_index_cache()`, `refresh_etf_holdings()`, `run_discovery()` |
| `llm_advisor.py` | LLM-powered analysis | `generate_analysis()`, `check_portfolio_health()`, `test_connection()`, `load_config()`, `save_config()` |
| `kill_signal_scanner.py` | Standalone scanner (batch kill signals) | Batch kill signal checks across portfolio |

## Database

SQLite at `invest.db`, managed via `db.py`.

**Tables:** `portfolio`, `watchlist`, `scan_results`, `kill_signal_log`, `price_snapshots`

**Migrations:** `init_db()` runs `ALTER TABLE` migrations on app startup. Add new columns as `try/except` blocks — SQLite doesn't support `ADD COLUMN IF NOT EXISTS`.

**Connection:** `pages/helpers.py` exposes the `@st.cache_resource` singleton via `get_shared_db()`. `db.py`'s `get_db()` is the non-cached low-level connector.

**Critical:** Always call `conn.commit()` after any INSERT/UPDATE/DELETE. The most common bug in this codebase is forgetting this.

## Scoring System

`score_company()` in `fetcher.py` evaluates 8 KPIs, each scored 0-3 (max 24):

| KPI | Key | Pass Threshold | Top Score |
|-----|-----|---------------|-----------|
| FCF Margin | `fcf_margin` | ≥10% | ≥20% → 3 |
| Gross Margin | `gross_margin` | ≥40% | ≥70% → 3 |
| Revenue Stability | `revenue_stability` | ≤25% vol | ≤10% → 3 |
| Growth Profile | `growth_profile` | −5% to 25% | 2-15% → 3 |
| FCF Yield | `fcf_yield` | ≥2% | ≥5% → 3 |
| Debt Discipline | `debt_discipline` | D/E ≤2.0 | ≤0.5 → 3 |
| Size Fit | `size_fit` | ≥$200M | $500M-$10B → 3 |
| Moat Quality | `moat_quality` | ≥40% GM or industrial | ≥60% GM → 3 |

**Important:** When yfinance returns `None` for a metric, that KPI is **skipped entirely** — the key won't exist in `scores` or `passes`. Always use `.get(key)` and handle `None` (missing data), not just `0` or `False`.

**Fit levels:** STRONG (≥18 + ≥6 passes), MODERATE (≥12 + ≥4 passes), WEAK (≥8), NOT FIT (<8)

## UI Buttons & Actions

| Button | Where | What It Does |
|--------|-------|-------------|
| 🔄 Refresh | Watchlist | Fetches fresh data from yfinance, re-scores, updates `last_price` + `score` + `score_breakdown` |
| 🔄 Refresh All Prices | Watchlist top | Bulk version of Refresh for all watchlist entries |
| 🧠 Analyze | Watchlist | Calls LLM to generate thesis/kill signals/buy-under. Does NOT update score |
| 📈 Buy → | Watchlist | Two-step inline form: shows buy price (pre-filled) + shares input, then moves to Portfolio |
| 🗑️ Remove | Watchlist/Portfolio | Removes from table |
| 🩺 Health Check | Portfolio | Fetches fresh data, re-scores, calls LLM to evaluate thesis validity. Updates score + status. Auto-sets WATCH if recommended |
| 👀 Watch | Discovery | Adds to Watchlist with auto-LLM analysis |

## LLM Advisor

Config stored in `llm_config.json`, editable via Settings page.

**Default:** ollama at `http://localhost:11434/v1`, model `glm-5.1:cloud`

**`generate_analysis()` returns:** `{thesis, kill_signals, buy_under, buy_under_reasoning}`
**`check_portfolio_health()` returns:** `{thesis_status, thesis_assessment, kill_signals_triggered, new_risks, overall_action, confidence, summary}`

**JSON parsing:** Uses brace-depth tracker (not regex) to find outermost JSON object. LLM responses often contain nested JSON arrays (`kill_signals_triggered: [{...}]`) which breaks `\{[^{}]*\}` regex.

**Prompt engineering:** LLMs tend to be verbose → response exceeds `max_tokens` → truncated mid-JSON → parse failure. Always constrain output explicitly in prompts ("max 2 short sentences", "max 3 items per array"). `max_tokens=3000` for health checks.

## Known Gotchas (Read This First)

### Streamlit
- **`st.rerun()` destroys all local variables.** Persist anything needed across reruns in `st.session_state`.
- **Buttons inside `st.form` don't trigger callbacks.** Use standalone `st.button()` for actions.
- **Each widget needs a unique `key`.** Use `key=f"name_{row['ticker']}"` pattern.
- **Streamlit reruns the entire script on every interaction.** Expensive operations must be cached or guarded with `st.session_state` flags.

### SQLite
- **Always `conn.commit()` after writes.** Forgetting this is the #1 bug.
- **Single-element tuples need trailing comma:** `(value,)` not `(value)`. Without it, Python treats parens as grouping, not a tuple → SQLite iterates string characters.
- **`@st.cache_resource`** lives in `pages/helpers.py` via `get_shared_db()` — use that single shared connection across all reruns.
- **`check_same_thread=False`** required because Streamlit reruns happen in different threads.
- **WAL mode** enabled for concurrent read/write.

### yfinance / Data
- **IBKR is opt-in** via `CSU_USE_IBKR=1` env var. Without paid subscriptions, IBKR returns error 10358/10089.
- **`None` values from yfinance are common** — especially `fcf_margin`, `fcf_yield`, `revenue_volatility` for non-US stocks. Always handle missing data.
- **`debt_to_equity` from yfinance** is sometimes absurdly high (e.g., 243 for CPAY) — it's total debt / total equity, and negative equity inflates it.

### LLM
- **`max_tokens` too low** → truncated JSON → parse failure. Use 2000+ for complex nested responses.
- **JSON regex doesn't work** for nested objects. Use the brace-depth tracker pattern from `llm_advisor.py`.
- **`score_company()` keys may be absent** when data is `None`. Always use `.get()` with `None` handling.

## Adding a New Feature

1. **New DB column?** Add `ALTER TABLE` in `init_db()` inside a `try/except` block.
2. **New button?** Use unique `key=f"btn_{ticker}"` pattern. Guard action with `st.session_state` flag if it triggers a rerun.
3. **New LLM prompt?** Keep output format explicit and constrained. Add `max_tokens` parameter generously.
4. **New dashboard section?** If it is top-level, add it to the sidebar radio in `app.py`; otherwise place it in the relevant `pages/*.py` module. For Discovery changes, decide whether they belong in the Manual Scan tab, the Index Discovery tab, or the shared results area.
5. **Always check imports.** Missing `import os`, `import json`, `from pathlib import Path` are a recurring bug.
6. **Always test with `python3 -c "import ast; ast.parse(open('app.py').read())"`** before pushing.

## Deployment

The app runs on a different machine than the dev machine.

1. Push to `main` on GitHub
2. Vítor runs `git pull` + restarts Streamlit
3. DB migrations auto-run on startup via `init_db()`

No CI/CD, no Docker, no automated deploys. Manual only.
