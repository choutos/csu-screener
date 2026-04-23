"""
Investment Process App — FMP Discovery Engine
Uses Financial Modeling Prep API to auto-discover quality companies.
Falls back to yfinance for detailed scoring.

FMP Free Tier includes:
- /stable/stock-list (all stocks)
- /stable/profile (company profiles)
- /stable/income-statement (financials)
- /stable/key-metrics (ratios)

Stock screener (/api/v3/stock-screener) requires Starter plan ($14/mo).
This module works with BOTH free and paid tiers.
"""
import requests
from db import get_db, upsert_scan
from fetcher import score_company
from datetime import datetime

STABLE_URL = "https://financialmodelingprep.com/stable"
V3_URL = "https://financialmodelingprep.com/api/v3"


def get_api_key() -> str | None:
    """Load API key from config file."""
    from pathlib import Path
    key_file = Path(__file__).parent / "fmp_api_key.txt"
    if key_file.exists():
        key = key_file.read_text().strip()
        return key if key else None
    return None


def save_api_key(key: str):
    from pathlib import Path
    (Path(__file__).parent / "fmp_api_key.txt").write_text(key.strip())


def test_api_key(key: str) -> tuple[bool, str]:
    """Test if an API key works. Returns (success, message)."""
    try:
        r = requests.get(f"{STABLE_URL}/stock-list", params={
            "apikey": key,
            "limit": 1,
        }, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) or (isinstance(data, dict) and "Error Message" not in data):
                return True, "✅ API key works!"
            else:
                return False, f"❌ API returned: {data}"
        elif r.status_code == 403:
            return False, "❌ Invalid API key"
        else:
            return False, f"❌ HTTP {r.status_code}"
    except Exception as e:
        return False, f"❌ Connection error: {e}"


def check_plan(key: str) -> str:
    """Detect if the API key has screener access (Starter+ plan)."""
    try:
        r = requests.get(f"{V3_URL}/stock-screener", params={
            "apikey": key,
            "marketCapMoreThan": 1000000000,
            "limit": 1,
        }, timeout=10)
        if r.status_code == 200:
            return "starter"
        else:
            return "free"
    except Exception:
        return "free"


# ─── Free Tier Discovery ─────────────────────────────────────────────────────

def get_stock_list(key: str, exchange: str = None, limit: int = 5000) -> list[dict]:
    """Get list of all stocks from FMP (free tier)."""
    params = {"apikey": key, "limit": limit}
    if exchange:
        params["exchange"] = exchange
    try:
        r = requests.get(f"{STABLE_URL}/stock-list", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def get_company_profile(key: str, ticker: str) -> dict | None:
    """Get company profile (free tier)."""
    try:
        r = requests.get(f"{STABLE_URL}/profile", params={
            "apikey": key,
            "symbol": ticker,
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data[0] if isinstance(data, list) and data else data
    except Exception:
        return None


def get_key_metrics(key: str, ticker: str) -> dict | None:
    """Get key financial metrics (free tier)."""
    try:
        r = requests.get(f"{STABLE_URL}/key-metrics", params={
            "apikey": key,
            "symbol": ticker,
            "limit": 1,
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data[0] if isinstance(data, list) and data else data
    except Exception:
        return None


def get_income_statement(key: str, ticker: str) -> dict | None:
    """Get latest income statement (free tier)."""
    try:
        r = requests.get(f"{STABLE_URL}/income-statement", params={
            "apikey": key,
            "symbol": ticker,
            "limit": 1,
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data[0] if isinstance(data, list) and data else data
    except Exception:
        return None


def get_cash_flow(key: str, ticker: str) -> dict | None:
    """Get latest cash flow statement (free tier)."""
    try:
        r = requests.get(f"{STABLE_URL}/cash-flow-statement", params={
            "apikey": key,
            "symbol": ticker,
            "limit": 1,
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data[0] if isinstance(data, list) and data else data
    except Exception:
        return None


# ─── Paid Tier Discovery (Starter+) ──────────────────────────────────────────

def discover_stocks_screener(api_key: str, min_market_cap: int = 200_000_000,
                             max_market_cap: int = 50_000_000_000,
                             min_fcf_margin: float = 0.05,
                             min_gross_margin: float = 0.30,
                             min_roe: float = 0.10,
                             sector: str = None,
                             exchange: str = None,
                             limit: int = 50) -> list[dict]:
    """Use FMP Stock Screener (requires Starter plan)."""
    params = {
        "apikey": api_key,
        "marketCapMoreThan": min_market_cap,
        "marketCapLessThan": max_market_cap,
        "limit": limit,
    }
    
    if min_fcf_margin > 0:
        params["freeCashFlowMarginMoreThan"] = round(min_fcf_margin * 100, 1)
    if min_gross_margin > 0:
        params["grossMarginMoreThan"] = round(min_gross_margin * 100, 1)
    if min_roe > 0:
        params["roeMoreThan"] = round(min_roe * 100, 1)
    if sector:
        params["sector"] = sector
    if exchange:
        params["exchange"] = exchange
    
    try:
        r = requests.get(f"{V3_URL}/stock-screener", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ─── Hybrid Discovery (works on free tier) ────────────────────────────────────

def discover_free_tier(api_key: str, exchange: str = None,
                       sector_filter: list[str] = None,
                       min_market_cap: int = 500_000_000) -> list[dict]:
    """
    Two-step discovery for free tier:
    1. Get stock list (free)
    2. Filter by market cap + sector
    3. Enrich top candidates with profiles + metrics
    
    Returns list of scored companies.
    """
    # Step 1: Get stock list
    stocks = get_stock_list(api_key, exchange=exchange)
    if isinstance(stocks, dict) and "error" in stocks:
        return stocks
    
    # Step 2: Filter
    filtered = []
    for s in stocks:
        mcap = s.get("marketCap", 0) or 0
        if mcap >= min_market_cap:
            if sector_filter:
                sec = (s.get("sector") or "").lower()
                if not any(sf.lower() in sec for sf in sector_filter):
                    continue
            filtered.append(s)
    
    # Sort by market cap descending, take top N
    filtered.sort(key=lambda x: x.get("marketCap", 0) or 0, reverse=True)
    candidates = filtered[:100]  # Process top 100
    
    # Step 3: Enrich with financial data
    results = []
    for stock in candidates:
        ticker = stock.get("symbol", "")
        if not ticker:
            continue
        
        # Get profile for sector/industry
        profile = get_company_profile(api_key, ticker)
        
        # Get key metrics for margins
        metrics = get_key_metrics(api_key, ticker)
        
        # Build data dict
        data = {
            "ticker": ticker,
            "name": stock.get("name") or (profile.get("companyName") if profile else ""),
            "sector": (profile.get("sector") if profile else "") or stock.get("sector", ""),
            "industry": (profile.get("industry") if profile else "") or stock.get("industry", ""),
            "market_cap_m": round((stock.get("marketCap", 0) or 0) / 1e6, 1),
            "price": stock.get("price"),
            "currency": "USD",
            "gross_margin": None,
            "fcf_margin": None,
            "fcf_yield": None,
            "debt_to_equity": None,
            "revenue_growth_3y": None,
            "revenue_volatility": None,
        }
        
        if profile:
            data["gross_margin"] = round(profile.get("grossMargin", 0) or 0, 3) if profile.get("grossMargin") else None
        
        if metrics:
            if metrics.get("freeCashFlowPerShare") and metrics.get("revenuePerShare"):
                data["fcf_margin"] = round(metrics["freeCashFlowPerShare"] / metrics["revenuePerShare"], 3) if metrics["revenuePerShare"] else None
            if metrics.get("debtToEquity"):
                data["debt_to_equity"] = round(metrics["debtToEquity"], 2)
            if metrics.get("revenueGrowth"):
                data["revenue_growth_3y"] = round(metrics["revenueGrowth"], 3)
        
        # Calculate FCF yield
        mcap = data["market_cap_m"] * 1e6 if data["market_cap_m"] else 0
        if data["fcf_margin"] and data.get("price") and mcap > 0:
            # Approximate: FCF = fcf_margin * (price / price_per_share) * shares
            # Simpler: use FCF yield from metrics if available
            pass
        
        # Score it
        scored = score_company(data)
        results.append(scored)
    
    results.sort(key=lambda x: x.get("total_score", 0), reverse=True)
    return results


# ─── Unified Discovery Entry Point ───────────────────────────────────────────

def run_discovery(api_key: str, preset: str = "quality_compounders",
                  exchange: str = None, sector: str = None) -> list[dict]:
    """
    Run discovery scan. Auto-detects free vs paid tier.
    """
    presets = {
        "quality_compounders": {
            "description": "High FCF, stable, durable businesses",
            "min_market_cap": 500_000_000,
            "max_market_cap": 50_000_000_000,
            "min_fcf_margin": 0.10,
            "min_gross_margin": 0.40,
            "min_roe": 0.12,
        },
        "deep_value": {
            "description": "Cheap on FCF yield, profitable",
            "min_market_cap": 200_000_000,
            "max_market_cap": 10_000_000_000,
            "min_fcf_margin": 0.08,
            "min_gross_margin": 0.30,
            "min_roe": 0.08,
        },
        "wide_moat": {
            "description": "High margins, dominant businesses",
            "min_market_cap": 1_000_000_000,
            "max_market_cap": 100_000_000_000,
            "min_fcf_margin": 0.15,
            "min_gross_margin": 0.60,
            "min_roe": 0.15,
        },
        "small_cap_quality": {
            "description": "Quality under the radar",
            "min_market_cap": 200_000_000,
            "max_market_cap": 3_000_000_000,
            "min_fcf_margin": 0.08,
            "min_gross_margin": 0.35,
            "min_roe": 0.10,
        },
        "european_quality": {
            "description": "Quality compounders in Europe",
            "min_market_cap": 500_000_000,
            "max_market_cap": 30_000_000_000,
            "min_fcf_margin": 0.08,
            "min_gross_margin": 0.35,
            "min_roe": 0.10,
        },
    }
    
    p = presets.get(preset, presets["quality_compounders"])
    
    # Try paid tier first (screener)
    plan = check_plan(api_key)
    
    if plan == "starter":
        results = discover_stocks_screener(
            api_key,
            min_market_cap=p["min_market_cap"],
            max_market_cap=p["max_market_cap"],
            min_fcf_margin=p["min_fcf_margin"],
            min_gross_margin=p["min_gross_margin"],
            min_roe=p["min_roe"],
            sector=sector,
            exchange=exchange,
        )
        
        if isinstance(results, dict) and "error" in results:
            return results
        
        # Score results
        enriched = []
        for stock in results:
            data = {
                "ticker": stock.get("symbol", ""),
                "name": stock.get("companyName", ""),
                "sector": stock.get("sector", ""),
                "industry": stock.get("industry", ""),
                "market_cap_m": round(stock.get("marketCap", 0) / 1e6, 1) if stock.get("marketCap") else None,
                "price": stock.get("price"),
                "currency": "USD",
                "gross_margin": round(stock.get("grossMargin", 0) or 0, 3),
                "fcf_margin": round(stock.get("freeCashFlowMargin", 0) or 0, 3),
                "fcf_yield": None,
                "debt_to_equity": round(stock.get("debtEquity", 0) or 0, 2),
                "revenue_growth_3y": round(stock.get("revenueGrowth5Years", 0) or 0, 3),
                "revenue_volatility": None,
            }
            enriched.append(score_company(data))
        
        enriched.sort(key=lambda x: x.get("total_score", 0), reverse=True)
        return enriched
    
    else:
        # Free tier: two-step approach
        ex = exchange if exchange and exchange != "Any" else None
        sector_list = [sector] if sector else None
        results = discover_free_tier(api_key, exchange=ex, sector_filter=sector_list,
                                     min_market_cap=p["min_market_cap"])
        
        if isinstance(results, dict) and "error" in results:
            return results
        
        return results
