"""Watchlist dashboard — companies you're tracking. Buy when price hits your target."""
import streamlit as st
import json

from db import (add_to_watchlist, remove_from_watchlist, move_to_portfolio, upsert_scan)
from fetcher import score_company
from smart_fetcher import fetch_company as smart_fetch, calculate_buy_under
from llm_advisor import generate_analysis
from pages.helpers import get_shared_db, render_score_breakdown, backfill_metadata


def render():
    st.title("\U0001f440 Watchlist")
    st.caption("Companies you're tracking. Buy when price hits your target.")

    conn = get_shared_db()

    # Refresh All button
    if st.button("\U0001f504 Refresh All Prices", type="secondary"):
        wl_tickers = conn.execute("SELECT ticker FROM watchlist").fetchall()
        progress = st.progress(0, text="Fetching prices...")
        updated = 0
        for i, t in enumerate(wl_tickers):
            data = smart_fetch(t["ticker"])
            if data:
                scored = score_company(data)
                upsert_scan(conn, scored)
                backfill_metadata(conn, "watchlist", t["ticker"], scored)
                price_val = scored.get("price")
                conn.execute("UPDATE watchlist SET score=?, max_score=?, last_price=?, last_checked=datetime('now'), updated_at=datetime('now'), score_breakdown=? WHERE ticker=?",
                             (scored["total_score"], scored["max_score"], price_val, json.dumps({"scores": scored.get("scores", {}), "passes": scored.get("passes", {})}), t["ticker"]))
                updated += 1
                conn.commit()
            progress.progress((i + 1) / len(wl_tickers), text=f"{i+1}/{len(wl_tickers)} \u2014 {t['ticker']}")
        st.success(f"Updated {updated}/{len(wl_tickers)} companies")
        st.rerun()

    rows = conn.execute("SELECT * FROM watchlist ORDER BY priority, last_checked DESC").fetchall()

    if not rows:
        st.info("Watchlist is empty. Add from Discovery or manually.")

    _render_add_form(conn)

    if rows:
        for row in rows:
            _render_watchlist_card(conn, row)


def _render_add_form(conn):
    with st.expander("\u2795 Add to Watchlist"):
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
                if not wn or not wsect or not wind:
                    fetched = smart_fetch(wt)
                    if fetched:
                        wt = fetched.get("ticker", wt)
                        wn = wn or fetched.get("name", "")
                        wsect = wsect or fetched.get("sector", "")
                        wind = wind or fetched.get("industry", "")
                add_to_watchlist(conn, wt, wn, wb, priority=wp,
                                 thesis=w_thesis, kill_signals=w_kill,
                                 sector=wsect, industry=wind)
                st.success(f"Added {wt}")
                st.rerun()


def _render_watchlist_card(conn, row):
    pri_emoji = {"HIGH": "\U0001f534", "MEDIUM": "\U0001f7e1", "LOW": "\U0001f7e2"}.get(row["priority"], "\u26aa")
    score_pct = round(row["score"] / row["max_score"] * 100) if row["max_score"] else 0

    with st.container(border=True):
        hcol, acol = st.columns([4, 1])
        with hcol:
            st.subheader(f"{pri_emoji} {row['ticker']} \u2014 {row['name']}")
            st.caption(f"{row['sector']} / {row['industry']} | Score: {row['score']}/{row['max_score']} ({score_pct}%) | Tracked since: {row['first_tracked'][:10] if row['first_tracked'] else '?'}")
            render_score_breakdown(row, expander_label=f"\U0001f4ca Score Breakdown ({row['score']}/{row['max_score']})")

        with acol:
            st.write("")  # spacer

        # Key info
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            cur_price = row["last_price"]
            if cur_price is not None and cur_price > 0:
                if row["buy_under"]:
                    pct_below = (row["buy_under"] - cur_price) / cur_price * 100
                    if cur_price <= row["buy_under"]:
                        st.write(f"**\U0001f4b5 Price:** ${cur_price:.2f} \U0001f7e2")
                    else:
                        st.write(f"**\U0001f4b5 Price:** ${cur_price:.2f} \U0001f534 ({pct_below:+.0f}% to buy)")
                else:
                    st.write(f"**\U0001f4b5 Price:** ${cur_price:.2f}")
            else:
                st.write("**\U0001f4b5 Price:** \u2014")
        with col2:
            if row["buy_under"]:
                st.write(f"**\U0001f3af Buy Under:** ${row['buy_under']:.2f}")
            else:
                st.write("**\U0001f3af Buy Under:** Not set")
        with col3:
            if row["thesis"]:
                with st.expander("\U0001f4dd Thesis"):
                    st.write(row["thesis"])
        with col4:
            if row["kill_signals"]:
                with st.expander("\u26a0\ufe0f Kill Signals"):
                    st.write(row["kill_signals"])

        # Actions
        acol1, acol2, acol3, acol4, acol5 = st.columns(5)
        with acol1:
            _render_buy_flow(conn, row)
        with acol2:
            _render_refresh(conn, row)
        with acol3:
            _render_analyze(conn, row)
        with acol4:
            if st.button("\U0001f5d1\ufe0f Remove", key=f"wr_{row['ticker']}"):
                remove_from_watchlist(conn, row["ticker"])
                st.rerun()
        with acol5:
            new_bu = st.number_input("Buy Under", value=float(row["buy_under"]) if row["buy_under"] else 0.0,
                                     key=f"bu_{row['ticker']}", step=1.0)
            if new_bu != (row["buy_under"] or 0) and new_bu > 0:
                conn.execute("UPDATE watchlist SET buy_under=?, updated_at=datetime('now') WHERE ticker=?",
                             (new_bu, row["ticker"]))
                conn.commit()


def _render_buy_flow(conn, row):
    buy_key = f"buy_step_{row['ticker']}"
    if st.button("\U0001f4c8 Buy \u2192", key=f"buy_{row['ticker']}"):
        st.session_state[buy_key] = True
        st.rerun()
    if st.session_state.get(buy_key):
        default_price = float(row["last_price"]) if row["last_price"] and row["last_price"] > 0 else 0.0
        bcol1, bcol2, bcol3 = st.columns(3)
        with bcol1:
            buy_price_input = st.number_input("Buy Price", value=default_price, step=1.0, key=f"bp_{row['ticker']}")
        with bcol2:
            buy_shares_input = st.number_input("Shares", value=0.0, step=1.0, key=f"bs_{row['ticker']}")
        with bcol3:
            st.write("")  # spacer
            if st.button("\u2705 Confirm Buy", key=f"confirm_buy_{row['ticker']}"):
                move_to_portfolio(conn, row["ticker"], buy_price=buy_price_input if buy_price_input > 0 else None, shares=buy_shares_input)
                conn.commit()
                st.session_state.pop(buy_key, None)
                st.success(f"Bought {row['ticker']}!")
                st.rerun()
            if st.button("\u274c Cancel", key=f"cancel_buy_{row['ticker']}"):
                st.session_state.pop(buy_key, None)
                st.rerun()


def _render_refresh(conn, row):
    if st.button("\U0001f504 Refresh", key=f"ref_{row['ticker']}"):
        with st.spinner(f"Fetching {row['ticker']}..."):
            data = smart_fetch(row["ticker"])
            if data:
                scored = score_company(data)
                upsert_scan(conn, scored)
                backfill_metadata(conn, "watchlist", row["ticker"], scored)
                breakdown_json = json.dumps({"scores": scored.get("scores", {}), "passes": scored.get("passes", {})})
                conn.execute("UPDATE watchlist SET score=?, max_score=?, last_price=?, last_checked=datetime('now'), updated_at=datetime('now'), score_breakdown=? WHERE ticker=?",
                             (scored["total_score"], scored["max_score"], scored.get("price"), breakdown_json, row["ticker"]))
                conn.commit()
                if not row["buy_under"]:
                    bu = calculate_buy_under(row["ticker"], data)
                    if bu and bu.get("buy_under_per_share"):
                        conn.execute("UPDATE watchlist SET buy_under=?, updated_at=datetime('now') WHERE ticker=?",
                                     (bu["buy_under_per_share"], row["ticker"]))
                st.rerun()


def _render_analyze(conn, row):
    if st.button("\U0001f9e0 Analyze", key=f"ai_{row['ticker']}"):
        with st.spinner(f"Analyzing {row['ticker']} with LLM..."):
            scan = conn.execute("SELECT * FROM scan_results WHERE ticker=?", (row["ticker"],)).fetchone()
            if scan:
                data = dict(scan)
            else:
                data = smart_fetch(row["ticker"])
                if data:
                    data = score_company(data)
            if data:
                backfill_metadata(conn, "watchlist", row["ticker"], data)
                analysis = generate_analysis(data)
                if analysis:
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
                    st.success(f"\U0001f9e0 Analysis saved for {row['ticker']}!")
                    st.rerun()
                else:
                    st.error("LLM analysis failed. Check Settings \u2192 LLM Advisor.")
            else:
                st.warning("No data to analyze. Refresh first.")
