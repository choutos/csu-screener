#!/usr/bin/env python3
"""
CSU-Inspired Vertical Software Screener
========================================
Screens public markets for companies fitting the Constellation Software
acquisition profile: vertical/niche software, high retention, low % of
customer costs, mission-critical, FCF-generative, unglamorous.

Data source: Yahoo Finance (yfinance) — free, no API key needed.

Usage:
  python screener.py                    # Run default seed screen
  python screener.py --sector Technology  # Filter by sector
  python screener.py --tickers CSU.TO ROP TDG  # Screen specific tickers
  python screener.py --export csv       # Export results
  python screener.py --watchlist        # Screen watchlist.json

For deeper data, consider:
  - Financial Modeling Prep API (free tier, better financials)
  - Stockopedia (paid) — quality/growth/value composite scores
  - SEC EDGAR + XBRL — raw filing data (free, complex)
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

# ─── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
WATCHLIST_FILE = BASE_DIR / "watchlist.json"
DATABASE_FILE = BASE_DIR / "data" / "screener-database.csv"
RESULTS_DIR = BASE_DIR / "data" / "results"
COMPANY_CARDS_DIR = BASE_DIR / "company-cards"
SECTOR_DIVES_DIR = BASE_DIR / "sector-deep-dives"
QUARTERLY_LETTERS_DIR = BASE_DIR / "quarterly-letters"

# ─── CSU-Inspired Thresholds ─────────────────────────────────────────────────

THRESHOLDS = {
    "max_revenue_volatility_5y": 0.25,
    "min_fcf_margin": 0.10,
    "min_gross_margin": 0.50,
    "min_ebit_margin": 0.15,
    "max_debt_to_equity": 2.0,
    "min_fcf_yield": 0.02,
    "min_revenue_growth_3y": -0.05,
    "max_revenue_growth_3y": 0.30,
    "min_years_public": 5,
    "min_market_cap_m": 200,
    "max_market_cap_m": 50000,
}

# Industries most likely to contain CSU-like companies
TARGET_INDUSTRIES = [
    "Software—Application",
    "Software—Infrastructure",
    "Information Technology Services",
    "Communication Equipment",
    "Specialty Industrial Machinery",
    "Scientific & Technical Instruments",
    "Business Equipment & Supplies",
    "Healthcare Information Services",
    "Medical Devices",
    "Aerospace & Defense",
    "Electronic Components",
    "Electrical Equipment & Parts",
]

# Seed tickers for default run
SEED_TICKERS = {
    "CSU.TO": "Constellation Software",
    "DND.TO": "Descartes Systems",
    "ROP": "Roper Technologies",
    "TDG": "TransDigm Group",
    "VRNS": "Varonis Systems",
    "BLKB": "Blackbaud",
    "MANH": "Manhattan Associates",
    "PTC": "PTC Inc",
    "SSNC": "SS&C Technologies",
    "JKHY": "Jack Henry & Associates",
    "FDS": "FactSet",
    "MORN": "Morningstar",
    "VEEV": "Veeva Systems",
    "PAYX": "Paychex",
    "PAGS": "PagSeguro Digital",
    "KEYS": "Keysight Technologies",
    "ANSS": "ANSYS",
    "ADSK": "Autodesk",
}


# ─── Core Functions ──────────────────────────────────────────────────────────

def fetch_company_data(ticker_str: str) -> dict | None:
    """Fetch financial data for a single ticker from Yahoo Finance."""
    try:
        ticker = yf.Ticker(ticker_str)
        info = ticker.info

        if not info or info.get("regularMarketPrice") is None:
            print(f"  ⚠ No data for {ticker_str}")
            return None

        name = info.get("longName") or info.get("shortName") or ticker_str
        market_cap = info.get("marketCap", 0) or 0

        # Margins
        gross_margin = info.get("grossMargins", 0) or 0
        ebit_margin = info.get("operatingMargins", 0) or 0
        total_revenue = info.get("totalRevenue", 0) or 0
        debt_to_equity = info.get("debtToEquity", 0) or 0

        # FCF from cash flow statement
        fcf_margin = None
        fcf_absolute = None
        try:
            cf = ticker.cashflow
            if cf is not None and not cf.empty and "Free Cash Flow" in cf.index:
                free_cf = cf.loc["Free Cash Flow"]
                if free_cf is not None and not free_cf.empty:
                    fcf_absolute = free_cf.iloc[0]
                    if total_revenue and total_revenue > 0:
                        fcf_margin = fcf_absolute / total_revenue
        except Exception:
            pass

        # FCF yield
        fcf_yield = None
        if fcf_absolute and market_cap and market_cap > 0:
            fcf_yield = fcf_absolute / market_cap

        # Revenue growth (CAGR from income statement)
        revenue_growth = None
        try:
            income = ticker.financials
            if income is not None and not income.empty and "Total Revenue" in income.index:
                rev = income.loc["Total Revenue"]
                if len(rev) >= 2:
                    n_years = len(rev) - 1
                    earliest = rev.iloc[-1]
                    if earliest > 0 and n_years > 0:
                        revenue_growth = (rev.iloc[0] / earliest) ** (1 / n_years) - 1
        except Exception:
            pass

        # Revenue volatility (std/mean)
        revenue_volatility = None
        try:
            income = ticker.financials
            if income is not None and not income.empty and "Total Revenue" in income.index:
                rev = income.loc["Total Revenue"].dropna()
                if len(rev) >= 3 and rev.mean() != 0:
                    revenue_volatility = float(rev.std() / rev.mean())
        except Exception:
            pass

        return {
            "ticker": ticker_str,
            "name": name,
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "market_cap_m": round(market_cap / 1e6, 1),
            "gross_margin": round(gross_margin, 3) if gross_margin else None,
            "ebit_margin": round(ebit_margin, 3) if ebit_margin else None,
            "fcf_margin": round(fcf_margin, 3) if fcf_margin is not None else None,
            "fcf_yield": round(fcf_yield, 4) if fcf_yield is not None else None,
            "debt_to_equity": round(debt_to_equity / 100, 2) if debt_to_equity else None,
            "revenue_growth_3y": round(revenue_growth, 3) if revenue_growth is not None else None,
            "revenue_volatility": round(revenue_volatility, 3) if revenue_volatility is not None else None,
            "price": info.get("regularMarketPrice"),
            "currency": info.get("currency", "USD"),
            "fetched_at": datetime.now().isoformat(),
        }

    except Exception as e:
        print(f"  ✗ Error fetching {ticker_str}: {e}")
        return None


def score_company(data: dict) -> dict:
    """
    Score a company against CSU-like criteria.
    Each KPI: 0 (fail) → 3 (exceptional).
    """
    scores = {}
    passes = {}

    # 1. FCF Margin
    v = data.get("fcf_margin")
    if v is not None:
        scores["fcf_margin"] = 3 if v >= 0.20 else (2 if v >= 0.10 else (1 if v >= 0.05 else 0))
        passes["fcf_margin"] = v >= THRESHOLDS["min_fcf_margin"]

    # 2. Gross Margin
    v = data.get("gross_margin")
    if v is not None:
        scores["gross_margin"] = 3 if v >= 0.70 else (2 if v >= 0.50 else (1 if v >= 0.30 else 0))
        passes["gross_margin"] = v >= THRESHOLDS["min_gross_margin"]

    # 3. Revenue Stability
    v = data.get("revenue_volatility")
    if v is not None:
        scores["revenue_stability"] = 3 if v <= 0.10 else (2 if v <= 0.20 else (1 if v <= 0.30 else 0))
        passes["revenue_stability"] = v <= THRESHOLDS["max_revenue_volatility_5y"]

    # 4. Growth Profile
    v = data.get("revenue_growth_3y")
    if v is not None:
        scores["growth_profile"] = 3 if 0.02 <= v <= 0.15 else (2 if v <= 0.02 else (1 if v <= 0.30 else 0))
        passes["growth_profile"] = THRESHOLDS["min_revenue_growth_3y"] <= v <= THRESHOLDS["max_revenue_growth_3y"]

    # 5. FCF Yield
    v = data.get("fcf_yield")
    if v is not None:
        scores["fcf_yield"] = 3 if v >= 0.05 else (2 if v >= 0.03 else (1 if v >= 0.02 else 0))
        passes["fcf_yield"] = v >= THRESHOLDS["min_fcf_yield"]

    # 6. Debt Discipline
    v = data.get("debt_to_equity")
    if v is not None:
        scores["debt_discipline"] = 3 if v <= 0.5 else (2 if v <= 1.0 else (1 if v <= 2.0 else 0))
        passes["debt_discipline"] = v <= THRESHOLDS["max_debt_to_equity"]

    # 7. Size Fit
    v = data.get("market_cap_m")
    if v is not None:
        scores["size_fit"] = 3 if 500 <= v <= 10000 else (2 if 200 <= v < 500 or 10000 < v <= 30000 else (1 if v >= 200 else 0))
        passes["size_fit"] = THRESHOLDS["min_market_cap_m"] <= v <= THRESHOLDS["max_market_cap_m"]

    # 8. Industry Fit
    industry = data.get("industry", "")
    if industry in TARGET_INDUSTRIES:
        scores["industry_fit"] = 3
        passes["industry_fit"] = True
    elif any(kw in industry.lower() for kw in ["software", "technology", "information", "data"]):
        scores["industry_fit"] = 2
        passes["industry_fit"] = True
    else:
        scores["industry_fit"] = 0
        passes["industry_fit"] = False

    total = sum(scores.values())
    max_possible = len(scores) * 3
    passes_count = sum(1 for v in passes.values() if v)

    data["scores"] = scores
    data["passes"] = passes
    data["total_score"] = total
    data["max_score"] = max_possible
    data["pass_rate"] = round(passes_count / len(passes), 2) if passes else 0

    if total >= 18 and passes_count >= 6:
        data["csu_fit"] = "STRONG"
    elif total >= 12 and passes_count >= 4:
        data["csu_fit"] = "MODERATE"
    elif total >= 8:
        data["csu_fit"] = "WEAK"
    else:
        data["csu_fit"] = "NOT FIT"

    return data


def format_results(results: list[dict], show_scores: bool = True) -> str:
    """Format screening results for terminal output."""
    if not results:
        return "No results to display."

    results.sort(key=lambda x: x.get("total_score", 0), reverse=True)

    emoji = {"STRONG": "🟢", "MODERATE": "🟡", "WEAK": "🟠", "NOT FIT": "🔴"}
    lines = [
        "=" * 100,
        "CSU-INSPIRED VERTICAL SOFTWARE SCREENER RESULTS",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 100,
    ]

    for r in results:
        fit = r.get("csu_fit", "N/A")
        e = emoji.get(fit, "⚪")
        lines.append(f"\n{e} {r['ticker']} — {r['name']}")
        lines.append(f"   {r.get('sector', 'N/A')} / {r.get('industry', 'N/A')}")
        lines.append(f"   Market Cap: ${r.get('market_cap_m', 0):,.0f}M | Price: {r.get('price', 'N/A')} {r.get('currency', '')}")

        metrics = []
        for key, fmt in [("gross_margin", ".1%"), ("fcf_margin", ".1%"), ("fcf_yield", ".2%"),
                         ("revenue_growth_3y", ".1%"), ("debt_to_equity", ".2f"), ("revenue_volatility", ".1%")]:
            v = r.get(key)
            if v is not None:
                metrics.append(f"{key}: {v:{fmt}}")
        lines.append(f"   {' | '.join(metrics)}")

        if show_scores:
            lines.append(f"   Score: {r.get('total_score', 0)}/{r.get('max_score', 0)} | Pass Rate: {r.get('pass_rate', 0):.0%} | Fit: {fit}")
            if "scores" in r:
                lines.append(f"   Scores: {', '.join(f'{k}:{v}' for k, v in r['scores'].items())}")

    return "\n".join(lines)


def save_to_database(results: list[dict]):
    """Append results to persistent CSV database."""
    db_dir = DATABASE_FILE.parent
    db_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for r in results:
        row = {k: v for k, v in r.items() if k not in ("scores", "passes")}
        for k, v in r.get("scores", {}).items():
            row[f"score_{k}"] = v
        rows.append(row)

    df = pd.DataFrame(rows)

    if DATABASE_FILE.exists():
        existing = pd.read_csv(DATABASE_FILE)
        today = datetime.now().strftime("%Y-%m-%d")
        tickers = [r["ticker"] for r in results]
        existing = existing[~((existing["ticker"].isin(tickers)) & (existing["fetched_at"].str.startswith(today)))]
        df = pd.concat([existing, df], ignore_index=True)

    df.to_csv(DATABASE_FILE, index=False)
    print(f"\n💾 Saved {len(results)} entries to {DATABASE_FILE}")


def export_results(results: list[dict], fmt: str = "csv"):
    """Export results to file."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    if fmt == "csv":
        path = RESULTS_DIR / f"screener_{timestamp}.csv"
        rows = []
        for r in results:
            row = {k: v for k, v in r.items() if k not in ("scores", "passes")}
            for k, v in r.get("scores", {}).items():
                row[f"score_{k}"] = v
            rows.append(row)
        pd.DataFrame(rows).to_csv(path, index=False)
        print(f"📊 Exported CSV: {path}")

    elif fmt == "json":
        path = RESULTS_DIR / f"screener_{timestamp}.json"
        with open(path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"📊 Exported JSON: {path}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CSU-Inspired Vertical Software Screener")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers to screen")
    parser.add_argument("--sector", help="Filter by sector")
    parser.add_argument("--export", choices=["csv", "json"], help="Export format")
    parser.add_argument("--no-save", action="store_true", help="Don't save to database")
    parser.add_argument("--watchlist", action="store_true", help="Screen watchlist.json")
    parser.add_argument("--seed", action="store_true", help="Screen built-in seed tickers")
    args = parser.parse_args()

    # Pick tickers
    tickers = []
    if args.tickers:
        tickers = args.tickers
    elif args.watchlist and WATCHLIST_FILE.exists():
        with open(WATCHLIST_FILE) as f:
            wl = json.load(f)
        tickers = list(wl.keys())
    elif args.seed:
        tickers = list(SEED_TICKERS.keys())
    else:
        tickers = list(SEED_TICKERS.keys())
        print(f"💡 No source specified. Screening {len(tickers)} seed tickers.\n")

    print(f"🔍 Screening {len(tickers)} companies...\n")

    results = []
    for i, t in enumerate(tickers, 1):
        print(f"  [{i}/{len(tickers)}] {t}...", end=" ", flush=True)
        data = fetch_company_data(t)
        if data:
            scored = score_company(data)
            print(f"{scored.get('csu_fit', '?')} ({scored.get('total_score', 0)}/{scored.get('max_score', '?')})")
            results.append(scored)
        else:
            print("SKIPPED")

    # Filter
    if args.sector and results:
        results = [r for r in results if args.sector.lower() in r.get("sector", "").lower()]

    # Output
    print(format_results(results))

    if not args.no_save and results:
        save_to_database(results)

    if args.export and results:
        export_results(results, args.export)

    # Summary
    if results:
        fits = {}
        for r in results:
            f = r.get("csu_fit", "UNKNOWN")
            fits[f] = fits.get(f, 0) + 1
        print(f"\n📋 Summary: {len(results)} screened → {fits}")
        strong = [r for r in results if r.get("csu_fit") == "STRONG"]
        if strong:
            print(f"🟢 Strong fits: {', '.join(r['ticker'] for r in strong)}")


if __name__ == "__main__":
    main()
