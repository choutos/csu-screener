"""
Investment Process App — FMP Discovery Engine
Uses Financial Modeling Prep API to auto-discover quality companies.
Free tier: 250 requests/day.
"""
import requests
from db import get_db, upsert_scan
from fetcher import score_company
from datetime import datetime

BASE_URL = "https://financialmodelingprep.com/api/v3"


def get_api_key() -> str | None:
    """Load API key from config file."""
    from pathlib import Path
    key_file = Path(__file__).parent / "fmp_api_key.txt"
    if key_file.exists():
        return key_file.read_text().strip()
    return None


def save_api_key(key: str):
    from pathlib import Path
    (Path(__file__).parent / "fmp_api_key.txt").write_text(key.strip())


def test_api_key(key: str) -> bool:
    """Test if an API key works."""
    try:
        r = requests.get(f"{BASE_URL}/stock-screener", params={
            "apikey": key,
            "limit": 1,
            "marketCapMoreThan": 1000000000,
        }, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def discover_quality_stocks(api_key: str, min_market_cap: int = 200_000_000,
                            max_market_cap: int = 50_000_000_000,
                            min_fcf_margin: float = 0.05,
                            min_gross_margin: float = 0.30,
                            min_roe: float = 0.10,
                            exchange: str = None,
                            limit: int = 50) -> list[dict]:
    """
    Discover stocks matching quality criteria via FMP Stock Screener.
    Returns list of basic company data from FMP.
    """
    params = {
        "apikey": api_key,
        "marketCapMoreThan": min_market_cap,
        "marketCapLessThan": max_market_cap,
        "freeCashFlowMarginMoreThan": min_fcf_margin * 100,  # FMP uses percentage
        "grossMarginMoreThan": min_gross_margin * 100,
        "roeMoreThan": min_roe * 100,
        "limit": limit,
    }
    
    if exchange:
        params["exchange"] = exchange
    
    try:
        r = requests.get(f"{BASE_URL}/stock-screener", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def discover_by_sector(api_key: str, sector: str, **kwargs) -> list[dict]:
    """Discover quality stocks in a specific sector."""
    params = {
        "apikey": api_key,
        "sector": sector,
        "marketCapMoreThan": kwargs.get("min_market_cap", 200_000_000),
        "marketCapLessThan": kwargs.get("max_market_cap", 50_000_000_000),
        "limit": kwargs.get("limit", 50),
    }
    try:
        r = requests.get(f"{BASE_URL}/stock-screener", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def get_company_profile(api_key: str, ticker: str) -> dict | None:
    """Get detailed company profile from FMP."""
    try:
        r = requests.get(f"{BASE_URL}/profile/{ticker}", params={"apikey": api_key}, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None
    except Exception:
        return None


def get_company_ratios(api_key: str, ticker: str) -> dict | None:
    """Get financial ratios from FMP."""
    try:
        r = requests.get(
            f"https://financialmodelingprep.com/api/v3/ratios/{ticker}",
            params={"apikey": api_key},
            timeout=10
        )
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None
    except Exception:
        return None


def run_discovery_scan(api_key: str, preset: str = "quality_compounders",
                       exchange: str = None) -> list[dict]:
    """
    Run a discovery scan with predefined presets.
    Returns list of companies enriched with FMP data + our scoring.
    """
    presets = {
        "quality_compounders": {
            "description": "High FCF, stable, durable businesses",
            "min_market_cap": 500_000_000,
            "max_market_cap": 50_000_000_000,
            "min_fcf_margin": 0.10,
            "min_gross_margin": 0.40,
            "min_roe": 0.12,
            "limit": 50,
        },
        "deep_value": {
            "description": "Cheap on FCF yield, profitable",
            "min_market_cap": 200_000_000,
            "max_market_cap": 10_000_000_000,
            "min_fcf_margin": 0.08,
            "min_gross_margin": 0.30,
            "min_roe": 0.08,
            "limit": 50,
        },
        "wide_moat": {
            "description": "High margins, dominant businesses",
            "min_market_cap": 1_000_000_000,
            "max_market_cap": 100_000_000_000,
            "min_fcf_margin": 0.15,
            "min_gross_margin": 0.60,
            "min_roe": 0.15,
            "limit": 50,
        },
        "small_cap_quality": {
            "description": "Quality under the radar",
            "min_market_cap": 200_000_000,
            "max_market_cap": 3_000_000_000,
            "min_fcf_margin": 0.08,
            "min_gross_margin": 0.35,
            "min_roe": 0.10,
            "limit": 50,
        },
        "european_quality": {
            "description": "Quality compounders in Europe",
            "min_market_cap": 500_000_000,
            "max_market_cap": 30_000_000_000,
            "min_fcf_margin": 0.08,
            "min_gross_margin": 0.35,
            "min_roe": 0.10,
            "limit": 50,
            "exchange": "ETF",
        },
    }
    
    p = presets.get(preset, presets["quality_compounders"])
    results = discover_quality_stocks(
        api_key,
        min_market_cap=p["min_market_cap"],
        max_market_cap=p["max_market_cap"],
        min_fcf_margin=p["min_fcf_margin"],
        min_gross_margin=p["min_gross_margin"],
        min_roe=p["min_roe"],
        exchange=exchange or p.get("exchange"),
        limit=p["limit"],
    )
    
    if isinstance(results, dict) and "error" in results:
        return results
    
    # Enrich with our scoring
    enriched = []
    for stock in results:
        # FMP returns basic screener data — normalize it
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
            "fcf_yield": None,  # Calculate below
            "debt_to_equity": round(stock.get("debtEquity", 0) or 0, 2),
            "revenue_growth_3y": round(stock.get("revenueGrowth5Years", 0) or 0, 3),
            "revenue_volatility": None,  # Not available from screener
        }
        
        # Calculate FCF yield
        if data["market_cap_m"] and data["fcf_margin"] and stock.get("revenue"):
            fcf = data["fcf_margin"] * stock["revenue"]
            data["fcf_yield"] = round(fcf / (data["market_cap_m"] * 1e6), 4) if data["market_cap_m"] > 0 else None
        
        # Score it
        scored = score_company(data)
        enriched.append(scored)
    
    # Sort by score
    enriched.sort(key=lambda x: x.get("total_score", 0), reverse=True)
    return enriched


def get_available_sectors(api_key: str) -> list[str]:
    """Get list of available sectors from FMP."""
    try:
        r = requests.get(f"{BASE_URL}/stock-screener", params={
            "apikey": api_key,
            "limit": 5,
            "marketCapMoreThan": 1000000000,
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        sectors = set()
        for stock in data:
            if stock.get("sector"):
                sectors.add(stock["sector"])
        return sorted(sectors)
    except Exception:
        return []
