"""Discovery dashboard — scan indexes or enter tickers manually."""
import streamlit as st
import pandas as pd

from db import add_to_watchlist, add_to_portfolio, upsert_scan
from fetcher import score_company
from smart_fetcher import fetch_company as smart_fetch, calculate_buy_under, get_data_source
from llm_advisor import generate_analysis
from discovery import (get_api_key, save_api_key, test_fmp_key, run_discovery,
                       get_available_ticker_count, get_index_stats, refresh_index_cache,
                       refresh_etf_holdings, PRESETS, INDEX_SOURCES, ETF_SOURCES)
from pages.helpers import get_shared_db


def render():
    st.title("\U0001f9ed Discovery")
    st.caption("Discover quality companies \u2014 scan indexes or enter tickers manually.")

    conn = get_shared_db()

    # Previous Scan Results (shared across tabs)
    _render_previous_results(conn)

    st.markdown("---")

    # Main Tabs: Manual Scan vs Index Discovery
    tab_manual, tab_index = st.tabs(["\u270f\ufe0f Manual Scan", "\U0001f9ed Index Discovery"])

    with tab_manual:
        _render_manual_scan(conn)

    with tab_index:
        _render_index_discovery(conn)


def _render_previous_results(conn):
    scan_rows = conn.execute("""
        SELECT * FROM scan_results
        ORDER BY score DESC, scanned_at DESC
    """).fetchall()

    if not scan_rows:
        return

    with st.expander(f"\U0001f4cb Previous Scan Results ({len(scan_rows)})", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            fit_filter = st.multiselect("Fit", ["STRONG", "MODERATE", "WEAK", "NOT FIT"], default=["STRONG", "MODERATE"], key="prev_fit")
        with col2:
            sector_filter = st.selectbox("Sector", ["All"] + list(set(r["sector"] for r in scan_rows if r["sector"])), key="prev_sector")

        filtered = scan_rows
        if fit_filter:
            filtered = [r for r in filtered if r["csu_fit"] in fit_filter]
        if sector_filter != "All":
            filtered = [r for r in filtered if r["sector"] == sector_filter]

        if filtered:
            df = pd.DataFrame(filtered)
            display_cols = ["ticker", "name", "sector", "industry", "score", "max_score", "csu_fit", "price", "fcf_yield", "gross_margin", "in_portfolio", "in_watchlist"]
            available_cols = [c for c in display_cols if c in df.columns]
            st.dataframe(df[available_cols], use_container_width=True, hide_index=True)

            # Actions on selected ticker
            st.subheader("Take Action")
            action_ticker = st.selectbox("Select Ticker", [r["ticker"] for r in filtered], key="prev_action_ticker")
            selected = next((r for r in filtered if r["ticker"] == action_ticker), None)

            if selected:
                acol1, acol2 = st.columns(2)
                with acol1:
                    buy_under = st.number_input("Buy Under Price", value=0.0, step=1.0, key="scan_bu")
                    if st.button("\U0001f440 Add to Watchlist", key="prev_add_wl"):
                        add_to_watchlist(conn, action_ticker, selected["name"],
                                        buy_under if buy_under > 0 else None,
                                        selected["score"], selected["max_score"],
                                        source="scan", sector=selected["sector"],
                                        industry=selected["industry"])
                        upsert_scan(conn, dict(selected))
                        conn.execute("UPDATE scan_results SET in_watchlist=1 WHERE ticker=?", (action_ticker,))
                        conn.commit()
                        st.success(f"Added {action_ticker} to watchlist!")
                        st.rerun()

                with acol2:
                    if st.button("\U0001f4c8 Add to Portfolio", key="prev_add_port"):
                        add_to_portfolio(conn, action_ticker, selected["name"],
                                        sector=selected["sector"], industry=selected["industry"],
                                        score=selected["score"], max_score=selected["max_score"])
                        upsert_scan(conn, dict(selected))
                        conn.execute("UPDATE scan_results SET in_portfolio=1 WHERE ticker=?", (action_ticker,))
                        conn.commit()
                        st.success(f"Added {action_ticker} to portfolio!")
                        st.rerun()
        else:
            st.info("No results match filters.")


def _render_manual_scan(conn):
    st.subheader("Quick Scan")
    st.caption("Enter tickers to fetch, score, and evaluate.")

    scan_tickers = st.text_input("Enter tickers (comma-separated)", placeholder="AAPL, MSFT, BRK-B", key="manual_tickers")

    if st.button("\U0001f680 Scan", key="manual_scan_btn") and scan_tickers:
        tickers = [t.strip().upper() for t in scan_tickers.split(",") if t.strip()]
        progress = st.progress(0)
        results = []

        for i, t in enumerate(tickers):
            with st.spinner(f"Fetching {t}..."):
                data = smart_fetch(t)
                if data:
                    t = data.get("ticker", t)
                    scored = score_company(data)
                    bu = calculate_buy_under(t, data)
                    if bu:
                        scored["buy_under"] = bu.get("buy_under_per_share")
                        scored["fair_value"] = bu.get("fair_value_per_share")
                    upsert_scan(conn, scored)
                    conn.commit()
                    results.append(scored)
            progress.progress((i + 1) / len(tickers))

        if results:
            st.success(f"Scanned {len(results)} companies via {get_data_source().upper()}")
            sorted_results = sorted(results, key=lambda x: x.get("total_score", 0), reverse=True)
            for r in sorted_results:
                fit_emoji = {"STRONG": "\U0001f7e2", "MODERATE": "\U0001f7e1", "WEAK": "\U0001f7e0", "NOT FIT": "\U0001f534"}.get(r.get("csu_fit"), "\u26aa")
                buy_str = f" | \U0001f4b0 Buy Under: ${r.get('buy_under', 'N/A')}" if r.get('buy_under') else ""
                fv_str = f" | Fair: ${r.get('fair_value', 'N/A')}" if r.get('fair_value') else ""
                with st.container():
                    st.write(f"{fit_emoji} **{r['ticker']}** \u2014 {r['name']} | Score: {r.get('total_score',0)}/{r.get('max_score','?')} | {r.get('csu_fit','?')}{buy_str}{fv_str}")
                    mcol1, mcol2, mcol3 = st.columns([2, 1, 1])
                    with mcol1:
                        st.caption(f"{r.get('sector', '')} \u00b7 {r.get('industry', '')}")
                    with mcol2:
                        if st.button("\U0001f440 Watchlist", key=f"mscan_wl_{r['ticker']}"):
                            add_to_watchlist(conn, r["ticker"], r.get("name", ""),
                                            r.get("buy_under") if r.get("buy_under") else None,
                                            r.get("total_score"), r.get("max_score"),
                                            source="manual_scan", sector=r.get("sector", ""),
                                            industry=r.get("industry", ""))
                            conn.execute("UPDATE scan_results SET in_watchlist=1 WHERE ticker=?", (r["ticker"],))
                            conn.commit()
                            st.success(f"Added {r['ticker']} to watchlist!")
                            st.rerun()
                    with mcol3:
                        if st.button("\U0001f4c8 Portfolio", key=f"mscan_pt_{r['ticker']}"):
                            add_to_portfolio(conn, r["ticker"], r.get("name", ""),
                                            sector=r.get("sector", ""), industry=r.get("industry", ""),
                                            score=r.get("total_score"), max_score=r.get("max_score"))
                            conn.execute("UPDATE scan_results SET in_portfolio=1 WHERE ticker=?", (r["ticker"],))
                            conn.commit()
                            st.success(f"Added {r['ticker']} to portfolio!")
                            st.rerun()


def _render_index_discovery(conn):
    # Index Cache Status
    st.subheader("Index Universe")
    idx_stats = get_index_stats()

    # Group by region
    regions = {"US": [], "Canada": [], "Europe": [], "Asia/Pacific": [], "ETF": []}
    region_map = {"US": "US", "CA": "Canada", "UK": "Europe", "DE": "Europe", "FR": "Europe", "NL": "Europe", "ES": "Europe", "IT": "Europe", "CH": "Europe", "SE": "Europe", "JP": "Asia/Pacific", "AU": "Asia/Pacific", "EU": "ETF"}

    for key, s in idx_stats.items():
        region = "ETF" if key.startswith("etf_") else region_map.get(s.get("region", "US"), "US")
        regions[region].append((key, s))

    tab_us, tab_ca, tab_eu, tab_ap, tab_etf = st.tabs(["\U0001f1fa\U0001f1f8 US", "\U0001f341 Canada", "\U0001f1ea\U0001f1fa Europe", "\U0001f30f Asia/Pacific", "\U0001f4e6 ETFs"])

    for tab, items in [(tab_us, regions["US"]), (tab_ca, regions["Canada"]), (tab_eu, regions["Europe"]), (tab_ap, regions["Asia/Pacific"]), (tab_etf, regions["ETF"])]:
        with tab:
            for key, s in items:
                icon = "\u2705" if s["cached"] > 0 else "\u2b1c"
                st.write(f"{icon} **{s['label']}** \u2014 {s['cached']} tickers ({s['cap']}-cap)")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("\U0001f504 Refresh Indexes", help="Re-download all index constituents from Wikipedia"):
            with st.spinner("Refreshing indexes..."):
                counts = refresh_index_cache()
                for k, v in counts.items():
                    if isinstance(v, str):
                        st.error(f"{INDEX_SOURCES.get(k, {}).get('label', k)}: {v}")
                    else:
                        st.success(f"{INDEX_SOURCES.get(k, {}).get('label', k)}: {v} tickers")
    with col2:
        if st.button("\U0001f4e6 Refresh ETFs", help="Fetch ETF holdings from iShares/BlackRock CSV files"):
            with st.spinner("Refreshing ETFs..."):
                counts = refresh_etf_holdings()
                for k, v in counts.items():
                    if isinstance(v, str):
                        st.warning(f"{k}: {v}")
                    else:
                        st.success(f"{k}: {v} holdings")

    st.markdown("---")

    # Preset Scans
    st.subheader("Discovery Scans")

    preset_options = [
        ("quality_compounders", "\U0001f3db\ufe0f Quality Compounders \u2014 High FCF, stable, durable"),
        ("deep_value", "\U0001f4b0 Deep Value \u2014 Cheap on FCF yield, profitable"),
        ("wide_moat", "\U0001f3f0 Wide Moat \u2014 High margins, dominant"),
        ("small_cap_quality", "\U0001f52d Small Cap Quality \u2014 US + EAFE small caps"),
        ("europe_quality", "\U0001f1ea\U0001f1fa Europe Quality \u2014 FTSE, DAX, CAC, IBEX, MIB..."),
        ("europe_small_cap", "\U0001f1ea\U0001f1fa Europe Small Cap \u2014 UK mid, MDAX, country ETFs"),
        ("canada_quality", "\U0001f341 Canada Quality \u2014 TSX 60, Composite, banks, rails, tech"),
        ("canada_small_cap", "\U0001f341 Canada Small Cap \u2014 TSX small/mid, quality under the radar"),
        ("asia_pacific", "\U0001f30f Asia-Pacific \u2014 Nikkei, ASX"),
        ("full_universe", "\U0001f30d Full Universe \u2014 All indexes (slow!)"),
    ]

    preset = st.selectbox("Scan Type", preset_options, format_func=lambda x: x[1], key="idx_preset")
    preset_key = preset[0]

    batch_size = st.slider(
        "Tickers to scan",
        min_value=10, max_value=100, value=20, step=10,
        help="How many tickers to fetch per scan. More = slower but more results.",
        key="idx_batch"
    )

    available = get_available_ticker_count(preset_key)
    st.caption(f"Available universe: {available} tickers | Scanning {min(batch_size, available)}")

    if st.button("\U0001f680 Run Discovery Scan", type="primary", disabled=available==0, key="idx_scan_btn"):
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
        _render_discovery_results(conn, results, preset_key)

    st.markdown("---")

    # Optional: FMP Integration
    _render_fmp_settings()


def _render_discovery_results(conn, results, preset_key="unknown"):
    if not results:
        st.info("No companies passed the filters. Try relaxing criteria or scanning more tickers.")
        return

    st.success(f"Found {len(results)} quality companies!")

    # Save to scan_results
    for r in results:
        upsert_scan(conn, r)
    conn.commit()

    # Display results
    for r in results:
        fit = r.get("csu_fit", "?")
        fit_emoji = {"STRONG": "\U0001f7e2", "MODERATE": "\U0001f7e1", "WEAK": "\U0001f7e0", "NOT FIT": "\U0001f534"}.get(fit, "\u26aa")
        score = r.get("total_score", 0)
        max_score = r.get("max_score", "?")

        # Check if already tracked
        in_p = conn.execute("SELECT 1 FROM portfolio WHERE ticker=?", (r['ticker'],)).fetchone()
        in_w = conn.execute("SELECT 1 FROM watchlist WHERE ticker=?", (r['ticker'],)).fetchone()
        status_badge = ""
        if in_p:
            status_badge = " \U0001f4ca OWN"
        elif in_w:
            status_badge = " \U0001f440 TRACKING"

        with st.container(border=True):
            hcol, scol, acol = st.columns([3, 1, 1])
            with hcol:
                st.write(f"{fit_emoji} **{r['ticker']}** \u2014 {r.get('name', '?')}{status_badge}")
                st.caption(f"{r.get('sector', '?')} / {r.get('industry', '?')} | MCap: ${r.get('market_cap_m', 0):,.0f}M")
            with scol:
                st.write(f"**{score}/{max_score}** | {fit}")
            with acol:
                if not in_p and not in_w:
                    if st.button("\U0001f440 Watch", key=f"disc_w_{r['ticker']}"):
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
                        suffix = " \U0001f9e0 Analysis generated" if analysis else ""
                        st.success(f"Added {r['ticker']} to watchlist!{suffix}")
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


def _render_fmp_settings():
    with st.expander("\U0001f511 FMP API Key (Optional \u2014 for European stocks)"):
        st.caption("The free discovery above covers US indexes. Add an FMP key for European exchanges.")
        api_key = get_api_key()
        current_key = st.text_input("FMP API Key", value=api_key or "", type="password", key="fmp_key_idx")
        if st.button("\U0001f4be Save FMP Key", key="fmp_save_idx") and current_key:
            save_api_key(current_key)
            st.success("Saved!")
        if api_key:
            if st.button("\U0001f9ea Test FMP Key", key="fmp_test_idx"):
                ok, msg = test_fmp_key(api_key)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
