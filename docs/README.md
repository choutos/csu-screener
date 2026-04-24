# CSU Screener — Documentation

## Overview

CSU Screener is an investment research tool for finding, scoring, and monitoring **quality compounders** — companies with durable competitive advantages, high retention, and strong cash generation.

The framework is inspired by **Compound Stock Theory (CSU)**: look for low customer cost concentration, high switching costs, recurring revenue, and mission-critical products.

## Documentation

| File | Description |
|------|-------------|
| [framework.md](framework.md) | Core investment thesis, philosophy, and what makes a compounder |
| [scoring.md](scoring.md) | The 8-KPI scoring system, fit classification, and thresholds |
| [valuation.md](valuation.md) | Reverse DCF methodology and buy-under price calculation |
| [health-checks.md](health-checks.md) | Kill signals, thesis monitoring, and portfolio health checks |
| [discovery.md](discovery.md) | Discovery presets, index/ETF sources, and scanning workflow |
| [architecture.md](architecture.md) | App architecture, file reference, database schema |

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app has four pages:

- **📊 Portfolio** — Track positions with thesis, kill signals, and health checks
- **👀 Watchlist** — Monitor candidates with score breakdowns and buy-under prices
- **🧭 Discovery** — Find new candidates via manual scan or batch index/ETF screening
- **⚙️ Settings** — Database stats, LLM advisor config, bulk import

## The Archetype

If you had to name one company that embodies the framework: **JKHY (Jack Henry & Associates)**. 99%+ retention, regulatory moat (banking software), mid-cap, high FCF margins, steady growth, customers that *can't* leave.

Every other candidate is measured against this standard.
