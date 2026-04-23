"""
Investment Process App — LLM Advisor
Generates thesis, kill signals, and buy-under guidance using an LLM.
Supports any OpenAI-compatible API (ollama, litellm proxy, etc.)
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent / "llm_config.json"

DEFAULT_CONFIG = {
    "provider": "ollama",
    "base_url": "http://localhost:11434/v1",
    "model": "glm-5.1:cloud",
    "api_key": "",
    "enabled": True,
}


def load_config() -> dict:
    """Load LLM config from disk, falling back to defaults."""
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                saved = json.load(f)
            # Merge with defaults for any missing keys
            cfg = {**DEFAULT_CONFIG, **saved}
            return cfg
    except Exception as e:
        logger.warning(f"Failed to load LLM config: {e}")
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    """Save LLM config to disk."""
    # Only save known keys
    clean = {k: cfg.get(k, DEFAULT_CONFIG[k]) for k in DEFAULT_CONFIG}
    with open(CONFIG_PATH, "w") as f:
        json.dump(clean, f, indent=2)


# ─── LLM Client ──────────────────────────────────────────────────────────────

def _call_llm(system_prompt: str, user_prompt: str, config: dict = None) -> Optional[str]:
    """Call the LLM via OpenAI-compatible API. Returns the response text."""
    cfg = config or load_config()
    
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package not installed. Run: pip install openai")
        return None
    
    base_url = cfg["base_url"].rstrip("/")
    api_key = cfg.get("api_key") or "ollama"  # ollama doesn't need a real key
    
    client = OpenAI(base_url=base_url, api_key=api_key)
    
    try:
        response = client.chat.completions.create(
            model=cfg["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return None


# ─── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an investment analyst specializing in quality compounders — companies with 
durable competitive advantages, high retention, and strong cash generation. Your framework is 
inspired by Compound Stock Theory (CSU-like): look for low customer cost concentration, high 
switching costs, recurring revenue, and mission-critical products.

You must respond ONLY with valid JSON — no markdown, no commentary, no code fences."""

USER_PROMPT_TEMPLATE = """Analyze this company for a quality compounder portfolio:

Ticker: {ticker}
Name: {name}
Sector: {sector} / {industry}
Market Cap: ${market_cap_m:,.0f}M
Price: ${price}
Currency: {currency}

Key Metrics:
- Gross Margin: {gross_margin}
- FCF Margin: {fcf_margin}
- FCF Yield: {fcf_yield}
- Revenue Growth (3Y): {revenue_growth_3y}
- Debt/Equity: {debt_to_equity}
- Revenue Volatility: {revenue_volatility}

Quality Score: {total_score}/{max_score} ({csu_fit})

Generate a JSON response with EXACTLY these keys:
{{
  "thesis": "2-3 sentence investment thesis: WHY this is a quality compounder. What's the moat? What makes it resilient?",
  "kill_signals": "2-3 specific kill signals: WHAT would make you sell? Be concrete (e.g., 'customer churn exceeds 5%', 'gross margin drops below 60%')",
  "buy_under_reasoning": "Brief reasoning for the buy-under price based on FCF and margins",
  "suggested_buy_under": <number or null>
}}

Be specific to THIS company — not generic. Reference the actual metrics above."""


# ─── Public API ──────────────────────────────────────────────────────────────

def generate_analysis(data: dict, config: dict = None) -> Optional[dict]:
    """
    Generate thesis, kill signals, and buy-under price using LLM.
    
    Args:
        data: Company data dict (from smart_fetcher or score_company)
        config: Optional LLM config override
    
    Returns:
        dict with keys: thesis, kill_signals, buy_under (float or None), buy_under_reasoning (str)
        None if LLM is unavailable or fails
    """
    cfg = config or load_config()
    if not cfg.get("enabled", True):
        return None
    
    # Format the prompt with available data
    fmt_data = {
        "ticker": data.get("ticker", "?"),
        "name": data.get("name", "?"),
        "sector": data.get("sector", "?"),
        "industry": data.get("industry", "?"),
        "market_cap_m": data.get("market_cap_m", 0) or 0,
        "price": data.get("price", "?"),
        "currency": data.get("currency", "USD"),
        "gross_margin": f"{data.get('gross_margin', 0) or 0:.0%}" if data.get("gross_margin") is not None else "N/A",
        "fcf_margin": f"{data.get('fcf_margin', 0) or 0:.0%}" if data.get("fcf_margin") is not None else "N/A",
        "fcf_yield": f"{data.get('fcf_yield', 0) or 0:.1%}" if data.get("fcf_yield") is not None else "N/A",
        "revenue_growth_3y": f"{data.get('revenue_growth_3y', 0) or 0:.0%}" if data.get("revenue_growth_3y") is not None else "N/A",
        "debt_to_equity": f"{data.get('debt_to_equity', 0) or 0:.2f}" if data.get("debt_to_equity") is not None else "N/A",
        "revenue_volatility": f"{data.get('revenue_volatility', 0) or 0:.1%}" if data.get("revenue_volatility") is not None else "N/A",
        "total_score": data.get("total_score", "?"),
        "max_score": data.get("max_score", "?"),
        "csu_fit": data.get("csu_fit", "?"),
    }
    
    user_prompt = USER_PROMPT_TEMPLATE.format(**fmt_data)
    
    raw = _call_llm(SYSTEM_PROMPT, user_prompt, cfg)
    if not raw:
        return None
    
    # Parse the response — strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Remove first and last line
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON in the response
        import re
        match = re.search(r'\{[^{}]*\}', cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning(f"Could not parse LLM response as JSON: {raw[:200]}")
                return None
        else:
            logger.warning(f"No JSON found in LLM response: {raw[:200]}")
            return None
    
    # Extract and validate fields
    result = {
        "thesis": parsed.get("thesis", ""),
        "kill_signals": parsed.get("kill_signals", ""),
        "buy_under_reasoning": parsed.get("buy_under_reasoning", ""),
    }
    
    # Buy-under: prefer LLM suggestion, but validate it's reasonable
    suggested = parsed.get("suggested_buy_under")
    current_price = data.get("price")
    if suggested and isinstance(suggested, (int, float)) and suggested > 0:
        # Sanity check: buy-under should be within 50-120% of current price
        if current_price and abs(suggested - current_price) / current_price < 0.5:
            result["buy_under"] = round(float(suggested), 2)
        else:
            result["buy_under"] = None
    else:
        result["buy_under"] = None
    
    return result


def test_connection(config: dict = None) -> tuple[bool, str]:
    """Test the LLM connection. Returns (success, message)."""
    cfg = config or load_config()
    
    try:
        from openai import OpenAI
    except ImportError:
        return False, "openai package not installed. Run: pip install openai"
    
    base_url = cfg["base_url"].rstrip("/")
    api_key = cfg.get("api_key") or "ollama"
    
    try:
        client = OpenAI(base_url=base_url, api_key=api_key)
        response = client.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=10,
            temperature=0,
        )
        text = response.choices[0].message.content.strip()
        return True, f"Connected! Model: {cfg['model']}, Response: {text}"
    except Exception as e:
        return False, f"Connection failed: {e}"
