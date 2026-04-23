"""
Investment Process App — Discovery Engine
Auto-discovers quality companies using multiple free sources.

Sources:
1. yfinance index constituents (S&P 500, S&P 400, S&P 600, Russell 2000)
2. Financial Modeling Prep API (free or paid — optional)
3. Manual ticker entry (always available)

No API key required for basic discovery.
"""
import requests
from db import get_db, upsert_scan
from fetcher import fetch_company, score_company
from datetime import datetime
import json
from pathlib import Path

# ─── API Key Management (FMP — optional) ──────────────────────────────────────

def get_api_key() -> str | None:
    from pathlib import Path
    key_file = Path(__file__).parent / "fmp_api_key.txt"
    if key_file.exists():
        key = key_file.read_text().strip()
        return key if key else None
    return None


def save_api_key(key: str):
    (Path(__file__).parent / "fmp_api_key.txt").write_text(key.strip())


def test_fmp_key(key: str) -> tuple[bool, str]:
    """Test FMP API key."""
    try:
        r = requests.get("https://financialmodelingprep.com/api/v3/profile/AAPL", params={
            "apikey": key,
        }, timeout=10)
        if r.status_code == 200:
            return True, "✅ FMP key works!"
        elif r.status_code == 403:
            return False, "❌ Invalid FMP key"
        elif r.status_code == 402:
            return False, "❌ FMP: Payment required (free tier limited)"
        else:
            return False, f"❌ FMP: HTTP {r.status_code}"
    except Exception as e:
        return False, f"❌ Connection error: {e}"


# ─── Index Constituents (Free — No API Key) ───────────────────────────────────

def _fetch_wikipedia_tickers(url: str) -> list[str]:
    """Fetch tickers from a Wikipedia page. Uses proper User-Agent."""
    import pandas as pd
    from io import StringIO
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    tables = pd.read_html(StringIO(r.text))
    return tables[0]["Symbol"].str.replace(".", "-").tolist()


def get_sp500_tickers() -> list[str]:
    """Get S&P 500 tickers from Wikipedia."""
    try:
        return _fetch_wikipedia_tickers("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    except Exception:
        return _get_cached_tickers("sp500")


def get_sp400_tickers() -> list[str]:
    """Get S&P 400 mid-cap tickers from Wikipedia."""
    try:
        return _fetch_wikipedia_tickers("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies")
    except Exception:
        return _get_cached_tickers("sp400")


def get_sp600_tickers() -> list[str]:
    """Get S&P 600 small-cap tickers from Wikipedia."""
    try:
        return _fetch_wikipedia_tickers("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies")
    except Exception:
        return _get_cached_tickers("sp600")


def _get_cached_tickers(index: str) -> list[str]:
    """Load cached tickers from file."""
    cache = Path(__file__).parent / "data" / f"{index}_tickers.json"
    if cache.exists():
        return json.loads(cache.read_text())
    return []


def _save_cached_tickers(index: str, tickers: list[str]):
    """Save tickers to cache file."""
    cache = Path(__file__).parent / "data" / f"{index}_tickers.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(tickers))


def refresh_index_cache() -> dict[str, int]:
    """Refresh all index caches. Returns {index: count}."""
    results = {}
    for name, fn in [("sp500", get_sp500_tickers), ("sp400", get_sp400_tickers), ("sp600", get_sp600_tickers)]:
        tickers = fn()
        if tickers:
            _save_cached_tickers(name, tickers)
            results[name] = len(tickers)
    return results


# ─── Discovery Scans ──────────────────────────────────────────────────────────

PRESETS = {
    "quality_compounders": {
        "description": "High FCF, stable, durable businesses",
        "indices": ["sp500", "sp400"],
        "min_fcf_margin": 0.10,
        "min_gross_margin": 0.40,
        "min_market_cap_m": 500,
    },
    "deep_value": {
        "description": "Cheap on FCF yield, profitable",
        "indices": ["sp400", "sp600"],
        "min_fcf_margin": 0.08,
        "min_gross_margin": 0.30,
        "min_market_cap_m": 200,
    },
    "wide_moat": {
        "description": "High margins, dominant businesses",
        "indices": ["sp500"],
        "min_fcf_margin": 0.15,
        "min_gross_margin": 0.60,
        "min_market_cap_m": 1000,
    },
    "small_cap_quality": {
        "description": "Quality under the radar",
        "indices": ["sp600", "sp400"],
        "min_fcf_margin": 0.08,
        "min_gross_margin": 0.35,
        "min_market_cap_m": 200,
    },
    "full_universe": {
        "description": "All US large/mid/small caps (slow!)",
        "indices": ["sp500", "sp400", "sp600"],
        "min_fcf_margin": 0.05,
        "min_gross_margin": 0.25,
        "min_market_cap_m": 100,
    },
}


def run_discovery(preset: str = "quality_compounders", 
                  batch_size: int = 20,
                  progress_callback=None) -> list[dict]:
    """
    Run a discovery scan using yfinance index constituents.
    No API key needed. Slower but truly free.
    
    Args:
        preset: Scan preset name
        batch_size: How many tickers to fetch per run (avoid rate limits)
        progress_callback: Optional fn(current, total, ticker) for progress updates
    
    Returns:
        List of scored company dicts
    """
    p = PRESETS.get(preset, PRESETS["quality_compounders"])
    
    # Gather tickers from indices
    all_tickers = []
    for idx_name in p["indices"]:
        tickers = _get_cached_tickers(idx_name)
        if not tickers:
            # Try fetching fresh
            fn_map = {"sp500": get_sp500_tickers, "sp400": get_sp400_tickers, "sp600": get_sp600_tickers}
            fn = fn_map.get(idx_name)
            if fn:
                tickers = fn()
                if tickers:
                    _save_cached_tickers(idx_name, tickers)
        all_tickers.extend(tickers)
    
    # Deduplicate
    seen = set()
    unique = []
    for t in all_tickers:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    
    # Limit batch
    to_scan = unique[:batch_size]
    
    results = []
    for i, ticker in enumerate(to_scan):
        if progress_callback:
            progress_callback(i, len(to_scan), ticker)
        
        data = fetch_company(ticker)
        if not data:
            continue
        
        # Pre-filter: skip if doesn't meet minimum criteria
        gm = data.get("gross_margin", 0) or 0
        fm = data.get("fcf_margin") or 0
        mc = data.get("market_cap_m", 0) or 0
        
        if gm < p["min_gross_margin"]:
            continue
        if fm < p["min_fcf_margin"]:
            continue
        if mc < p["min_market_cap_m"]:
            continue
        
        scored = score_company(data)
        
        # Only keep moderate or better
        if scored.get("total_score", 0) >= 12:
            results.append(scored)
    
    results.sort(key=lambda x: x.get("total_score", 0), reverse=True)
    return results


def get_available_ticker_count(preset: str) -> int:
    """Get how many tickers are available for a preset."""
    p = PRESETS.get(preset, PRESETS["quality_compounders"])
    total = 0
    for idx_name in p["indices"]:
        tickers = _get_cached_tickers(idx_name)
        total += len(tickers)
    return total


def get_index_stats() -> dict:
    """Get stats about cached index data."""
    stats = {}
    for idx in ["sp500", "sp400", "sp600"]:
        tickers = _get_cached_tickers(idx)
        cache_file = Path(__file__).parent / "data" / f"{idx}_tickers.json"
        stats[idx] = {
            "cached": len(tickers),
            "cache_exists": cache_file.exists(),
        }
    return stats
