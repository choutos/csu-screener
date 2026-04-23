"""
Investment Process App — Data Fetcher
Fetches company data from Yahoo Finance and scores against quality criteria.
Broader than CSU — applicable to any sector with durable competitive advantages.
"""
import yfinance as yf
from datetime import datetime


def fetch_company(ticker_str: str) -> dict | None:
    """Fetch financial data for a single ticker."""
    try:
        t = yf.Ticker(ticker_str)
        info = t.info
        if not info or info.get("regularMarketPrice") is None:
            return None

        name = info.get("longName") or info.get("shortName") or ticker_str
        market_cap = info.get("marketCap", 0) or 0
        total_revenue = info.get("totalRevenue", 0) or 0

        # FCF
        fcf_margin = fcf_yield = fcf_absolute = None
        try:
            cf = t.cashflow
            if cf is not None and not cf.empty and "Free Cash Flow" in cf.index:
                fcf_val = cf.loc["Free Cash Flow"]
                if fcf_val is not None and not fcf_val.empty:
                    fcf_absolute = fcf_val.iloc[0]
                    if total_revenue and total_revenue > 0:
                        fcf_margin = fcf_absolute / total_revenue
                    if fcf_absolute and market_cap and market_cap > 0:
                        fcf_yield = fcf_absolute / market_cap
        except Exception:
            pass

        # Revenue growth
        revenue_growth = None
        try:
            income = t.financials
            if income is not None and not income.empty and "Total Revenue" in income.index:
                rev = income.loc["Total Revenue"]
                if len(rev) >= 2 and rev.iloc[-1] > 0:
                    revenue_growth = (rev.iloc[0] / rev.iloc[-1]) ** (1 / (len(rev) - 1)) - 1
        except Exception:
            pass

        # Revenue volatility
        revenue_volatility = None
        try:
            income = t.financials
            if income is not None and not income.empty and "Total Revenue" in income.index:
                rev = income.loc["Total Revenue"].dropna()
                if len(rev) >= 3 and rev.mean() != 0:
                    revenue_volatility = float(rev.std() / rev.mean())
        except Exception:
            pass

        # EBIT margin
        ebit_margin = info.get("operatingMargins", 0) or 0

        return {
            "ticker": ticker_str,
            "name": name,
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "market_cap_m": round(market_cap / 1e6, 1),
            "price": info.get("regularMarketPrice"),
            "currency": info.get("currency", "USD"),
            "gross_margin": round(info.get("grossMargins", 0) or 0, 3),
            "ebit_margin": round(ebit_margin, 3) if ebit_margin else None,
            "fcf_margin": round(fcf_margin, 3) if fcf_margin is not None else None,
            "fcf_yield": round(fcf_yield, 4) if fcf_yield is not None else None,
            "debt_to_equity": round((info.get("debtToEquity", 0) or 0) / 100, 2),
            "revenue_growth_3y": round(revenue_growth, 3) if revenue_growth is not None else None,
            "revenue_volatility": round(revenue_volatility, 3) if revenue_volatility is not None else None,
            "pe_ratio": info.get("trailingPE"),
            "fetched_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return None


def score_company(data: dict) -> dict:
    """
    Score against quality criteria — broader than CSU.
    Any company with durable competitive advantage, high retention,
    low % of customer costs, and strong cash generation can score well.
    """
    scores = {}
    passes = {}

    # 1. FCF Margin
    v = data.get("fcf_margin")
    if v is not None:
        scores["fcf_margin"] = 3 if v >= 0.20 else (2 if v >= 0.10 else (1 if v >= 0.05 else 0))
        passes["fcf_margin"] = v >= 0.10

    # 2. Gross Margin
    v = data.get("gross_margin")
    if v is not None:
        scores["gross_margin"] = 3 if v >= 0.70 else (2 if v >= 0.50 else (1 if v >= 0.30 else 0))
        passes["gross_margin"] = v >= 0.40  # Broader than CSU — industrials with 40%+ can qualify

    # 3. Revenue Stability
    v = data.get("revenue_volatility")
    if v is not None:
        scores["revenue_stability"] = 3 if v <= 0.10 else (2 if v <= 0.20 else (1 if v <= 0.30 else 0))
        passes["revenue_stability"] = v <= 0.25

    # 4. Growth Profile
    v = data.get("revenue_growth_3y")
    if v is not None:
        scores["growth_profile"] = 3 if 0.02 <= v <= 0.15 else (2 if v <= 0.02 else (1 if v <= 0.25 else 0))
        passes["growth_profile"] = -0.05 <= v <= 0.25  # Broader range

    # 5. FCF Yield
    v = data.get("fcf_yield")
    if v is not None:
        scores["fcf_yield"] = 3 if v >= 0.05 else (2 if v >= 0.03 else (1 if v >= 0.02 else 0))
        passes["fcf_yield"] = v >= 0.02

    # 6. Debt Discipline
    v = data.get("debt_to_equity")
    if v is not None:
        scores["debt_discipline"] = 3 if v <= 0.5 else (2 if v <= 1.0 else (1 if v <= 2.0 else 0))
        passes["debt_discipline"] = v <= 2.0

    # 7. Size Fit
    v = data.get("market_cap_m")
    if v is not None:
        scores["size_fit"] = 3 if 500 <= v <= 10000 else (2 if 200 <= v < 500 or 10000 < v <= 50000 else 1)
        passes["size_fit"] = v >= 200

    # 8. Moat Quality (sector-aware heuristic)
    # High-margin industries = likely moat; low-margin = need to prove it
    industry = data.get("industry", "").lower()
    sector = data.get("sector", "").lower()
    gm = data.get("gross_margin", 0) or 0
    
    if gm >= 0.60:
        scores["moat_quality"] = 3
        passes["moat_quality"] = True
    elif gm >= 0.40:
        scores["moat_quality"] = 2
        passes["moat_quality"] = True
    elif any(kw in sector for kw in ["industrial", "energy", "material", "real estate"]):
        scores["moat_quality"] = 2  # Capital-intensive sectors get a pass on gross margin
        passes["moat_quality"] = True
    else:
        scores["moat_quality"] = 0
        passes["moat_quality"] = False

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
