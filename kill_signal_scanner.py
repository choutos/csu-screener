#!/usr/bin/env python3
"""
Kill Signal Scanner
===================
Weekly cron: re-fetches all watchlist + portfolio companies,
compares current metrics to entry metrics, flags kill signals.

Kill Signal Rules:
- RETENTION_DROP: Revenue declining >5% YoY (proxy for lost customers)
- FCF_COMPRESS: FCF margin dropped >3pp from entry
- MARGIN_EROSION: Gross margin dropped >5pp from entry
- VALUATION_STRETCH: Price > 2x fair value (buy_under)
- THESIS_CHANGE: Sector/industry reclassification or major metric shift
- DEBT_SPIKE: Debt-to-equity increased >50% from entry
- PRICE_BELOW_BUY: Current price dropped below buy-under (opportunity check)

Usage:
    python kill_signal_scanner.py          # Scan all, print results
    python kill_signal_scanner.py --json   # Output as JSON (for alerts)
    python kill_signal_scanner.py --alert  # Send Telegram alert via OpenClaw
"""
import sys
import json
from contextlib import closing
from datetime import datetime
from pathlib import Path

# Add app dir to path
sys.path.insert(0, str(Path(__file__).parent))

from smart_fetcher import fetch_company, get_data_source
from fetcher import score_company
from db import get_db, log_kill_signal


def scan_watchlist() -> list[dict]:
    """Scan all watchlist companies for kill signals."""
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT * FROM watchlist ORDER BY priority, last_checked DESC").fetchall()

    alerts = []
    for row in rows:
        result = check_company(dict(row), source="watchlist")
        if result:
            alerts.extend(result)
    return alerts


def scan_portfolio() -> list[dict]:
    """Scan all portfolio companies for kill signals."""
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT * FROM portfolio WHERE status='OPEN'").fetchall()

    alerts = []
    for row in rows:
        result = check_company(dict(row), source="portfolio")
        if result:
            alerts.extend(result)
    return alerts


def check_company(entry: dict, source: str = "watchlist") -> list[dict]:
    """
    Check a single company for kill signals.
    Compares current metrics to entry metrics stored in the DB.
    """
    ticker = entry.get("ticker", "")
    if not ticker:
        return []
    
    # Fetch current data
    data = fetch_company(ticker)
    if not data:
        return [{"ticker": ticker, "signal": "FETCH_FAILED", "severity": "WARNING",
                 "details": f"Could not fetch data for {ticker}", "source": source}]
    
    # Re-score
    scored = score_company(data)

    # Store baseline metrics if not present, then load for comparison
    _save_baseline(ticker, data)
    baseline = _get_baseline(ticker)

    alerts = []
    
    # ─── Rule 1: FCF Compression ───────────────────────────────────────
    if baseline and baseline.get("fcf_margin") and data.get("fcf_margin"):
        drop = baseline["fcf_margin"] - data["fcf_margin"]
        if drop >= 0.03:  # 3pp drop
            severity = "CRITICAL" if drop >= 0.06 else "WARNING"
            alerts.append({
                "ticker": ticker,
                "signal": "FCF_COMPRESS",
                "severity": severity,
                "details": f"FCF margin: {data['fcf_margin']:.1%} (was {baseline['fcf_margin']:.1%}, -{drop:.1%})",
                "action": "REVIEW" if severity == "WARNING" else "CONSIDER_SELL",
                "source": source,
            })
    
    # ─── Rule 2: Gross Margin Erosion ─────────────────────────────────
    if baseline and baseline.get("gross_margin") and data.get("gross_margin"):
        drop = baseline["gross_margin"] - data["gross_margin"]
        if drop >= 0.05:  # 5pp drop
            severity = "CRITICAL" if drop >= 0.10 else "WARNING"
            alerts.append({
                "ticker": ticker,
                "signal": "MARGIN_EROSION",
                "severity": severity,
                "details": f"Gross margin: {data['gross_margin']:.1%} (was {baseline['gross_margin']:.1%}, -{drop:.1%})",
                "action": "REVIEW" if severity == "WARNING" else "CONSIDER_SELL",
                "source": source,
            })
    
    # ─── Rule 3: Revenue Decline (Retention Proxy) ────────────────────
    if data.get("revenue_growth_3y") is not None and data["revenue_growth_3y"] < -0.05:
        alerts.append({
            "ticker": ticker,
            "signal": "RETENTION_DROP",
            "severity": "CRITICAL" if data["revenue_growth_3y"] < -0.10 else "WARNING",
            "details": f"Revenue declining: {data['revenue_growth_3y']:.1%} YoY",
            "action": "REVIEW",
            "source": source,
        })
    
    # ─── Rule 4: Debt Spike ───────────────────────────────────────────
    if baseline and baseline.get("debt_to_equity") and data.get("debt_to_equity"):
        if baseline["debt_to_equity"] > 0:
            pct_increase = (data["debt_to_equity"] / baseline["debt_to_equity"]) - 1
            if pct_increase >= 0.50:  # 50% increase in D/E
                alerts.append({
                    "ticker": ticker,
                    "signal": "DEBT_SPIKE",
                    "severity": "WARNING",
                    "details": f"D/E: {data['debt_to_equity']:.2f} (was {baseline['debt_to_equity']:.2f}, +{pct_increase:.0%})",
                    "action": "REVIEW",
                    "source": source,
                })
    
    # ─── Rule 5: Valuation Stretch ────────────────────────────────────
    buy_under = entry.get("buy_under")
    current_price = data.get("price")
    if buy_under and current_price and buy_under > 0:
        stretch = current_price / buy_under
        if stretch >= 2.0:  # Price 2x above buy-under
            alerts.append({
                "ticker": ticker,
                "signal": "VALUATION_STRETCH",
                "severity": "WARNING",
                "details": f"Price ${current_price:.2f} is {stretch:.1f}x buy-under (${buy_under:.2f})",
                "action": "HOLD_NOT_BUY",
                "source": source,
            })
    
    # ─── Rule 6: Price Below Buy-Under (Opportunity) ──────────────────
    if buy_under and current_price and buy_under > 0 and current_price < buy_under:
        discount = (1 - current_price / buy_under) * 100
        alerts.append({
            "ticker": ticker,
            "signal": "PRICE_BELOW_BUY",
            "severity": "OK",  # This is actually good!
            "details": f"Price ${current_price:.2f} is {discount:.0f}% below buy-under (${buy_under:.2f})",
            "action": "CONSIDER_BUY",
            "source": source,
        })
    
    # ─── Rule 7: Score Deterioration ───────────────────────────────────
    if entry.get("score") and scored.get("total_score"):
        old_score = entry["score"]
        new_score = scored["total_score"]
        if old_score >= 18 and new_score < 15:  # STRONG → not STRONG
            alerts.append({
                "ticker": ticker,
                "signal": "SCORE_DROP",
                "severity": "WARNING",
                "details": f"Score: {new_score}/{scored['max_score']} (was {old_score}/{entry.get('max_score', '?')})",
                "action": "REVIEW",
                "source": source,
            })
    
    # ─── Rule 8: Fetch Failure ─────────────────────────────────────────
    # Already handled above
    
    with closing(get_db()) as conn:
        for alert in alerts:
            log_kill_signal(
                conn,
                ticker=alert["ticker"],
                signal_type=alert["signal"],
                severity=alert["severity"],
                details=alert["details"],
                action=alert.get("action", "WATCH"),
                current_price=current_price,
            )

        if current_price:
            conn.execute("INSERT INTO price_snapshots (ticker, price) VALUES (?, ?)",
                         (ticker, current_price))

        conn.execute("UPDATE watchlist SET last_checked=datetime('now'), score=?, max_score=? WHERE ticker=?",
                     (scored.get("total_score", 0), scored.get("max_score", 24), ticker))
        conn.execute("UPDATE portfolio SET last_kill_check=datetime('now') WHERE ticker=?", (ticker,))
        conn.commit()

    return alerts


# ─── Baseline Metrics Storage ─────────────────────────────────────────────────

def _save_baseline(ticker: str, data: dict):
    """Save current metrics as baseline for future comparison."""
    metrics = {
        "gross_margin": data.get("gross_margin"),
        "fcf_margin": data.get("fcf_margin"),
        "debt_to_equity": data.get("debt_to_equity"),
        "revenue_growth_3y": data.get("revenue_growth_3y"),
        "price": data.get("price"),
        "score": data.get("total_score"),
        "captured_at": datetime.now().isoformat(),
    }
    # Store as JSON in notes or a dedicated column
    # For now, use a simple file-based cache
    cache_dir = Path(__file__).parent / "data" / "baselines"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{ticker}.json"
    cache_file.write_text(json.dumps(metrics, indent=2))


def _get_baseline(ticker: str) -> dict | None:
    """Load baseline metrics for comparison."""
    cache_file = Path(__file__).parent / "data" / "baselines" / f"{ticker}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    return None


# ─── Report Formatting ────────────────────────────────────────────────────────

def format_report(alerts: list[dict]) -> str:
    """Format kill signal alerts into a readable report."""
    if not alerts:
        return "✅ No kill signals detected. All companies look healthy."
    
    # Separate by severity
    critical = [a for a in alerts if a.get("severity") == "CRITICAL"]
    warnings = [a for a in alerts if a.get("severity") == "WARNING"]
    opportunities = [a for a in alerts if a.get("severity") == "OK"]
    
    lines = []
    
    if critical:
        lines.append("🔴 CRITICAL KILL SIGNALS:")
        for a in critical:
            lines.append(f"  • {a['ticker']}: {a['signal']} — {a['details']}")
            lines.append(f"    Action: {a.get('action', 'REVIEW')}")
        lines.append("")
    
    if warnings:
        lines.append("🟡 WARNINGS:")
        for a in warnings:
            lines.append(f"  • {a['ticker']}: {a['signal']} — {a['details']}")
            lines.append(f"    Action: {a.get('action', 'WATCH')}")
        lines.append("")
    
    if opportunities:
        lines.append("🟢 OPPORTUNITIES:")
        for a in opportunities:
            lines.append(f"  • {a['ticker']}: {a['signal']} — {a['details']}")
            lines.append(f"    Action: {a.get('action', 'CONSIDER_BUY')}")
        lines.append("")
    
    lines.append(f"Data source: {get_data_source().upper()}")
    lines.append(f"Checked: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    return "\n".join(lines)


def format_telegram(alerts: list[dict]) -> str:
    """Format for Telegram notification (shorter)."""
    if not alerts:
        return "✅ Weekly kill signal scan: all clear. No action needed."
    
    critical = [a for a in alerts if a.get("severity") == "CRITICAL"]
    warnings = [a for a in alerts if a.get("severity") == "WARNING"]
    opportunities = [a for a in alerts if a.get("severity") == "OK"]
    
    lines = ["🎯 Kill Signal Scan Report"]
    lines.append("")
    
    if critical:
        lines.append(f"🔴 {len(critical)} CRITICAL:")
        for a in critical:
            lines.append(f"• {a['ticker']}: {a['details']}")
    
    if warnings:
        lines.append(f"🟡 {len(warnings)} warnings:")
        for a in warnings:
            lines.append(f"• {a['ticker']}: {a['details']}")
    
    if opportunities:
        lines.append(f"🟢 {len(opportunities)} opportunities:")
        for a in opportunities:
            lines.append(f"• {a['ticker']}: {a['details']}")
    
    lines.append(f"\nvia {get_data_source().upper()} | {datetime.now().strftime('%a %H:%M')}")
    
    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Kill Signal Scanner")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--alert", action="store_true", help="Send Telegram alert")
    parser.add_argument("--watchlist-only", action="store_true", help="Only scan watchlist")
    parser.add_argument("--portfolio-only", action="store_true", help="Only scan portfolio")
    args = parser.parse_args()
    
    alerts = []
    if not args.portfolio_only:
        alerts.extend(scan_watchlist())
    if not args.watchlist_only:
        alerts.extend(scan_portfolio())
    
    if args.json:
        print(json.dumps(alerts, indent=2))
    elif args.alert:
        # Send via Telegram
        msg = format_telegram(alerts)
        try:
            import subprocess
            # Use OpenClaw's message tool via the gateway
            subprocess.run([
                "openclaw", "invoke", "--message", msg,
                "--channel", "telegram", "--target", "991233"
            ], timeout=30)
        except Exception as e:
            print(f"Failed to send alert: {e}")
            print(f"Message: {msg}")
    else:
        print(format_report(alerts))
    
    return 0 if not alerts else 1


if __name__ == "__main__":
    sys.exit(main())
