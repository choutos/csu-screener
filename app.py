"""
Investment Process App
=======================
Three dashboards: Portfolio, Watchlist, Scanner.
Run: streamlit run app.py
"""
import streamlit as st
from db import get_db, add_to_portfolio, add_to_watchlist, move_to_portfolio, move_to_watchlist, remove_from_watchlist, remove_from_portfolio, log_kill_signal, update_portfolio_status, upsert_scan
from fetcher import fetch_company, score_company
from smart_fetcher import fetch_company as smart_fetch, calculate_buy_under, get_data_source, is_ib_available
from llm_advisor import generate_analysis, load_config as load_llm_config, save_config as save_llm_config, test_connection as test_llm_connection
from discovery import get_api_key, save_api_key, test_fmp_key, run_discovery, get_available_ticker_count, get_index_stats, refresh_index_cache, refresh_etf_holdings, PRESETS, INDEX_SOURCES, ETF_SOURCES, ibkr_scan
import pandas as pd
from datetime import datetime
from pathlib import Path

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Invest Process", page_icon="🎩", layout="wide")

# ─── Sidebar ──────────────────────────────────────────────────────────────────
page = st.sidebar.radio("📐 Dashboard", ["📊 Portfolio", "👀 Watchlist", "🔍 Scanner", "🧭 Discovery", "⚙️ Settings"])

# Data source indicator
source = get_data_source()
source_emoji = "🏦" if source == "ibkr" else "📈"
source_label = "IB Gateway" if source == "ibkr" else "yfinance"
st.sidebar.caption(f"{source_emoji} Data: {source_label}")

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

    # Refresh All button
    if st.button("🔄 Refresh All Prices", type="secondary"):
        wl_tickers = conn.execute("SELECT ticker FROM watchlist").fetchall()
        progress = st.progress(0, text="Fetching prices...")
        updated = 0
        for i, t in enumerate(wl_tickers):
            data = smart_fetch(t["ticker"])
            if data:
                scored = score_company(data)
                upsert_scan(conn, scored)
                price_val = scored.get("price")
                conn.execute("UPDATE watchlist SET score=?, max_score=?, last_price=?, last_checked=datetime('now'), updated_at=datetime('now') WHERE ticker=?",
                             (scored["total_score"], scored["max_score"], price_val, t["ticker"]))
                updated += 1
                conn.commit()
            progress.progress((i + 1) / len(wl_tickers), text=f"{i+1}/{len(wl_tickers)} — {t['ticker']}")
        st.success(f"Updated {updated}/{len(wl_tickers)} companies")
        st.rerun()

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
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    # Current price + buy-under comparison
                    cur_price = row["last_price"]
                    if cur_price is not None and cur_price > 0:
                        if row["buy_under"]:
                            pct_below = (row["buy_under"] - cur_price) / cur_price * 100
                            if cur_price <= row["buy_under"]:
                                st.write(f"**💵 Price:** ${cur_price:.2f} 🟢")
                            else:
                                st.write(f"**💵 Price:** ${cur_price:.2f} 🔴 ({pct_below:+.0f}% to buy)")
                        else:
                            st.write(f"**💵 Price:** ${cur_price:.2f}")
                    else:
                        st.write("**💵 Price:** —")
                with col2:
                    if row["buy_under"]:
                        st.write(f"**🎯 Buy Under:** ${row['buy_under']:.2f}")
                    else:
                        st.write("**🎯 Buy Under:** Not set")
                with col3:
                    if row["thesis"]:
                        with st.expander(f"📝 Thesis"):
                            st.write(row["thesis"])
                with col4:
                    if row["kill_signals"]:
                        with st.expander(f"⚠️ Kill Signals"):
                            st.write(row["kill_signals"])
                
                # Actions
                acol1, acol2, acol3, acol4, acol5 = st.columns(5)
                with acol1:
                    if st.button(f"📈 Buy →", key=f"buy_{row['ticker']}"):
                        move_to_portfolio(conn, row["ticker"])
                        st.success(f"Moved {row['ticker']} to portfolio!")
                        st.rerun()
                with acol2:
                    if st.button(f"🔄 Refresh", key=f"ref_{row['ticker']}"):
                        with st.spinner(f"Fetching {row['ticker']}..."):
                            data = smart_fetch(row["ticker"])
                            if data:
                                scored = score_company(data)
                                upsert_scan(conn, scored)
                                conn.execute("UPDATE watchlist SET score=?, max_score=?, last_price=?, last_checked=datetime('now'), updated_at=datetime('now') WHERE ticker=?",
                                             (scored["total_score"], scored["max_score"], scored.get("price"), row["ticker"]))
                                conn.commit()
                                if not row["buy_under"]:
                                    bu = calculate_buy_under(row["ticker"], data)
                                    if bu and bu.get("buy_under_per_share"):
                                        conn.execute("UPDATE watchlist SET buy_under=?, updated_at=datetime('now') WHERE ticker=?",
                                                     (bu["buy_under_per_share"], row["ticker"]))
                                st.rerun()
                with acol3:
                    if st.button(f"🧠 Analyze", key=f"ai_{row['ticker']}"):
                        with st.spinner(f"Analyzing {row['ticker']} with LLM..."):
                            # Fetch fresh data if needed
                            scan = conn.execute("SELECT * FROM scan_results WHERE ticker=?", (row["ticker"],)).fetchone()
                            if scan:
                                data = dict(scan)
                            else:
                                data = smart_fetch(row["ticker"])
                                if data:
                                    data = score_company(data)
                            if data:
                                analysis = generate_analysis(data)
                                if analysis:
                                    updates = []
                                    if analysis.get("thesis"):
                                        conn.execute("UPDATE watchlist SET thesis=?, updated_at=datetime('now') WHERE ticker=?",
                                                     (analysis["thesis"], row["ticker"]))
                                    if analysis.get("kill_signals"):
                                        conn.execute("UPDATE watchlist SET kill_signals=?, updated_at=datetime('now') WHERE ticker=?",
                                                     (analysis["kill_signals"], row["ticker"]))
                                    if analysis.get("buy_under"):
                                        conn.execute("UPDATE watchlist SET buy_under=?, updated_at=datetime('now') WHERE ticker=?",
                                                     (analysis["buy_under"], row["ticker"]))
                                    conn.commit()
                                    st.success(f"🧠 Analysis saved for {row['ticker']}!")
                                    st.rerun()
                                else:
                                    st.error("LLM analysis failed. Check Settings → LLM Advisor.")
                            else:
                                st.warning("No data to analyze. Refresh first.")
                with acol4:
                    if st.button(f"🗑️ Remove", key=f"wr_{row['ticker']}"):
                        remove_from_watchlist(conn, row["ticker"])
                        st.rerun()
                with acol5:
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
                data = smart_fetch(t)
                if data:
                    scored = score_company(data)
                    # Add buy-under calculation
                    bu = calculate_buy_under(t, data)
                    if bu:
                        scored["buy_under"] = bu.get("buy_under_per_share")
                        scored["fair_value"] = bu.get("fair_value_per_share")
                    upsert_scan(conn, scored)
                    results.append(scored)
            progress.progress((i + 1) / len(tickers))
        
        if results:
            st.success(f"Scanned {len(results)} companies via {get_data_source().upper()}")
            for r in sorted(results, key=lambda x: x.get("total_score", 0), reverse=True):
                fit_emoji = {"STRONG": "🟢", "MODERATE": "🟡", "WEAK": "🟠", "NOT FIT": "🔴"}.get(r.get("csu_fit"), "⚪")
                buy_str = f" | 💰 Buy Under: ${r.get('buy_under', 'N/A')}" if r.get('buy_under') else ""
                fv_str = f" | Fair: ${r.get('fair_value', 'N/A')}" if r.get('fair_value') else ""
                st.write(f"{fit_emoji} **{r['ticker']}** — {r['name']} | Score: {r.get('total_score',0)}/{r.get('max_score','?')} | {r.get('csu_fit','?')}{buy_str}{fv_str}")
    
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


# ─── Discovery Dashboard ──────────────────────────────────────────────────────
elif page == "🧭 Discovery":
    st.title("🧭 Discovery")
    st.caption("Auto-discover quality companies from index constituents. No API key needed — uses Wikipedia + yfinance.")
    
    conn = get_db()
    
    # ── Index Cache Status ──
    st.subheader("Index Universe")
    idx_stats = get_index_stats()
    
    # Group by region
    regions = {"US": [], "Europe": [], "Asia/Pacific": [], "ETF": []}
    region_map = {"US": "US", "UK": "Europe", "DE": "Europe", "FR": "Europe", "NL": "Europe", "ES": "Europe", "IT": "Europe", "CH": "Europe", "SE": "Europe", "JP": "Asia/Pacific", "AU": "Asia/Pacific", "EU": "ETF"}
    
    for key, s in idx_stats.items():
        region = "ETF" if key.startswith("etf_") else region_map.get(s.get("region", "US"), "US")
        regions[region].append((key, s))
    
    tab_us, tab_eu, tab_ap, tab_etf = st.tabs(["🇺🇸 US", "🇪🇺 Europe", "🌏 Asia/Pacific", "📦 ETFs"])
    
    needs_refresh = any(not s["cache_exists"] for s in idx_stats.values())
    
    for tab, items in [(tab_us, regions["US"]), (tab_eu, regions["Europe"]), (tab_ap, regions["Asia/Pacific"]), (tab_etf, regions["ETF"])]:
        with tab:
            for key, s in items:
                icon = "✅" if s["cached"] > 0 else "⬜"
                st.write(f"{icon} **{s['label']}** — {s['cached']} tickers ({s['cap']}-cap)")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Refresh Indexes", help="Re-download all index constituents from Wikipedia"):
            with st.spinner("Refreshing indexes..."):
                counts = refresh_index_cache()
                for k, v in counts.items():
                    if isinstance(v, str):
                        st.error(f"{INDEX_SOURCES.get(k, {}).get('label', k)}: {v}")
                    else:
                        st.success(f"{INDEX_SOURCES.get(k, {}).get('label', k)}: {v} tickers")
    with col2:
        if st.button("📦 Refresh ETFs", help="Fetch ETF holdings via yfinance"):
            with st.spinner("Refreshing ETFs..."):
                counts = refresh_etf_holdings()
                for k, v in counts.items():
                    if isinstance(v, str):
                        st.warning(f"{k}: {v}")
                    else:
                        st.success(f"{k}: {v} holdings")
    
    st.markdown("---")
    
    # ── Preset Scans ──
    st.subheader("Discovery Scans")
    
    preset_options = [
        ("quality_compounders", "🏛️ Quality Compounders — High FCF, stable, durable"),
        ("deep_value", "💰 Deep Value — Cheap on FCF yield, profitable"),
        ("wide_moat", "🏰 Wide Moat — High margins, dominant"),
        ("small_cap_quality", "🔭 Small Cap Quality — US + EAFE small caps"),
        ("europe_quality", "🇪🇺 Europe Quality — FTSE, DAX, CAC, IBEX, MIB..."),
        ("europe_small_cap", "🇪🇺 Europe Small Cap — UK mid, MDAX, country ETFs"),
        ("asia_pacific", "🌏 Asia-Pacific — Nikkei, ASX"),
        ("full_universe", "🌍 Full Universe — All indexes (slow!)"),
    ]
    
    preset = st.selectbox("Scan Type", preset_options, format_func=lambda x: x[1])
    preset_key = preset[0]
    
    batch_size = st.slider(
        "Tickers to scan",
        min_value=10, max_value=100, value=20, step=10,
        help="How many tickers to fetch per scan. More = slower but more results."
    )
    
    available = get_available_ticker_count(preset_key)
    st.caption(f"Available universe: {available} tickers | Scanning {min(batch_size, available)}")
    
    if st.button("🚀 Run Discovery Scan", type="primary", disabled=available==0):
        progress = st.progress(0, text="Starting scan...")
        
        def on_progress(current, total, ticker):
            pct = int((current + 1) / total * 100)
            progress.progress(pct, text=f"Scanning {ticker}... ({current+1}/{total})")
        
        try:
            results = run_discovery(preset=preset_key, batch_size=batch_size, progress_callback=on_progress)
        except Exception as e:
            st.error(f"Scan error: {e}")
            results = []
        
        progress.empty()
        st.session_state["discovery_results"] = results
    
    # Show results from session state (survives rerun after Watch button)
    results = st.session_state.get("discovery_results", None)
    if results is not None:
        if not results:
            st.info("No companies passed the filters. Try relaxing criteria or scanning more tickers.")
        else:
            st.success(f"Found {len(results)} quality companies!")
            
            # Save to scan_results
            for r in results:
                upsert_scan(conn, r)
            conn.commit()
            
            # Display results
            for r in results:
                fit = r.get("csu_fit", "?")
                fit_emoji = {"STRONG": "🟢", "MODERATE": "🟡", "WEAK": "🟠", "NOT FIT": "🔴"}.get(fit, "⚪")
                score = r.get("total_score", 0)
                max_score = r.get("max_score", "?")
                
                # Check if already tracked
                in_p = conn.execute("SELECT 1 FROM portfolio WHERE ticker=?", (r['ticker'],)).fetchone()
                in_w = conn.execute("SELECT 1 FROM watchlist WHERE ticker=?", (r['ticker'],)).fetchone()
                status_badge = ""
                if in_p:
                    status_badge = " 📊 OWN"
                elif in_w:
                    status_badge = " 👀 TRACKING"
                
                with st.container(border=True):
                    hcol, scol, acol = st.columns([3, 1, 1])
                    with hcol:
                        st.write(f"{fit_emoji} **{r['ticker']}** — {r.get('name', '?')}{status_badge}")
                        st.caption(f"{r.get('sector', '?')} / {r.get('industry', '?')} | MCap: ${r.get('market_cap_m', 0):,.0f}M")
                    with scol:
                        st.write(f"**{score}/{max_score}** | {fit}")
                    with acol:
                        if not in_p and not in_w:
                            if st.button(f"👀 Watch", key=f"disc_w_{r['ticker']}"):
                                add_to_watchlist(conn, r['ticker'], r.get('name', ''),
                                                score=score, max_score=max_score, source=f"discovery_{preset_key}",
                                                sector=r.get('sector', ''), industry=r.get('industry', ''))
                                # Auto-generate thesis & kill signals via LLM
                                analysis = generate_analysis(r)
                                if analysis:
                                    updates = []
                                    if analysis.get("thesis"):
                                        updates.append("thesis=?")
                                    if analysis.get("kill_signals"):
                                        updates.append("kill_signals=?")
                                    if analysis.get("buy_under"):
                                        updates.append("buy_under=?")
                                    if updates:
                                        vals = []
                                        for k in ["thesis", "kill_signals", "buy_under"]:
                                            if analysis.get(k):
                                                vals.append(analysis[k])
                                        vals.append(r['ticker'])
                                        conn.execute(f"UPDATE watchlist SET {', '.join(updates)}, updated_at=datetime('now') WHERE ticker=?", vals)
                                conn.commit()
                                st.success(f"Added {r['ticker']} to watchlist!{' 🧠 Analysis generated' if analysis else ''}")
                                st.rerun()
                    
                    # Key metrics row
                    metrics = []
                    for key, label, fmt in [
                        ("gross_margin", "Gross M", ".0%"),
                        ("fcf_margin", "FCF M", ".0%"),
                        ("fcf_yield", "FCF Y", ".1%"),
                        ("revenue_growth_3y", "Rev Gr", ".0%"),
                        ("debt_to_equity", "D/E", ".2f"),
                    ]:
                        v = r.get(key)
                        if v is not None:
                            try:
                                metrics.append(f"{label}: {v:{fmt}}")
                            except (ValueError, TypeError):
                                metrics.append(f"{label}: {v}")
                    if metrics:
                        st.caption(" | ".join(metrics))
    
    st.markdown("---")
    
    # ── Optional: FMP Integration ──
    with st.expander("🔑 FMP API Key (Optional — for European stocks)"):
        st.caption("The free discovery above covers US indexes. Add an FMP key for European exchanges.")
        api_key = get_api_key()
        current_key = st.text_input("FMP API Key", value=api_key or "", type="password")
        if st.button("💾 Save FMP Key") and current_key:
            save_api_key(current_key)
            st.success("Saved!")
        if api_key:
            if st.button("🧪 Test FMP Key"):
                ok, msg = test_fmp_key(api_key)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
    
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
    
    # ── LLM Advisor Settings ──
    st.subheader("🧠 LLM Advisor")
    st.caption("Configure an LLM to auto-generate thesis, kill signals, and buy-under prices.")
    
    llm_cfg = load_llm_config()
    
    llm_enabled = st.checkbox("Enable LLM Advisor", value=llm_cfg.get("enabled", True), key="llm_enabled")
    
    llm_col1, llm_col2 = st.columns(2)
    with llm_col1:
        llm_provider = st.selectbox("Provider", ["ollama", "litellm", "openai", "custom"],
                                    index=["ollama", "litellm", "openai", "custom"].index(llm_cfg.get("provider", "ollama")),
                                    key="llm_provider")
        llm_model = st.text_input("Model", value=llm_cfg.get("model", "glm-5.1:cloud"), key="llm_model")
    with llm_col2:
        llm_base_url = st.text_input("Base URL", value=llm_cfg.get("base_url", "http://localhost:11434/v1"), key="llm_base_url")
        llm_api_key = st.text_input("API Key", value=llm_cfg.get("api_key", ""), type="password", key="llm_api_key")
    
    llm_btn_col1, llm_btn_col2 = st.columns(2)
    with llm_btn_col1:
        if st.button("💾 Save LLM Settings"):
            save_llm_config({
                "provider": llm_provider,
                "base_url": llm_base_url,
                "model": llm_model,
                "api_key": llm_api_key,
                "enabled": llm_enabled,
            })
            st.success("LLM settings saved!")
    with llm_btn_col2:
        if st.button("🧪 Test Connection"):
            test_cfg = {
                "provider": llm_provider,
                "base_url": llm_base_url,
                "model": llm_model,
                "api_key": llm_api_key,
                "enabled": llm_enabled,
            }
            ok, msg = test_llm_connection(test_cfg)
            if ok:
                st.success(msg)
            else:
                st.error(msg)
    
    st.markdown("---")
    
    st.subheader("Danger Zone")
    
    if st.button("🗑️ Clear All Scan Results"):
        conn.execute("DELETE FROM scan_results")
        conn.commit()
        st.warning("Cleared all scan results.")
        st.rerun()
    
    conn.close()
