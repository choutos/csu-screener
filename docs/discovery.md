# Discovery & Scanning

## Overview

The Discovery page finds new investment candidates by scanning indexes, ETFs, or individual tickers against the CSU framework. It has two modes:

- **✏️ Manual Scan** — Enter comma-separated tickers for quick evaluation
- **🧭 Index Discovery** — Batch scan across 16 indexes and 14 ETFs with preset filters

Both modes write results to the `scan_results` table, which feeds the "📋 Previous Scan Results" section at the top of the page.

## Discovery Presets

| Preset | Universe | Min FCF Margin | Min GM | Min MCap | Description |
|--------|----------|----------------|--------|----------|-------------|
| 🏛️ Quality Compounders | S&P 500 + 400 | 10% | 40% | $500M | High FCF, stable, durable businesses |
| 💰 Deep Value | S&P 400 + 600 | 8% | 30% | $200M | Cheap on FCF yield, profitable |
| 🏰 Wide Moat | S&P 500 | 15% | 60% | $1B | High margins, dominant businesses |
| 🔭 Small Cap Quality | S&P 600 + 400 + IWM + SCZ | 8% | 35% | $200M | Quality under the radar |
| 🇪🇺 Europe Quality | FTSE + DAX + CAC + IBEX + MIB + AEX + SMI | 8% | 35% | $300M | European quality compounders |
| 🇪🇺 Europe Small Cap | FTSE 250 + MDAX + country ETFs | 5% | 25% | $100M | European small/mid caps with quality |
| 🌏 Asia-Pacific | Nikkei 225 + ASX 200 | 6% | 30% | $300M | Japan and Australia |
| 🍁 Canada Quality | TSX 60 + Composite + XIC + EWC | 8% | 35% | $300M | Canadian compounders (banks, rails, tech) |
| 🍁 Canada Small Cap | Composite + XMD + XCS + EWC | 5% | 25% | $100M | Canadian small/mid caps |
| 🌍 Full Universe | All indexes | 5% | 25% | $100M | Everything (slow!) |

### Preset Design Rationale

- **Quality Compounders** is the default — the strictest filters, the best companies
- **Deep Value** relaxes margin requirements to find companies that are cheap on cash flow
- **Wide Moat** is the most exclusive — only high-margin, large-cap businesses
- **Small Cap Quality** targets the mid-cap sweet spot ($200M–$10B) where compounders hide
- **Europe** presets have relaxed thresholds because European companies tend to have lower reported margins (different accounting standards, more conservative management)
- **Asia-Pacific** similarly relaxed — Japanese companies in particular tend to have lower margins but strong balance sheets

## Index Sources

### US Indexes (Wikipedia)

| Key | Index | Cap Range |
|-----|-------|-----------|
| `sp500` | S&P 500 | Large cap |
| `sp400` | S&P 400 | Mid cap |
| `sp600` | S&P 600 | Small cap |

### European Indexes (Wikipedia)

| Key | Index | Country |
|-----|-------|---------|
| `ftse100` | FTSE 100 | UK |
| `ftse250` | FTSE 250 | UK (mid) |
| `dax40` | DAX 40 | Germany |
| `mdax` | MDAX | Germany (mid) |
| `cac40` | CAC 40 | France |
| `aex25` | AEX 25 | Netherlands |
| `ibex35` | IBEX 35 | Spain |
| `ftse_mib` | FTSE MIB | Italy |
| `smi20` | SMI 20 | Switzerland |

### Asia-Pacific Indexes (Wikipedia)

| Key | Index | Country |
|-----|-------|---------|
| `nikkei225` | Nikkei 225 | Japan |
| `asx200` | ASX 200 | Australia |

### Canadian Indexes (Wikipedia)

| Key | Index | Cap Range | Suffix |
|-----|-------|-----------|--------|
| `tsx60` | S&P/TSX 60 | Large cap | `.TO` |
| `tsx_composite` | S&P/TSX Composite | Large/mid cap | `.TO` |

**Note:** Canadian tickers require the `.TO` suffix for yfinance. This is automatically appended by the scraper when the index source has a `suffix` field.

### ETF Holdings (iShares / BlackRock CSV)

Holdings are fetched directly from issuer CSV files (iShares product pages for US-listed ETFs, BlackRock Canada product pages for TSX-listed ETFs). No yfinance dependency.

| Key | ETF | Focus | Source |
|-----|-----|-------|--------|
| `etf_iwm` | IWM | US small cap (Russell 2000) | iShares US |
| `etf_ijr` | IJR | S&P SmallCap 600 | iShares US |
| `etf_qual` | QUAL | US quality factor | iShares US |
| `etf_scz` | SCZ | International small cap | iShares US |
| `etf_efav` | EFAV | EAFE quality factor | iShares US |
| `etf_ezu` | EZU | Eurozone | iShares US |
| `etf_ewg` | EWG | Germany | iShares US |
| `etf_ewu` | EWU | UK | iShares US |
| `etf_ewq` | EWQ | France | iShares US |
| `etf_ewp` | EWP | Spain | iShares US |
| `etf_ewi` | EWI | Italy | iShares US |
| `etf_ewd` | EWD | Sweden | iShares US |
| `etf_ews` | EWS | Switzerland | iShares US |
| `etf_ewc` | EWC | Canada (MSCI) | iShares US |
| `etf_xic` | XIC | iShares S&P/TSX Capped Composite | BlackRock CA |
| `etf_xmd` | XMD | iShares S&P/TSX MidCap | BlackRock CA |
| `etf_xcs` | XCS | iShares S&P/TSX SmallCap | BlackRock CA |

**VGK** (Vanguard FTSE Europe) is listed in ETF_SOURCES but has no iShares/BlackRock backing; it is explicitly marked as unsupported until a Vanguard holdings source is added.

## Scan Workflow

### Index Discovery Flow

1. **Build universe**: Fetch tickers from cached index/ETF data
2. **Deduplicate**: Remove tickers that appear in multiple indexes
3. **Skip already-scanned**: Check `scan_results` table to avoid re-fetching
4. **Random sample**: Pick `batch_size` tickers randomly (don't always start from A)
5. **Fetch & filter**: For each ticker:
   - Fetch data via yfinance (or IBKR if available)
   - Apply preset filters (min FCF margin, min GM, min market cap)
   - If passes filters, run full `score_company()` evaluation
6. **Rank & display**: Sort by total score, display with fit classification
7. **Persist**: All results saved to `scan_results` table

### Manual Scan Flow

1. **Parse input**: Split comma-separated tickers, normalize to uppercase
2. **Fetch & score**: For each ticker, fetch data and run `score_company()`
3. **Calculate buy-under**: Run `calculate_buy_under()` for each result
4. **Display**: Show results ranked by score with fit classification

### Caching

Index constituents are cached in SQLite (`index_cache` table) to avoid re-scraping Wikipedia on every run. ETF holdings are cached similarly.

**Refresh buttons** re-download from source:
- "🔄 Refresh Indexes" — re-scrapes all Wikipedia index pages
- "📦 Refresh ETFs" — re-fetches ETF holdings from iShares/BlackRock CSV files

## FMP Integration (Optional)

For European stocks, yfinance data can be sparse. An optional **FMP (Financial Modeling Prep)** API key can be configured in Settings or on the Discovery page:

- Free tier: 250 requests/day
- Better coverage of European exchanges
- More reliable financial data for non-US companies

To use: enter your FMP API key in the "🔑 FMP API Key" section and test the connection.

## IBKR Scanner (Advanced)

If Interactive Brokers Gateway is running and `CSU_USE_IBKR=1` is set, the scanner can use IBKR's built-in market scanner for more precise fundamental screening:

- **Quality Compounders** and **Wide Moat** presets use IBKR scanner when available
- Scanner pre-filters by fundamentals before fetching detailed data
- Falls back to index-based scanning if IBKR is unavailable

**Limitations**: IBKR requires a paid data subscription for fundamental data. Without it, errors 10358/10089 are returned. yfinance is the default for this reason.
