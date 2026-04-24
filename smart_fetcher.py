"""
Investment Process App — Smart Data Layer
Auto-detects IB Gateway → uses it for data. Falls back to yfinance.

IBKR provides:
- Full fundamentals (ratios, estimates, financials)
- European/Asian market coverage
- Real-time prices
- Built-in stock scanner

yfinance fallback:
- US stocks mostly
- Less reliable fundamental data
- No screener
"""
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ─── IB Gateway Detection & Connection ────────────────────────────────────────

_ib_client = None
_ib_connected = False


def is_ib_available() -> bool:
    """Check if IB Gateway is running and reachable."""
    import socket
    # IB Gateway default ports: 7497 (live), 7496 (paper), 4002 (live), 4001 (paper)
    for port in [7497, 7496, 4002, 4001]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            if result == 0:
                return True
        except Exception:
            continue
    return False


def get_ib_connection():
    """Get or create an IB connection. Returns None if unavailable."""
    global _ib_client, _ib_connected
    
    if _ib_connected and _ib_client is not None:
        return _ib_client
    
    if not is_ib_available():
        return None
    
    _ensure_event_loop()
    try:
        from ib_insync import IB
        ib = IB()
        # Try connecting to the first available port
        for port in [7497, 7496, 4002, 4001]:
            try:
                ib.connect("127.0.0.1", port, clientId=10, timeout=5)
                _ib_client = ib
                _ib_connected = True
                logger.info(f"Connected to IB Gateway on port {port}")
                return ib
            except Exception:
                continue
        return None
    except ImportError:
        return None


def disconnect_ib():
    """Disconnect from IB Gateway."""
    global _ib_client, _ib_connected
    if _ib_client:
        try:
            _ib_client.disconnect()
        except Exception:
            pass
    _ib_client = None
    _ib_connected = False


def get_data_source() -> str:
    """Returns 'ibkr' or 'yfinance' based on config and availability."""
    if os.environ.get("CSU_USE_IBKR", "").lower() in ("1", "true", "yes"):
        return "ibkr" if is_ib_available() else "yfinance"
    return "yfinance"


def _should_try_ibkr() -> bool:
    """Check if we should attempt IBKR. Requires explicit opt-in via env var."""
    return (os.environ.get("CSU_USE_IBKR", "").lower() in ("1", "true", "yes")
            and is_ib_available())


# ─── Canadian Ticker Resolution ──────────────────────────────────────────────

# Suffixes to try when a bare ticker fails on yfinance.
# .TO = Toronto Stock Exchange (TSX), .V = TSX Venture Exchange (TSXV).
_CANADIAN_SUFFIXES = (".TO", ".V")


def _has_exchange_suffix(ticker: str) -> bool:
    """Return True if the ticker already contains an exchange suffix (e.g. .TO, .L)."""
    return "." in ticker


def _try_yfinance_variants(ticker: str) -> Optional[dict]:
    """Try fetching *ticker* from yfinance, then Canadian-suffixed variants.

    Returns the first successful result (with the resolved ticker stored in
    data["ticker"]) or None.
    """
    # 1. Try the ticker as-is first.
    data = _fetch_from_yfinance(ticker)
    if data:
        return data

    # 2. If the ticker already has an exchange suffix, don't guess further.
    if _has_exchange_suffix(ticker):
        return None

    # 3. Try Canadian exchange suffixes.
    for suffix in _CANADIAN_SUFFIXES:
        candidate = ticker + suffix
        data = _fetch_from_yfinance(candidate)
        if data:
            logger.info(f"Resolved bare ticker {ticker} → {candidate}")
            return data

    return None


# ─── Unified Fetch Interface ──────────────────────────────────────────────────

def fetch_company(ticker: str) -> Optional[dict]:
    """
    Fetch company data. Uses yfinance by default.
    Set CSU_USE_IBKR=1 env var to try IB Gateway first.

    For bare tickers (no exchange suffix) that fail on the first attempt,
    Canadian suffixes (.TO, .V) are tried automatically.
    """
    if _should_try_ibkr():
        data = _fetch_from_ibkr(ticker)
        price = data.get("price") if data else None
        has_price = price is not None and str(price) != 'nan' and price > 0
        has_fundamentals = data.get("gross_margin") is not None if data else False
        if data and has_price and has_fundamentals:
            data["data_source"] = "ibkr"
            return data
        # IBKR gave partial data — fall back

    data = _try_yfinance_variants(ticker)
    if data:
        data["data_source"] = "yfinance"
    return data


def fetch_companies_batch(tickers: list[str]) -> list[dict]:
    """Fetch multiple companies. Uses IBKR's batch capabilities when opted in."""
    if _should_try_ibkr():
        results = _fetch_batch_ibkr(tickers)
        if results and any(r.get("price") and r.get("gross_margin") is not None for r in results):
            for r in results:
                r["data_source"] = "ibkr"
            return results
    
    # yfinance fallback
    results = []
    for t in tickers:
        data = _fetch_from_yfinance(t)
        if data:
            data["data_source"] = "yfinance"
            results.append(data)
    return results


# ─── IBKR Implementation ──────────────────────────────────────────────────────

def _ensure_event_loop():
    """Ensure an asyncio event loop exists (needed for ib_insync in Streamlit threads)."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)


def _fetch_from_ibkr(ticker: str) -> Optional[dict]:
    """Fetch comprehensive company data from IB Gateway."""
    _ensure_event_loop()
    try:
        from ib_insync import IB, Stock, util
        util.startLoop()
    except ImportError:
        return None
    
    ib = get_ib_connection()
    if not ib:
        return None
    
    try:
        # Resolve contract
        contract = Stock(ticker, "SMART", "USD")
        ib.qualifyContracts(contract)
        
        # Get fundamentals
        fundamentals = ib.reqFundamentalData(contract, "ReportFinSummary")
        
        # Get price
        ticker_obj = ib.reqMktData(contract, "", True, False)
        ib.sleep(1)
        
        # Get account summary for position data
        data = {
            "ticker": ticker,
            "name": contract.symbol,
            "sector": None,
            "industry": None,
            "market_cap_m": None,
            "price": ticker_obj.marketPrice() if ticker_obj else None,
            "currency": "USD",
            "gross_margin": None,
            "fcf_margin": None,
            "fcf_yield": None,
            "debt_to_equity": None,
            "revenue_growth_3y": None,
            "revenue_volatility": None,
        }
        
        # Parse fundamentals if available
        if fundamentals:
            data.update(_parse_ibkr_fundamentals(fundamentals))
        
        return data
        
    except Exception as e:
        logger.warning(f"IBKR fetch failed for {ticker}: {e}")
        return None


def _fetch_batch_ibkr(tickers: list[str]) -> Optional[list[dict]]:
    """Fetch multiple companies from IBKR."""
    _ensure_event_loop()
    try:
        from ib_insync import Stock, util
        util.startLoop()
    except ImportError:
        return None
    
    ib = get_ib_connection()
    if not ib:
        return None
    
    results = []
    try:
        for ticker in tickers:
            data = _fetch_from_ibkr(ticker)
            if data:
                results.append(data)
        return results if results else None
    except Exception as e:
        logger.warning(f"IBKR batch failed: {e}")
        return None


def _parse_ibkr_fundamentals(xml_data: str) -> dict:
    """Parse IBKR fundamental data XML into our dict format."""
    # IBKR returns XML — basic parsing for key metrics
    # This is a simplified version; full parsing would use lxml
    import re
    result = {}
    
    # Try to extract key ratios from the XML
    patterns = {
        "gross_margin": r"GrossMargin.*?(\d+\.?\d*)",
        "net_margin": r"NetMargin.*?(\d+\.?\d*)",
        "debt_to_equity": r"DebtToEquity.*?(\d+\.?\d*)",
        "revenue_growth": r"RevenueGrowth.*?(-?\d+\.?\d*)",
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, xml_data, re.IGNORECASE)
        if match:
            val = float(match.group(1))
            if key == "gross_margin":
                result["gross_margin"] = round(val / 100, 3) if val > 1 else round(val, 3)
            elif key == "debt_to_equity":
                result["debt_to_equity"] = round(val, 2)
            elif key == "revenue_growth":
                result["revenue_growth_3y"] = round(val, 3)
    
    return result


# ─── IBKR Scanner ─────────────────────────────────────────────────────────────

def ibkr_scan(scanner_params: dict) -> Optional[list[dict]]:
    """
    Use IBKR's built-in stock scanner.
    Returns list of tickers matching criteria.
    Only available when IB Gateway is connected.
    """
    try:
        from ib_insync import IB, ScannerSubscription, Stock
        ib = get_ib_connection()
        if not ib:
            return None
        
        scan = ScannerSubscription()
        scan.instrument = "STK"
        scan.locationCode = scanner_params.get("location", "STK.US")
        scan.scanCode = scanner_params.get("scan_code", "TOP_PERC_GAIN")
        
        if scanner_params.get("min_market_cap"):
            scan.marketCapAbove = scanner_params["min_market_cap"]
        if scanner_params.get("max_market_cap"):
            scan.marketCapBelow = scanner_params["max_market_cap"]
        if scanner_params.get("min_price"):
            scan.priceAbove = scanner_params["min_price"]
        if scanner_params.get("max_price"):
            scan.priceBelow = scanner_params["max_price"]
        
        results = ib.reqScannerData(scan)
        
        return [
            {
                "ticker": r.contractDetails.contract.symbol,
                "name": r.contractDetails.longName or r.contractDetails.contract.symbol,
                "exchange": r.contractDetails.contract.exchange,
            }
            for r in results
        ]
        
    except Exception as e:
        logger.warning(f"IBKR scan failed: {e}")
        return None


# ─── yfinance Implementation (Fallback) ────────────────────────────────────────

def _fetch_from_yfinance(ticker: str) -> Optional[dict]:
    """Fetch company data from yfinance. Same logic as the original fetcher."""
    try:
        import yfinance as yf
        
        stock = yf.Ticker(ticker)
        info = stock.info
        
        if not info or not info.get("regularMarketPrice"):
            return None
        
        # Extract key metrics
        data = {
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName", ticker),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "market_cap_m": round((info.get("marketCap") or 0) / 1e6, 1) or None,
            "price": info.get("regularMarketPrice") or info.get("currentPrice"),
            "currency": info.get("currency", "USD"),
            "gross_margin": round(info.get("grossMargins", 0) or 0, 3) if info.get("grossMargins") else None,
            "fcf_margin": None,
            "fcf_yield": None,
            "debt_to_equity": round(info.get("debtToEquity", 0) or 0, 2) if info.get("debtToEquity") else None,
            "revenue_growth_3y": round(info.get("revenueGrowth", 0) or 0, 3) if info.get("revenueGrowth") else None,
            "revenue_volatility": None,
        }
        
        # Calculate FCF margin
        fcf = info.get("freeCashflow")
        revenue = info.get("totalRevenue")
        if fcf and revenue and revenue > 0:
            data["fcf_margin"] = round(fcf / revenue, 3)
        
        # Calculate FCF yield
        mcap = info.get("marketCap")
        if fcf and mcap and mcap > 0:
            data["fcf_yield"] = round(fcf / mcap, 4)
        
        # Revenue volatility from financials
        try:
            revs = stock.financials.loc["Total Revenue"] if "Total Revenue" in stock.financials.index else None
            if revs is not None and len(revs) >= 3:
                vals = revs.head(4).values.astype(float)
                changes = []
                for i in range(1, len(vals)):
                    if vals[i-1] != 0:
                        changes.append((vals[i] - vals[i-1]) / abs(vals[i-1]))
                if changes:
                    import numpy as np
                    data["revenue_volatility"] = round(float(np.std(changes)), 3)
        except Exception:
            pass
        
        return data
        
    except Exception as e:
        logger.warning(f"yfinance fetch failed for {ticker}: {e}")
        return None


# ─── Buy-Under Calculator ─────────────────────────────────────────────────────

def calculate_buy_under(ticker: str, data: dict = None) -> Optional[dict]:
    """
    Calculate a conservative 'Buy Under' price using FCF-based valuation.
    
    Method: Reverse DCF
    - Take current FCF
    - Assume conservative growth (3-5% for 10 years)
    - Apply discount rate (10%)
    - Terminal value at 15x FCF
    - Buy Under = Fair Value × 0.75 (25% margin of safety)
    
    Returns dict with fair_value, buy_under, and assumptions.
    """
    if not data:
        data = fetch_company(ticker)
    if not data:
        return None
    
    price = data.get("price")
    mcap = (data.get("market_cap_m") or 0) * 1e6
    fcf_margin = data.get("fcf_margin")
    fcf_yield = data.get("fcf_yield")
    growth = data.get("revenue_growth_3y")
    
    if not price or not mcap or not fcf_margin:
        return None
    
    # Calculate current FCF
    fcf = fcf_margin * mcap / (fcf_margin + (1 - fcf_margin))  # Approximate
    if fcf_yield and mcap > 0:
        fcf = fcf_yield * mcap  # More accurate if we have this
    
    if fcf <= 0:
        return None
    
    # Growth assumptions based on track record
    if growth and growth > 0.10:
        assumed_growth = 0.08  # Cap at 8% regardless of history
    elif growth and growth > 0.03:
        assumed_growth = growth * 0.7  # Degrade to 70% of historical
    else:
        assumed_growth = 0.03  # Minimum 3% for quality companies
    
    discount_rate = 0.10
    terminal_multiple = 15
    years = 10
    margin_of_safety = 0.75
    
    # DCF calculation
    pv_fcf = 0
    projected_fcf = fcf
    for year in range(1, years + 1):
        projected_fcf *= (1 + assumed_growth)
        pv = projected_fcf / ((1 + discount_rate) ** year)
        pv_fcf += pv
    
    # Terminal value
    terminal_fcf = projected_fcf * (1 + assumed_growth * 0.5)  # Slow growth forever
    terminal_value = terminal_fcf * terminal_multiple
    pv_terminal = terminal_value / ((1 + discount_rate) ** years)
    
    fair_value = pv_fcf + pv_terminal
    buy_under = fair_value * margin_of_safety
    
    return {
        "ticker": ticker,
        "current_price": price,
        "current_mcap_m": round(mcap / 1e6, 1),
        "estimated_fcf_m": round(fcf / 1e6, 1),
        "assumed_growth": round(assumed_growth, 3),
        "discount_rate": discount_rate,
        "terminal_multiple": terminal_multiple,
        "fair_value_m": round(fair_value / 1e6, 1),
        "fair_value_per_share": round(fair_value / (mcap / price), 2) if price else None,
        "buy_under_m": round(buy_under / 1e6, 1),
        "buy_under_per_share": round(buy_under / (mcap / price), 2) if price else None,
        "upside_to_fair": round((fair_value / mcap - 1) * 100, 1) if mcap > 0 else None,
        "upside_to_buy_under": round((buy_under / mcap - 1) * 100, 1) if mcap > 0 else None,
        "method": "reverse_dcf",
        "data_source": data.get("data_source", "unknown"),
    }
