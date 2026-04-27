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

from fetcher import fetch_company, score_company

# ─── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
WATCHLIST_FILE = BASE_DIR / "watchlist.json"
DATABASE_FILE = BASE_DIR / "data" / "screener-database.csv"
RESULTS_DIR = BASE_DIR / "data" / "results"
COMPANY_CARDS_DIR = BASE_DIR / "company-cards"
SECTOR_DIVES_DIR = BASE_DIR / "sector-deep-dives"
QUARTERLY_LETTERS_DIR = BASE_DIR / "quarterly-letters"

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
        data = fetch_company(t)
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
