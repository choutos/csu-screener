"""
Investment Process App
=======================
Three dashboards: Portfolio, Watchlist, Scanner.
Run: streamlit run app.py
"""
import streamlit as st
from db import get_db, add_to_portfolio, add_to_watchlist, move_to_portfolio, move_to_watchlist, remove_from_watchlist, remove_from_portfolio, log_kill_signal, update_portfolio_status, upsert_scan
from fetcher import fetch_company, score_company
import pandas as pd
from datetime import datetime

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Invest Process", page_icon="🎩", layout="wide")

# ─── Sidebar ──────────────────────────────────────────────────────────────────
page = st.sidebar.radio("📐 Dashboard", ["📊 Portfolio", "👀 Watchlist", "🔍 Scanner", "⚙️ Settings"])
st.sidebar.markdown("---")
st.sidebar.markdown("*Investment Process App*\n🎩")

# ─── Portfolio Dashboard ─────────────────────────────────────────────────────
if page == "📊 Portfolio":
    st.title("📊 Portfolio")
    st.caption("Track holdings, monitor kill signals, decide HOLD / SELL / BUY MORE")
    
    conn = get_db()
    rows = conn.execute("SELECT * FROM portfolio ORDER BY updated_at DESC").fetchall()
    
    if not rows:
        st.info("No positions yet. Add from the Watchlist or Scanner.")
        with st.expander("➕ Add position manually"):
            with st.form("add_portfolio"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    ticker = st.text_input("Ticker").upper()
                    name = st.text_input("Company Name")
                with col2:
                    buy_price = st.number_input("Buy Price", min_value=0.0, step=0.01)
                    shares = st.number_input("Shares", min_value=0.0, step=0.1)
                    buy_date = st.date_input("Buy Date", value=datetime.now())
                with col3:
                    sector = st.text_input("Sector")
                    industry = st.text_input("Industry")
                
                thesis = st.text_area("Thesis (why do you own this?)")
                kill_signals = st.text_area("Kill Signals (what would make you sell?)")
                
                if st.form_submit_button("Add to Portfolio") and ticker:
                    add_to_portfolio(conn, ticker, name, buy_price,
                                     str(buy_date), shares, thesis, kill_signals,
                                     sector=sector, industry=industry)
                    st.success(f"Added {ticker}")
                    st.rerun()
    else:
        # Summary metrics
        total_positions = len(rows)
        statuses = {}
        for r in rows:
            s = r["status"]
            statuses[s] = statuses.get(s, 0) + 1
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Positions", total_positions)
        col2.metric("HOLD", statuses.get("HOLD", 0))
        col3.metric("SELL", statuses.get("SELL", 0))
        col4.metric("BUY MORE", statuses.get("BUY_MORE", 0))
        
        st.markdown("---")
        
        # Position cards
        for row in rows:
            status_emoji = {"HOLD": "🟢", "SELL": "🔴", "BUY_MORE": "🔵"}.get(row["status"], "⚪")
            score_pct = round(row["score"] / row["max_score"] * 100) if row["max_score"] else 0
            
            with st.container(border=True):
                header_col, status_col, action_col = st.columns([3, 1, 1])
                with header_col:
                    st.subheader(f"{status_emoji} {row['ticker']} — {row['name']}")
                    st.caption(f"{row['sector']} / {row['industry']}")
                
                with status_col:
                    new_status = st.selectbox(
                        "Status", ["HOLD", "SELL", "BUY_MORE"],
                        index=["HOLD", "SELL", "BUY_MORE"].index(row["status"]),
                        key=f"status_{row['ticker']}"
                    )
                    if new_status != row["status"]:
                        update_portfolio_status(conn, row["ticker"], new_status)
                        st.rerun()
                
                with action_col:
                    if st.button("🗑️ Remove", key=f"rm_{row['ticker']}"):
                        remove_from_portfolio(conn, row["ticker"])
                        st.rerun()
                
                # Details
                det_col1, det_col2, det_col3 = st.columns(3)
                with det_col1:
                    if row["buy_price"]:
                        st.write(f"**Buy Price:** ${row['buy_price']:.2f}")
                    if row["shares"]:
                        st.write(f"**Shares:** {row['shares']}")
                    if row["buy_date"]:
                        st.write(f"**Buy Date:** {row['buy_date']}")
                
                with det_col2:
                    st.write(f"**Score:** {row['score']}/{row['max_score']} ({score_pct}%)")
                    if row["last_kill_check"]:
                        st.write(f"**Last Kill Check:** {row['last_kill_check'][:10]}")
                
                with det_col3:
                    if row["thesis"]:
                        st.write(f"**Thesis:** {row['thesis'][:100]}{'...' if len(row['thesis'])>100 else ''}")
                
                # Kill signals
                if row["kill_signals"]:
                    with st.expander("⚠️ Kill Signals"):
                        st.write(row["kill_signals"])
                
                # Kill signal check
                with st.expander("🔍 Run Kill Signal Check"):
                    with st.form(f"kill_{row['ticker']}"):
                        signal_type = st.selectbox("Signal Type", [
                            "RETENTION_DROP", "FCF_COMPRESS", "VOLATILITY_SPIKE",
                            "THESIS_CHANGE", "MGMT_TURNOVER", "VALUATION_STRETCH", "OTHER"
                        ])
                        severity = st.selectbox("Severity", ["OK", "WARNING", "CRITICAL"])
                        details = st.text_area("Details")
                        action = st.selectbox("Action", ["HOLD", "SELL", "BUY_MORE", "WATCH"])
                        
                        if st.form_submit_button("Log Signal"):
                            log_kill_signal(conn, row["ticker"], signal_type, severity, details, action)
                            update_portfolio_status(conn, row["ticker"], action)
                            st.success("Logged!")
                            st.rerun()
                
                # Recent kill signal history
                kill_logs = conn.execute(
                    "SELECT * FROM kill_signal_log WHERE ticker=? ORDER BY check_date DESC LIMIT 3",
                    (row["ticker"],)
                ).fetchall()
                if kill_logs:
                    for kl in kill_logs:
                        sev_emoji = {"OK": "✅", "WARNING": "⚠️", "CRITICAL": "🔴"}.get(kl["severity"], "⚪")
                        st.caption(f"{sev_emoji} {kl['check_date'][:10]} — {kl['signal_type']}: {kl['details'][:80] if kl['details'] else ''} → {kl['action']}")
    
    conn.close()


# ─── Watchlist Dashboard ─────────────────────────────────────────────────────
elif page == "👀 Watchlist":
    st.title("👀 Watchlist")
    st.caption("Companies you're tracking. Buy when price hits your target.")
    
    conn = get_db()
    rows = conn.execute("SELECT * FROM watchlist ORDER BY priority, last_checked DESC").fetchall()
    
    if not rows:
        st.info("Watchlist is empty. Add from the Scanner or manually.")
    
    with st.expander("➕ Add to Watchlist"):
        with st.form("add_watchlist"):
            col1, col2 = st.columns(2)
            with col1:
                wt = st.text_input("Ticker").upper()
                wn = st.text_input("Company Name")
                wb = st.number_input("Buy Under ($)", min_value=0.0, step=1.0)
            with col2:
                wp = st.selectbox("Priority", ["HIGH", "MEDIUM", "LOW"])
                wsect = st.text_input("Sector")
                wind = st.text_input("Industry")
            
            w_thesis = st.text_area("Thesis")
            w_kill = st.text_area("Kill Signals")
            
            if st.form_submit_button("Add") and wt:
                add_to_watchlist(conn, wt, wn, wb, priority=wp,
                                 thesis=w_thesis, kill_signals=w_kill,
                                 sector=wsect, industry=wind)
                st.success(f"Added {wt}")
                st.rerun()
    
    if rows:
        for row in rows:
            pri_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(row["priority"], "⚪")
            score_pct = round(row["score"] / row["max_score"] * 100) if row["max_score"] else 0
            
            with st.container(border=True):
                hcol, acol = st.columns([4, 1])
                with hcol:
                    st.subheader(f"{pri_emoji} {row['ticker']} — {row['name']}")
                    st.caption(f"{row['sector']} / {row['industry']} | Score: {row['score']}/{row['max_score']} ({score_pct}%) | Tracked since: {row['first_tracked'][:10] if row['first_tracked'] else '?'}")
                
                with acol:
                    st.write("")  # spacer
                
                # Key info
                col1, col2, col3 = st.columns(3)
                with col1:
                    if row["buy_under"]:
                        st.write(f"**🎯 Buy Under:** ${row['buy_under']:.2f}")
                    else:
                        st.write("**🎯 Buy Under:** Not set")
                with col2:
                    if row["thesis"]:
                        st.write(f"**Thesis:** {row['thesis'][:80]}{'...' if len(row['thesis'])>80 else ''}")
                with col3:
                    if row["kill_signals"]:
                        st.write(f"**Kill Signals:** {row['kill_signals'][:80]}{'...' if len(row['kill_signals'])>80 else ''}")
                
                # Actions
                acol1, acol2, acol3, acol4 = st.columns(4)
                with acol1:
                    if st.button(f"📈 Buy → Portfolio", key=f"buy_{row['ticker']}"):
                        buy_price = st.session_state.get(f"bp_{row['ticker']}", 0)
                        move_to_portfolio(conn, row["ticker"])
                        st.success(f"Moved {row['ticker']} to portfolio!")
                        st.rerun()
                with acol2:
                    if st.button(f"🔄 Refresh Data", key=f"ref_{row['ticker']}"):
                        with st.spinner(f"Fetching {row['ticker']}..."):
                            data = fetch_company(row["ticker"])
                            if data:
                                scored = score_company(data)
                                upsert_scan(conn, scored)
                                conn.execute("UPDATE watchlist SET score=?, max_score=?, last_checked=datetime('now'), updated_at=datetime('now') WHERE ticker=?",
                                             (scored["total_score"], scored["max_score"], row["ticker"]))
                                st.rerun()
                with acol3:
                    if st.button(f"🗑️ Remove", key=f"wr_{row['ticker']}"):
                        remove_from_watchlist(conn, row["ticker"])
                        st.rerun()
                with acol4:
                    # Quick update buy-under
                    new_bu = st.number_input("Buy Under", value=float(row["buy_under"]) if row["buy_under"] else 0.0,
                                             key=f"bu_{row['ticker']}", step=1.0)
                    if new_bu != (row["buy_under"] or 0) and new_bu > 0:
                        conn.execute("UPDATE watchlist SET buy_under=?, updated_at=datetime('now') WHERE ticker=?",
                                     (new_bu, row["ticker"]))
                        conn.commit()
    
    conn.close()


# ─── Scanner Dashboard ────────────────────────────────────────────────────────
elif page == "🔍 Scanner":
    st.title("🔍 Scanner")
    st.caption("Discover new investment candidates. Not limited to software.")
    
    conn = get_db()
    
    # Quick scan
    st.subheader("Quick Scan")
    scan_tickers = st.text_input("Enter tickers (comma-separated)", placeholder="AAPL, MSFT, BRK-B")
    
    if st.button("🚀 Scan") and scan_tickers:
        tickers = [t.strip().upper() for t in scan_tickers.split(",") if t.strip()]
        progress = st.progress(0)
        results = []
        
        for i, t in enumerate(tickers):
            with st.spinner(f"Fetching {t}..."):
                data = fetch_company(t)
                if data:
                    scored = score_company(data)
                    upsert_scan(conn, scored)
                    results.append(scored)
            progress.progress((i + 1) / len(tickers))
        
        if results:
            st.success(f"Scanned {len(results)} companies")
            for r in sorted(results, key=lambda x: x.get("total_score", 0), reverse=True):
                fit_emoji = {"STRONG": "🟢", "MODERATE": "🟡", "WEAK": "🟠", "NOT FIT": "🔴"}.get(r.get("csu_fit"), "⚪")
                st.write(f"{fit_emoji} **{r['ticker']}** — {r['name']} | Score: {r.get('total_score',0)}/{r.get('max_score','?')} | {r.get('csu_fit','?')}")
    
    st.markdown("---")
    
    # Previous scan results
    st.subheader("Previous Scan Results")
    scan_rows = conn.execute("""
        SELECT * FROM scan_results 
        ORDER BY score DESC, scanned_at DESC
    """).fetchall()
    
    if scan_rows:
        # Filter controls
        col1, col2 = st.columns(2)
        with col1:
            fit_filter = st.multiselect("Fit", ["STRONG", "MODERATE", "WEAK", "NOT FIT"], default=["STRONG", "MODERATE"])
        with col2:
            sector_filter = st.selectbox("Sector", ["All"] + list(set(r["sector"] for r in scan_rows if r["sector"])))
        
        filtered = scan_rows
        if fit_filter:
            filtered = [r for r in filtered if r["csu_fit"] in fit_filter]
        if sector_filter != "All":
            filtered = [r for r in filtered if r["sector"] == sector_filter]
        
        # Display as table
        if filtered:
            df = pd.DataFrame(filtered)
            display_cols = ["ticker", "name", "sector", "industry", "score", "max_score", "csu_fit", "price", "fcf_yield", "gross_margin", "in_portfolio", "in_watchlist"]
            available_cols = [c for c in display_cols if c in df.columns]
            st.dataframe(df[available_cols], use_container_width=True, hide_index=True)
            
            # Actions on selected ticker
            st.subheader("Take Action")
            action_ticker = st.selectbox("Select Ticker", [r["ticker"] for r in filtered])
            selected = next((r for r in filtered if r["ticker"] == action_ticker), None)
            
            if selected:
                acol1, acol2 = st.columns(2)
                with acol1:
                    buy_under = st.number_input("Buy Under Price", value=0.0, step=1.0, key="scan_bu")
                    if st.button("👀 Add to Watchlist"):
                        add_to_watchlist(conn, action_ticker, selected["name"],
                                        buy_under if buy_under > 0 else None,
                                        selected["score"], selected["max_score"],
                                        source="scan", sector=selected["sector"],
                                        industry=selected["industry"])
                        upsert_scan(conn, dict(selected))  # refresh
                        conn.execute("UPDATE scan_results SET in_watchlist=1 WHERE ticker=?", (action_ticker,))
                        st.success(f"Added {action_ticker} to watchlist!")
                        st.rerun()
                
                with acol2:
                    if st.button("📈 Add to Portfolio"):
                        add_to_portfolio(conn, action_ticker, selected["name"],
                                        sector=selected["sector"], industry=selected["industry"],
                                        score=selected["score"], max_score=selected["max_score"])
                        upsert_scan(conn, dict(selected))
                        conn.execute("UPDATE scan_results SET in_portfolio=1 WHERE ticker=?", (action_ticker,))
                        st.success(f"Added {action_ticker} to portfolio!")
                        st.rerun()
        else:
            st.info("No results match filters.")
    else:
        st.info("No scan results yet. Run a scan above.")
    
    conn.close()


# ─── Settings ─────────────────────────────────────────────────────────────────
elif page == "⚙️ Settings":
    st.title("⚙️ Settings")
    
    conn = get_db()
    
    st.subheader("Database Stats")
    p_count = conn.execute("SELECT COUNT(*) FROM portfolio").fetchone()[0]
    w_count = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
    s_count = conn.execute("SELECT COUNT(*) FROM scan_results").fetchone()[0]
    k_count = conn.execute("SELECT COUNT(*) FROM kill_signal_log").fetchone()[0]
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Portfolio", p_count)
    col2.metric("Watchlist", w_count)
    col3.metric("Scanned", s_count)
    col4.metric("Kill Signal Logs", k_count)
    
    st.markdown("---")
    
    st.subheader("Bulk Import from Screener")
    st.caption("Import tickers from the csu-screener watchlist.json")
    
    if st.button("Import Watchlist from Screener"):
        import json
        from pathlib import Path
        wl_path = Path(__file__).parent.parent / "screener" / "watchlist.json"
        if wl_path.exists():
            with open(wl_path) as f:
                wl = json.load(f)
            imported = 0
            for ticker, name in wl.items():
                existing = conn.execute("SELECT ticker FROM watchlist WHERE ticker=?", (ticker,)).fetchone()
                if not existing:
                    add_to_watchlist(conn, ticker, name, priority="MEDIUM", source="screener_import")
                    imported += 1
            st.success(f"Imported {imported} new tickers to watchlist. ({len(wl) - imported} already existed)")
        else:
            st.error("watchlist.json not found")
    
    st.markdown("---")
    
    st.subheader("Seed Deep-Dive Picks")
    st.caption("Add the top picks from the deep-dive analysis to watchlist with buy-under prices")
    
    seed_data = {
        "JKHY": {"name": "Jack Henry & Associates", "buy_under": 150, "priority": "HIGH", "thesis": "99%+ retention, regulatory moat, closest CSU archetype in public markets"},
        "SSNC": {"name": "SS&C Technologies", "buy_under": 60, "priority": "HIGH", "thesis": "8.5% FCF yield, 97% retention, serial acquirer, AI-resistant"},
        "VEEV": {"name": "Veeva Systems", "buy_under": 140, "priority": "MEDIUM", "thesis": "Pharma regulatory moat, mission-critical, but expensive"},
        "PTC":  {"name": "PTC Inc", "buy_under": 120, "priority": "MEDIUM", "thesis": "Industrial CAD/PLM lock-in, 5% FCF yield"},
        "KEYS": {"name": "Keysight Technologies", "buy_under": 250, "priority": "LOW", "thesis": "Physics-based moat, cyclical trough, wait for FCF recovery"},
        "MANH": {"name": "Manhattan Associates", "buy_under": 100, "priority": "MEDIUM", "thesis": "Best WMS but 55x earnings, need correction"},
        "FDS":  {"name": "FactSet", "buy_under": 200, "priority": "LOW", "thesis": "Data moat, AI risk is real, 91% retention"},
        "PAYX": {"name": "Paychex", "buy_under": 80, "priority": "LOW", "thesis": "43% FCF margin, SMB payroll, defensive"},
    }
    
    if st.button("Seed Watchlist"):
        for ticker, info in seed_data.items():
            existing = conn.execute("SELECT ticker FROM watchlist WHERE ticker=?", (ticker,)).fetchone()
            if not existing:
                add_to_watchlist(conn, ticker, info["name"], info["buy_under"],
                                priority=info["priority"], thesis=info["thesis"], source="deep_dive")
        st.success(f"Seeded {len(seed_data)} tickers to watchlist!")
        st.rerun()
    
    st.markdown("---")
    
    st.subheader("Danger Zone")
    if st.button("🗑️ Clear All Scan Results"):
        conn.execute("DELETE FROM scan_results")
        conn.commit()
        st.warning("Cleared all scan results.")
        st.rerun()
    
    conn.close()
