"""
Investment Process App — Discovery Engine
Auto-discovers quality companies using multiple free sources.

Sources (auto-detected):
1. IBKR Scanner (when Gateway is running) — global, all markets
2. ETF Holdings (iShares/BlackRock CSV) — pull constituents from issuer holdings files
3. Wikipedia Index Constituents — S&P, FTSE, DAX, CAC, etc.
4. Nikkei official CSV — authoritative constituent list from indexes.nikkei.co.jp
   Primary: current-day components CSV; Secondary: weights CSV; Last resort: hardcoded list

No API key required for basic discovery.
"""
import csv
import io
import os
import re
import requests
import json
from db import get_db, upsert_scan
from fetcher import fetch_company, score_company
from smart_fetcher import is_ib_available, fetch_company as smart_fetch
from datetime import datetime
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
    try:
        r = requests.get("https://financialmodelingprep.com/stable/search-symbol", params={
            "apikey": key, "query": "AAPL",
        }, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                return True, "✅ FMP key works!"
            return False, "❌ FMP: Empty response"
        elif r.status_code == 403:
            return False, "❌ Invalid FMP key"
        elif r.status_code == 402:
            return False, "❌ FMP: Payment required"
        return False, f"❌ FMP: HTTP {r.status_code}"
    except Exception as e:
        return False, f"❌ Connection error: {e}"


# ─── Universe Sources ─────────────────────────────────────────────────────────

INDEX_SOURCES = {
    # US
    "sp500": {"url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "label": "S&P 500", "region": "US", "cap": "large"},
    "sp400": {"url": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "label": "S&P 400", "region": "US", "cap": "mid"},
    "sp600": {"url": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies", "label": "S&P 600", "region": "US", "cap": "small"},
    # Europe
    "ftse100": {"url": "https://en.wikipedia.org/wiki/FTSE_100_Index", "label": "FTSE 100", "region": "UK", "cap": "large"},
    "ftse250": {"url": "https://en.wikipedia.org/wiki/FTSE_250_Index", "label": "FTSE 250", "region": "UK", "cap": "mid"},
    "dax40": {"url": "https://en.wikipedia.org/wiki/DAX", "label": "DAX 40", "region": "DE", "cap": "large"},
    "mdax": {"url": "https://en.wikipedia.org/wiki/MDAX", "label": "MDAX", "region": "DE", "cap": "mid"},
    "cac40": {"url": "https://en.wikipedia.org/wiki/CAC_40", "label": "CAC 40", "region": "FR", "cap": "large"},
    "aex25": {"url": "https://en.wikipedia.org/wiki/AEX_index", "label": "AEX 25", "region": "NL", "cap": "large"},
    "ibex35": {"url": "https://en.wikipedia.org/wiki/IBEX_35", "label": "IBEX 35", "region": "ES", "cap": "large"},
    "ftse_mib": {"url": "https://en.wikipedia.org/wiki/FTSE_MIB", "label": "FTSE MIB", "region": "IT", "cap": "large"},
    "smi20": {"url": "https://en.wikipedia.org/wiki/Swiss_Market_Index", "label": "SMI 20", "region": "CH", "cap": "large"},
    "omx30": {"url": "https://en.wikipedia.org/wiki/OMX_Stockholm_30", "label": "OMX Stockholm 30", "region": "SE", "cap": "large"},
    # Canada
    "tsx60": {"url": "https://en.wikipedia.org/wiki/S%26P/TSX_60", "label": "S&P/TSX 60", "region": "CA", "cap": "large", "suffix": ".TO"},
    "tsx_composite": {"url": "https://en.wikipedia.org/wiki/S%26P/TSX_Composite_Index", "label": "S&P/TSX Composite", "region": "CA", "cap": "large", "suffix": ".TO"},
    # Asia/Pacific
    "nikkei225": {
        "label": "Nikkei 225", "region": "JP", "cap": "large",
        # 1) Primary: current-day components CSV (official Nikkei export)
        "csv_url": "https://indexes.nikkei.co.jp/nkave/archives/file/nikkei_stock_average_components_sample(today).csv",
        # 2) Secondary: weights CSV (also official, updated less frequently)
        "csv_url_fallback": "https://indexes.nikkei.co.jp/nkave/archives/file/nikkei_stock_average_weight_en.csv",
        # 3) Last resort: hardcoded list
        "static_tickers": True,
    },
    "asx200": {"url": "https://en.wikipedia.org/wiki/S%26P/ASX_200", "label": "ASX 200", "region": "AU", "cap": "large", "suffix": ".AX"},
}

ETF_SOURCES = {
    "SCZ": {"label": "iShares MSCI EAFE Small-Cap", "region": "EU", "cap": "small"},
    "EZU": {"label": "iShares MSCI Eurozone", "region": "EU", "cap": "large"},
    "VGK": {"label": "Vanguard FTSE Europe", "region": "EU", "cap": "large"},
    "EWG": {"label": "iShares MSCI Germany", "region": "DE", "cap": "large"},
    "EWU": {"label": "iShares MSCI United Kingdom", "region": "UK", "cap": "large"},
    "EWQ": {"label": "iShares MSCI France", "region": "FR", "cap": "large"},
    "EWP": {"label": "iShares MSCI Spain", "region": "ES", "cap": "large"},
    "EWI": {"label": "iShares MSCI Italy", "region": "IT", "cap": "large"},
    "EWD": {"label": "iShares MSCI Sweden", "region": "SE", "cap": "large"},
    "EWS": {"label": "iShares MSCI Switzerland", "region": "CH", "cap": "large"},
    "IWM": {"label": "iShares Russell 2000", "region": "US", "cap": "small"},
    "IJR": {"label": "iShares Core S&P Small-Cap", "region": "US", "cap": "small"},
    "QUAL": {"label": "iShares MSCI USA Quality Factor", "region": "US", "cap": "large"},
    "EFAV": {"label": "iShares MSCI EAFE Quality Factor", "region": "EU", "cap": "large"},
    # Canada
    "XIC": {"label": "iShares S&P/TSX Capped Composite", "region": "CA", "cap": "large"},
    "XMD": {"label": "iShares S&P/TSX MidCap", "region": "CA", "cap": "mid"},
    "XCS": {"label": "iShares S&P/TSX SmallCap", "region": "CA", "cap": "small"},
    "EWC": {"label": "iShares MSCI Canada", "region": "CA", "cap": "large"},
}

# ─── iShares / BlackRock product page URLs ───────────────────────────────────
# Used to locate the official holdings CSV for each ETF.
_ISHARES_PRODUCT_URLS: dict[str, str] = {
    # US-listed iShares  (ishares.com direct CSV pattern)
    "SCZ":  "https://www.ishares.com/us/products/239626/ishares-msci-eafe-smallcap-etf",
    "EZU":  "https://www.ishares.com/us/products/239623/ishares-msci-emu-etf",
    "EWG":  "https://www.ishares.com/us/products/239580/ishares-msci-germany-etf",
    "EWU":  "https://www.ishares.com/us/products/239690/ishares-msci-united-kingdom-etf",
    "EWQ":  "https://www.ishares.com/us/products/239648/ishares-msci-france-etf",
    "EWP":  "https://www.ishares.com/us/products/239683/ishares-msci-spain-capped-etf",
    "EWI":  "https://www.ishares.com/us/products/239664/ishares-msci-italy-etf",
    "EWD":  "https://www.ishares.com/us/products/239684/ishares-msci-sweden-etf",
    "EWS":  "https://www.ishares.com/us/products/239685/ishares-msci-switzerland-etf",
    "IWM":  "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf",
    "IJR":  "https://www.ishares.com/us/products/239774/ishares-core-sp-smallcap-etf",
    "QUAL": "https://www.ishares.com/us/products/256101/ishares-msci-usa-quality-factor-etf",
    "EFAV": "https://www.ishares.com/us/products/239626/ishares-msci-eafe-min-vol-factor-etf",
    "EWC":  "https://www.ishares.com/us/products/239615/ishares-msci-canada-etf",
    # Canada-listed BlackRock ETFs (blackrock.com/ca product pages)
    "XIC":  "https://www.blackrock.com/ca/investors/en/products/239837/ishares-sptsx-capped-composite-index-etf",
    "XMD":  "https://www.blackrock.com/ca/investors/en/products/239839/ishares-sptsx-midcap-index-etf",
    "XCS":  "https://www.blackrock.com/ca/investors/en/products/239840/ishares-sptsx-smallcap-index-etf",
}


# ─── Static Ticker Lists ──────────────────────────────────────────────────────
# Fallback for Nikkei 225 if the official CSV from indexes.nikkei.co.jp is unreachable.
# Updated periodically — last update: 2026-04
_NIKKEI_225_TICKERS = [
    "1332.T","1605.T","1721.T","1801.T","1802.T","1803.T","1808.T","1812.T","1925.T","1928.T",
    "1963.T","2002.T","2269.T","2282.T","2501.T","2502.T","2503.T","2531.T","2670.T","2768.T",
    "2801.T","2802.T","2871.T","2897.T","2914.T","3086.T","3088.T","3099.T","3289.T","3382.T",
    "3401.T","3402.T","3405.T","3407.T","3436.T","3659.T","3626.T","3861.T","3863.T","3865.T",
    "3904.T","4004.T","4005.T","4021.T","4042.T","4061.T","4063.T","4151.T","4183.T","4188.T",
    "4208.T","4324.T","4452.T","4502.T","4503.T","4506.T","4507.T","4519.T","4523.T","4568.T",
    "4578.T","4661.T","4664.T","4666.T","4684.T","4689.T","4704.T","4716.T","4739.T","4751.T",
    "4755.T","4768.T","4813.T","4901.T","4902.T","4911.T","4967.T","5001.T","5002.T","5019.T",
    "5020.T","5108.T","5101.T","5201.T","5214.T","5233.T","5301.T","5332.T","5333.T","5401.T",
    "5406.T","5411.T","5541.T","5631.T","5706.T","5711.T","5713.T","5714.T","5715.T","5801.T",
    "5802.T","5803.T","5819.T","5901.T","6098.T","6103.T","6113.T","6146.T","6178.T","6272.T",
    "6301.T","6302.T","6326.T","6367.T","6471.T","6479.T","6501.T","6503.T","6504.T","6506.T",
    "6574.T","6645.T","6674.T","6701.T","6702.T","6703.T","6723.T","6752.T","6753.T","6758.T",
    "6841.T","6857.T","6902.T","6920.T","6941.T","6952.T","6954.T","6971.T","6976.T","7004.T",
    "7011.T","7012.T","7013.T","7186.T","7201.T","7202.T","7203.T","7205.T","7211.T","7261.T",
    "7267.T","7269.T","7270.T","7272.T","7309.T","7453.T","7506.T","7518.T","7532.T","7550.T",
    "7731.T","7733.T","7735.T","7741.T","7751.T","7752.T","7762.T","7832.T","7845.T","7951.T",
    "7952.T","7974.T","7976.T","8001.T","8002.T","8015.T","8031.T","8035.T","8053.T","8058.T",
    "8098.T","8233.T","8252.T","8253.T","8267.T","8303.T","8304.T","8306.T","8308.T","8309.T",
    "8316.T","8331.T","8354.T","8355.T","8369.T","8411.T","8591.T","8601.T","8604.T","8628.T",
    "8630.T","8714.T","8725.T","8729.T","8750.T","8766.T","8795.T","8799.T","8801.T","8802.T",
    "8804.T","8830.T","8954.T","8964.T","8975.T","8977.T","9001.T","9005.T","9007.T","9008.T",
    "9009.T","9020.T","9021.T","9022.T","9064.T","9101.T","9104.T","9107.T","9147.T","9201.T",
    "9202.T","9301.T","9332.T","9366.T","9432.T","9433.T","9434.T","9437.T","9501.T","9502.T",
    "9503.T","9531.T","9532.T","9603.T","9613.T","9676.T","9681.T","9719.T","9735.T","9749.T",
    "9766.T","9843.T","9983.T","9984.T",
]


# ─── Wikipedia Fetching ───────────────────────────────────────────────────────

def _fetch_wikipedia_tickers(url: str) -> list[str]:
    import pandas as pd
    from io import StringIO
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    tables = pd.read_html(StringIO(r.text))
    for table in tables:
        for col in table.columns:
            col_lower = str(col).lower()
            if any(k in col_lower for k in ["symbol", "ticker", "code"]):
                series = table[col].dropna().astype(str)
                tickers = series.str.replace(".", "-").tolist()
                tickers = [t for t in tickers if t and t != "nan" and len(t) <= 10 and not t.startswith("Category")]
                if tickers:
                    return tickers
    return []


# ─── Nikkei Official CSV ─────────────────────────────────────────────────────
# Source priority for Nikkei 225 constituents:
#   1. Current-day components CSV — published daily, most up-to-date
#   2. Weights CSV (English) — official, updated less frequently
#   3. Hardcoded _NIKKEI_225_TICKERS list — last resort if both CSVs fail
# All sources are from Nikkei Inc. (indexes.nikkei.co.jp).
# Rebalanced semi-annually (April and October).

def _fetch_nikkei_csv_tickers(url: str) -> list[str]:
    """Fetch Nikkei 225 tickers from an official CSV, return as ['1234.T', ...].

    Robust to footer/note rows: only rows whose Code field is a pure digit
    string are included.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    tickers = []
    for row in reader:
        code = (row.get("Code") or row.get("code") or "").strip()
        if code and code.isdigit():
            tickers.append(f"{code}.T")
    return tickers


def _apply_suffix(tickers: list[str], suffix: str) -> list[str]:
    """Append yfinance suffix (e.g. '.TO' for TSX) to tickers that don't already have it."""
    if not suffix:
        return tickers
    return [t + suffix if not t.endswith(suffix) else t for t in tickers]


def _get_cached_tickers(index: str) -> list[str]:
    cache = Path(__file__).parent / "data" / f"{index}_tickers.json"
    if cache.exists():
        return json.loads(cache.read_text())
    return []


def _save_cached_tickers(index: str, tickers: list[str]):
    cache = Path(__file__).parent / "data" / f"{index}_tickers.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(tickers))


def refresh_index_cache(indexes: list[str] = None) -> dict[str, int | str]:
    """Refresh index caches. Returns {index: count} or {index: error}."""
    targets = indexes or list(INDEX_SOURCES.keys())
    results = {}
    for name in targets:
        src = INDEX_SOURCES.get(name)
        if not src:
            results[name] = "unknown index"
            continue
        try:
            # Nikkei: try components CSV → weights CSV → hardcoded list
            if src.get("csv_url") or src.get("csv_url_fallback"):
                tickers = []
                # 1) Primary: current-day components CSV
                if src.get("csv_url"):
                    try:
                        tickers = _fetch_nikkei_csv_tickers(src["csv_url"])
                    except Exception:
                        tickers = []
                # 2) Secondary: weights CSV
                if not tickers and src.get("csv_url_fallback"):
                    try:
                        tickers = _fetch_nikkei_csv_tickers(src["csv_url_fallback"])
                    except Exception:
                        tickers = []
                # 3) Last resort: hardcoded list
                if not tickers and src.get("static_tickers"):
                    static_map = {"nikkei225": _NIKKEI_225_TICKERS}
                    tickers = static_map.get(name, [])
            elif src.get("static_tickers"):
                static_map = {"nikkei225": _NIKKEI_225_TICKERS}
                tickers = static_map.get(name, [])
            else:
                tickers = _fetch_wikipedia_tickers(src["url"])
            if tickers:
                tickers = _apply_suffix(tickers, src.get("suffix", ""))
                _save_cached_tickers(name, tickers)
                results[name] = len(tickers)
            else:
                results[name] = "no tickers found"
        except Exception as e:
            results[name] = f"error: {e}"
    return results


def _fetch_ishares_holdings_csv(ticker: str) -> list[str]:
    """Download and parse the official iShares/BlackRock holdings CSV for *ticker*.

    Strategy:
      • US iShares (ishares.com): build the direct CSV URL from the product page URL.
      • Canada BlackRock (blackrock.com/ca): scrape the product page for the CSV href.
    The CSV files contain a preamble of metadata rows before the actual header row;
    we detect the header by looking for a "Ticker" column.
    """
    product_url = _ISHARES_PRODUCT_URLS.get(ticker)
    if product_url is None:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/125.0.0.0 Safari/537.36",
    }

    csv_url: str | None = None

    if "ishares.com/us/" in product_url:
        # Direct CSV pattern for US iShares:
        # <product_url>/1467271812596.ajax?fileType=csv&fileName=<TICKER>_holdings&dataType=fund
        csv_url = (
            f"{product_url}/1467271812596.ajax"
            f"?fileType=csv&fileName={ticker}_holdings&dataType=fund"
        )
    elif "blackrock.com/ca/" in product_url:
        # Scrape the product page for the holdings CSV link
        resp = requests.get(product_url, headers=headers, timeout=30)
        resp.raise_for_status()
        match = re.search(r'href="([^"]*?\.ajax\?fileType=csv[^"]*)"', resp.text)
        if match:
            href = match.group(1)
            csv_url = href if href.startswith("http") else f"https://www.blackrock.com{href}"

    if csv_url is None:
        return []

    resp = requests.get(csv_url, headers=headers, timeout=30)
    resp.raise_for_status()

    # Parse CSV — skip preamble lines until we find the header containing "Ticker"
    lines = resp.text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if "Ticker" in line:
            header_idx = i
            break
    if header_idx is None:
        return []

    reader = csv.DictReader(lines[header_idx:])
    symbols: list[str] = []
    for row in reader:
        raw = (row.get("Ticker") or "").strip()
        if not raw or raw == "-":
            continue
        # Basic validity: starts with a letter, only contains typical ticker chars
        if re.match(r"^[A-Za-z][A-Za-z0-9.\-]{0,15}$", raw):
            symbols.append(raw)
    return symbols


def refresh_etf_holdings(etfs: list[str] = None) -> dict[str, int | str]:
    """Fetch and cache ETF holdings from issuer CSV files (iShares/BlackRock)."""
    targets = etfs or list(ETF_SOURCES.keys())
    results: dict[str, int | str] = {}
    for etf_ticker in targets:
        if etf_ticker not in _ISHARES_PRODUCT_URLS:
            results[etf_ticker] = "unsupported issuer (no iShares/BlackRock source)"
            continue
        try:
            symbols = _fetch_ishares_holdings_csv(etf_ticker)
            if symbols:
                _save_cached_tickers(f"etf_{etf_ticker.lower()}", symbols)
                results[etf_ticker] = len(symbols)
            else:
                results[etf_ticker] = "no holdings found in CSV"
        except Exception as e:
            results[etf_ticker] = f"error: {e}"
    return results


# ─── IBKR Scanner ─────────────────────────────────────────────────────────────

def ibkr_scan(scanner_type: str = "high_margins") -> list[dict] | None:
    """Use IBKR's built-in scanner. Only works when opted in AND Gateway is connected."""
    if not os.environ.get("CSU_USE_IBKR", "").lower() in ("1", "true", "yes"):
        return None
    if not is_ib_available():
        return None
    # Ensure event loop exists (Streamlit thread compat)
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        from ib_insync import IB, ScannerSubscription
        ib = IB()
        connected = False
        for port in [7497, 7496, 4002, 4001]:
            try:
                ib.connect("127.0.0.1", port, clientId=11, timeout=5)
                connected = True
                break
            except Exception:
                continue
        if not connected:
            return None

        scan_configs = {
            "high_margins": ScannerSubscription(
                instrument="STK", locationCode="STK.US",
                scanCode="HIGH_GROSS_MARGIN", abovePrice=5, aboveVolume=100000,
            ),
            "high_dividend_yield": ScannerSubscription(
                instrument="STK", locationCode="STK.US",
                scanCode="HIGH_DIVIDEND_YIELD", abovePrice=5,
            ),
            "europe_high_margins": ScannerSubscription(
                instrument="STK", locationCode="STK.EUR",
                scanCode="HIGH_GROSS_MARGIN", abovePrice=5,
            ),
            "asia_high_margins": ScannerSubscription(
                instrument="STK", locationCode="STK.ASIA",
                scanCode="HIGH_GROSS_MARGIN", abovePrice=5,
            ),
        }
        scan = scan_configs.get(scanner_type, scan_configs["high_margins"])
        results = ib.reqScannerData(scan)
        ib.disconnect()

        companies = []
        for r in results:
            cd = r.contractDetails
            companies.append({
                "ticker": cd.contract.symbol,
                "name": cd.longName or cd.contract.symbol,
                "exchange": cd.contract.exchange,
                "currency": cd.contract.currency,
            })
        return companies
    except Exception:
        return None


# ─── Discovery Presets & Scans ────────────────────────────────────────────────

PRESETS = {
    "quality_compounders": {
        "description": "High FCF, stable, durable businesses",
        "indexes": ["sp500", "sp400"],
        "min_fcf_margin": 0.10,
        "min_gross_margin": 0.40,
        "min_market_cap_m": 500,
    },
    "deep_value": {
        "description": "Cheap on FCF yield, profitable",
        "indexes": ["sp400", "sp600"],
        "min_fcf_margin": 0.08,
        "min_gross_margin": 0.30,
        "min_market_cap_m": 200,
    },
    "wide_moat": {
        "description": "High margins, dominant businesses",
        "indexes": ["sp500"],
        "min_fcf_margin": 0.15,
        "min_gross_margin": 0.60,
        "min_market_cap_m": 1000,
    },
    "small_cap_quality": {
        "description": "Quality under the radar",
        "indexes": ["sp600", "sp400", "etf_iwm", "etf_scz"],
        "min_fcf_margin": 0.08,
        "min_gross_margin": 0.35,
        "min_market_cap_m": 200,
    },
    "europe_quality": {
        "description": "European quality compounders",
        "indexes": ["ftse100", "ftse250", "dax40", "cac40", "aex25", "ibex35", "ftse_mib", "smi20", "etf_ezu", "etf_vgk"],
        "min_fcf_margin": 0.08,
        "min_gross_margin": 0.35,
        "min_market_cap_m": 300,
    },
    "europe_small_cap": {
        "description": "European small/mid caps with quality",
        "indexes": ["ftse250", "mdax", "etf_scz", "etf_ewg", "etf_ewu", "etf_ewq", "etf_ewp", "etf_ewi"],
        "min_fcf_margin": 0.05,
        "min_gross_margin": 0.25,
        "min_market_cap_m": 100,
    },
    "canada_quality": {
        "description": "Canadian quality compounders (banks, rails, utilities, tech)",
        "indexes": ["tsx60", "tsx_composite", "etf_xic", "etf_ewc"],
        "min_fcf_margin": 0.08,
        "min_gross_margin": 0.35,
        "min_market_cap_m": 300,
    },
    "canada_small_cap": {
        "description": "Canadian small/mid caps with quality",
        "indexes": ["tsx_composite", "etf_xmd", "etf_xcs", "etf_ewc"],
        "min_fcf_margin": 0.05,
        "min_gross_margin": 0.25,
        "min_market_cap_m": 100,
    },
    "asia_pacific": {
        "description": "Asia-Pacific quality (Japan, Australia)",
        "indexes": ["nikkei225", "asx200"],
        "min_fcf_margin": 0.06,
        "min_gross_margin": 0.30,
        "min_market_cap_m": 300,
    },
    "full_universe": {
        "description": "All available tickers (slow!)",
        "indexes": list(INDEX_SOURCES.keys()),
        "min_fcf_margin": 0.05,
        "min_gross_margin": 0.25,
        "min_market_cap_m": 100,
    },
}


def run_discovery(preset: str = "quality_compounders",
                  batch_size: int = 20,
                  progress_callback=None) -> list[dict]:
    """Run discovery scan. Uses IBKR scanner when available, else index constituents."""
    p = PRESETS.get(preset, PRESETS["quality_compounders"])

    # If IBKR is available, try scanner first for relevant presets
    if is_ib_available() and preset in ["quality_compounders", "wide_moat"]:
        scan_type = "high_margins"
        ib_results = ibkr_scan(scan_type)
        if ib_results:
            results = []
            for i, comp in enumerate(ib_results[:batch_size]):
                if progress_callback:
                    progress_callback(i, min(batch_size, len(ib_results)), comp["ticker"])
                data = smart_fetch(comp["ticker"], discovery_mode=True)
                if data:
                    gm = data.get("gross_margin", 0) or 0
                    fm = data.get("fcf_margin") or 0
                    if gm >= p["min_gross_margin"] and fm >= p["min_fcf_margin"]:
                        scored = score_company(data)
                        if scored.get("total_score", 0) >= 12:
                            results.append(scored)
            results.sort(key=lambda x: x.get("total_score", 0), reverse=True)
            return results

    # Fallback: index constituents + yfinance
    all_tickers = []
    for idx_name in p["indexes"]:
        tickers = _get_cached_tickers(idx_name)
        if not tickers and idx_name.startswith("etf_"):
            etf_symbol = idx_name.replace("etf_", "").upper()
            holdings = _fetch_etf_holdings_simple(etf_symbol)
            if holdings:
                _save_cached_tickers(idx_name, holdings)
                tickers = holdings
        all_tickers.extend(tickers)

    seen = set()
    unique = []
    for t in all_tickers:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    # Skip already-scanned tickers (avoid re-scanning same companies)
    try:
        conn = get_db()
        already = {r[0] for r in conn.execute("SELECT ticker FROM scan_results").fetchall()}
        fresh = [t for t in unique if t not in already]
    except Exception:
        fresh = unique

    # Random sample from fresh tickers (don't always start from A)
    import random
    pool = fresh if len(fresh) >= batch_size else unique  # fallback if all scanned
    random.seed()  # true randomness each run
    sample_size = min(batch_size, len(pool))
    to_scan = random.sample(pool, sample_size)
    results = []
    for i, ticker in enumerate(to_scan):
        if progress_callback:
            progress_callback(i, len(to_scan), ticker)
        data = smart_fetch(ticker, discovery_mode=True)
        if not data:
            continue
        gm = data.get("gross_margin", 0) or 0
        fm = data.get("fcf_margin") or 0
        mc = data.get("market_cap_m", 0) or 0
        if gm < p["min_gross_margin"] or fm < p["min_fcf_margin"] or mc < p["min_market_cap_m"]:
            continue
        scored = score_company(data)
        if scored.get("total_score", 0) >= 12:
            results.append(scored)

    results.sort(key=lambda x: x.get("total_score", 0), reverse=True)
    return results


def _fetch_etf_holdings_simple(etf_ticker: str) -> list[str]:
    """Fetch ETF holdings from issuer CSV (iShares/BlackRock). Returns [] on failure."""
    try:
        return _fetch_ishares_holdings_csv(etf_ticker)
    except Exception:
        return []


def get_available_ticker_count(preset: str) -> int:
    p = PRESETS.get(preset, PRESETS["quality_compounders"])
    total = 0
    for idx_name in p["indexes"]:
        tickers = _get_cached_tickers(idx_name)
        total += len(tickers)
    return total


def get_index_stats() -> dict:
    stats = {}
    for idx in list(INDEX_SOURCES.keys()):
        tickers = _get_cached_tickers(idx)
        cache_file = Path(__file__).parent / "data" / f"{idx}_tickers.json"
        src = INDEX_SOURCES.get(idx, {})
        stats[idx] = {
            "cached": len(tickers),
            "cache_exists": cache_file.exists(),
            "label": src.get("label", idx),
            "region": src.get("region", "?"),
            "cap": src.get("cap", "?"),
        }
    for etf in ETF_SOURCES:
        tickers = _get_cached_tickers(f"etf_{etf.lower()}")
        cache_file = Path(__file__).parent / "data" / f"etf_{etf.lower()}_tickers.json"
        src = ETF_SOURCES.get(etf, {})
        stats[f"etf_{etf.lower()}"] = {
            "cached": len(tickers),
            "cache_exists": cache_file.exists(),
            "label": src.get("label", etf),
            "region": src.get("region", "?"),
            "cap": src.get("cap", "?"),
        }
    return stats
