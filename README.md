# CSU-Inspired Vertical Software Screener

Screen public markets for companies fitting the [Constellation Software](https://en.wikipedia.org/wiki/Constellation_Software) acquisition profile: vertical/niche software, high revenue retention, low % of customer costs, mission-critical, FCF-generative, unglamorous.

Based on the investment thesis from [Fuco's analysis](https://www.youtube.com/watch?v=yy4WEATDoYQ).

## Quick Start

```bash
# Clone and setup
git clone https://github.com/choutos/csu-screener.git
cd csu-screener
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run with built-in seed tickers
python screener.py

# Screen specific tickers
python screener.py --tickers CSU.TO ROP TDG VRNS

# Screen your watchlist
python screener.py --watchlist

# Export results
python screener.py --export csv
```

## The 8 KPIs

| # | KPI | What It Measures | Strong (3) | Pass (2) | Weak (1) | Fail (0) |
|---|-----|-----------------|------------|----------|----------|-----------|
| 1 | FCF Margin | Cash generation | ≥20% | 10-20% | 5-10% | <5% |
| 2 | Gross Margin | Software economics | ≥70% | 50-70% | 30-50% | <30% |
| 3 | Revenue Stability | Retention proxy (volatility) | ≤10% | 10-20% | 20-30% | >30% |
| 4 | Growth Profile | Durability, not speed | 2-15% CAGR | 0-2% | 15-30% | >30% or <-5% |
| 5 | FCF Yield | Valuation discipline | ≥5% | 3-5% | 2-3% | <2% |
| 6 | Debt Discipline | Capital structure | D/E ≤0.5 | 0.5-1.0 | 1.0-2.0 | >2.0 |
| 7 | Size Fit | Mid-cap sweet spot | $500M-10B | $200-500M / $10-30B | >$30B | <$200M |
| 8 | Industry Fit | Vertical/niche | Direct vertical | Adjacent tech | Horizontal | Not tech |

**Scoring:** Each KPI 0-3. Total ≥18 with ≥6 passes = 🟢 STRONG fit.

## Directory Structure

```
csu-screener/
├── screener.py              # Main screener script
├── requirements.txt         # Python dependencies
├── watchlist.json           # Your tracked tickers
├── data/
│   ├── screener-database.csv  # Persistent results
│   └── results/               # Exported snapshots
├── company-cards/            # Per-company deep analyses
├── sector-deep-dives/         # Per-sector analysis
├── quarterly-letters/         # Your quarterly reviews
├── scoring-template.md        # Full KPI details + qualitative add-ons
├── sector-guide.md            # How to pick your sectors
├── process-implementation.md  # The full investment process
├── rejection-log.md           # Companies you passed on
└── README.md                  # This file
```

## Usage

### Screening

```bash
# Built-in seed tickers (18 CSU-like companies)
python screener.py --seed

# Your custom watchlist (edit watchlist.json)
python screener.py --watchlist

# Specific tickers
python screener.py --tickers CSU.TO TOP.BR ROP

# Filter by sector after screening
python screener.py --sector Technology

# Export results
python screener.py --export csv
python screener.py --export json

# Skip saving to database
python screener.py --no-save
```

### Watchlist Format

Edit `watchlist.json`:

```json
{
  "CSU.TO": "Constellation Software",
  "ROP": "Roper Technologies",
  "YOUR-TICKER": "Company Name"
}
```

## The Investment Process

### Weekly
1. Run screener on watchlist → update database
2. Review any new STRONG/MODERATE fits
3. Add 1-2 new tickers from discovery sources

### Monthly
1. Deep-dive one company (fill out a company card)
2. Review scoring template — any criteria need adjusting?
3. Check positions against kill signals

### Quarterly ("Universities")
1. Review all past analyses — what patterns emerged?
2. Update scoring weights if needed
3. Write a "quarterly letter" summarizing learnings
4. Purge watchlist of stale entries

### Annually
1. Full portfolio review against process
2. Compare actual outcomes vs. initial scores (calibration)
3. Update process documentation

## Kill Signals (When to Sell)

1. Gross retention drops below 90%
2. FCF margin compresses >5pp
3. Revenue volatility spikes
4. Acquisition spree into unfamiliar verticals
5. Key operational management turnover
6. The thesis premise fundamentally changes

**Price decline is NOT a kill signal. Thesis change IS.**

## Discovery Sources

The screener catches *financial* fits. Qualitative discovery also needs:

- **13F filings** — concentrated, value-oriented fund holdings
- **CSU's own acquisitions** — each one reveals a niche; find public competitors
- **Industry conferences** — vertical software events
- **PE activity** — when PE buys vertical software, look at public peers
- **Substack/newsletters** — Outsider Trader, etc.
- **Your own industry** — what software does YOUR industry use?

## License

Private repository. Personal use only.
