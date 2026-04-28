"""Portfolio dashboard — track holdings, monitor kill signals, decide HOLD / SELL / BUY MORE."""
import streamlit as st
import json
from datetime import datetime

from db import (add_to_portfolio, remove_from_portfolio, log_kill_signal,
                update_portfolio_status, upsert_scan,
                add_to_position, update_position_cost_basis)
from fetcher import score_company
from smart_fetcher import fetch_company as smart_fetch
from llm_advisor import check_portfolio_health
from pages.helpers import get_shared_db, render_score_breakdown, backfill_metadata


def render():
    st.title("\U0001f4ca Portfolio")
    st.caption("Track holdings, monitor kill signals, decide HOLD / SELL / BUY MORE")

    conn = get_shared_db()
    rows = conn.execute("SELECT * FROM portfolio ORDER BY updated_at DESC").fetchall()

    if not rows:
        st.info("No positions yet. Add from the Watchlist or Discovery.")
        _render_add_form(conn)
        return

    # Summary metrics
    total_positions = len(rows)
    statuses = {}
    for r in rows:
        s = r["status"]
        statuses[s] = statuses.get(s, 0) + 1

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Positions", total_positions)
    col2.metric("HOLD", statuses.get("HOLD", 0))
    col3.metric("WATCH", statuses.get("WATCH", 0))
    col4.metric("SELL", statuses.get("SELL", 0))
    col5.metric("BUY MORE", statuses.get("BUY_MORE", 0))

    st.markdown("---")

    # Position cards
    for row in rows:
        _render_position_card(conn, row)


def _render_add_form(conn):
    with st.expander("\u2795 Add position manually"):
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
                if not name or not sector or not industry:
                    fetched = smart_fetch(ticker)
                    if fetched:
                        ticker = fetched.get("ticker", ticker)
                        name = name or fetched.get("name", "")
                        sector = sector or fetched.get("sector", "")
                        industry = industry or fetched.get("industry", "")
                add_to_portfolio(conn, ticker, name, buy_price,
                                 str(buy_date), shares, thesis, kill_signals,
                                 sector=sector, industry=industry)
                st.success(f"Added {ticker}")
                st.rerun()


def _render_position_card(conn, row):
    status_emoji = {"HOLD": "\U0001f7e2", "WATCH": "\U0001f7e1", "SELL": "\U0001f534", "BUY_MORE": "\U0001f535"}.get(row["status"], "\u26aa")
    score_pct = round(row["score"] / row["max_score"] * 100) if row["max_score"] else 0

    with st.container(border=True):
        header_col, status_col, action_col = st.columns([3, 1, 1])
        with header_col:
            st.subheader(f"{status_emoji} {row['ticker']} \u2014 {row['name']}")
            st.caption(f"{row['sector']} / {row['industry']}")

        with status_col:
            status_options = ["HOLD", "WATCH", "SELL", "BUY_MORE"]
            current_status = row["status"] if row["status"] in status_options else "HOLD"
            new_status = st.selectbox(
                "Status", status_options,
                index=status_options.index(current_status),
                key=f"status_{row['ticker']}"
            )
            if new_status != row["status"]:
                update_portfolio_status(conn, row["ticker"], new_status)
                st.rerun()

        with action_col:
            if st.button("\U0001f5d1\ufe0f Remove", key=f"rm_{row['ticker']}"):
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
            render_score_breakdown(row)
            if row["last_kill_check"]:
                st.write(f"**Last Kill Check:** {row['last_kill_check'][:10]}")

        with det_col3:
            if row["thesis"]:
                st.write(f"**Thesis:** {row['thesis'][:100]}{'...' if len(row['thesis'])>100 else ''}")

        # Buy more / edit cost basis
        _render_edit_position(conn, row)

        # Kill signals (expandable)
        if row["kill_signals"]:
            with st.expander("\u26a0\ufe0f Kill Signals"):
                st.write(row["kill_signals"])

        # Health Check
        _render_health_check(conn, row)

        # Recent kill signal history
        kill_logs = conn.execute(
            "SELECT * FROM kill_signal_log WHERE ticker=? ORDER BY check_date DESC LIMIT 3",
            (row["ticker"],)
        ).fetchall()
        if kill_logs:
            for kl in kill_logs:
                sev_emoji = {"OK": "\u2705", "WARNING": "\u26a0\ufe0f", "CRITICAL": "\U0001f534"}.get(kl["severity"], "\u26aa")
                st.caption(f"{sev_emoji} {kl['check_date'][:10]} \u2014 {kl['signal_type']}: {kl['details'][:80] if kl['details'] else ''} \u2192 {kl['action']}")


def _render_edit_position(conn, row):
    ticker = row["ticker"]
    cur_shares = float(row["shares"] or 0)
    cur_price = float(row["buy_price"] or 0)

    with st.expander("\U0001f4b0 Buy more / Edit cost basis"):
        tab_add, tab_edit = st.tabs(["Buy more shares", "Edit values directly"])

        with tab_add:
            c1, c2 = st.columns(2)
            with c1:
                add_shares = st.number_input(
                    "Additional shares", min_value=0.0, step=0.1,
                    key=f"add_shares_{ticker}",
                )
            with c2:
                lot_price = st.number_input(
                    "Price per share", min_value=0.0, step=0.01,
                    key=f"lot_price_{ticker}",
                )

            if add_shares > 0 and lot_price > 0:
                new_shares = cur_shares + add_shares
                if cur_shares > 0 and cur_price > 0:
                    new_avg = ((cur_shares * cur_price) + (add_shares * lot_price)) / new_shares
                else:
                    new_avg = lot_price
                st.caption(
                    f"Preview: {cur_shares:g} @ ${cur_price:.2f}  +  "
                    f"{add_shares:g} @ ${lot_price:.2f}  →  "
                    f"**{new_shares:g} @ ${new_avg:.2f}** avg"
                )

            disabled = add_shares <= 0 or lot_price <= 0
            if st.button("Buy More", key=f"buy_more_{ticker}", disabled=disabled):
                add_to_position(conn, ticker, add_shares, lot_price)
                conn.commit()
                st.success(f"Added {add_shares:g} shares of {ticker} @ ${lot_price:.2f}")
                st.rerun()

        with tab_edit:
            c1, c2 = st.columns(2)
            with c1:
                edit_shares = st.number_input(
                    "Shares", min_value=0.0, step=0.1, value=cur_shares,
                    key=f"edit_shares_{ticker}",
                )
            with c2:
                edit_price = st.number_input(
                    "Buy price (avg)", min_value=0.0, step=0.01, value=cur_price,
                    key=f"edit_price_{ticker}",
                )

            unchanged = edit_shares == cur_shares and edit_price == cur_price
            if st.button("Save", key=f"edit_save_{ticker}", disabled=unchanged):
                update_position_cost_basis(conn, ticker, edit_shares, edit_price)
                conn.commit()
                st.success(f"Updated {ticker}: {edit_shares:g} shares @ ${edit_price:.2f}")
                st.rerun()


def _render_health_check(conn, row):
    hc_col1, hc_col2 = st.columns([1, 3])
    with hc_col1:
        if st.button("\U0001fa7a Health Check", key=f"hc_{row['ticker']}"):
            st.session_state[f"hc_run_{row['ticker']}"] = True
            st.rerun()
    with hc_col2:
        last_hc = st.session_state.get(f"hc_result_{row['ticker']}")
        if last_hc:
            status_colors = {"INTACT": "\U0001f7e2", "WEAKENED": "\U0001f7e1", "BROKEN": "\U0001f534"}
            se = status_colors.get(last_hc["thesis_status"], "\u26aa")
            st.write(f"{se} **Thesis: {last_hc['thesis_status']}** \u2014 {last_hc['summary']}")

    # Run health check on demand
    if st.session_state.get(f"hc_run_{row['ticker']}"):
        st.session_state.pop(f"hc_run_{row['ticker']}", None)
        with st.spinner(f"Checking {row['ticker']}..."):
            data = smart_fetch(row["ticker"])
            if data:
                scored = score_company(data)
                upsert_scan(conn, scored)
                backfill_metadata(conn, "portfolio", row["ticker"], scored)
                result = check_portfolio_health(scored, row["thesis"], row["kill_signals"])
                if result:
                    st.session_state[f"hc_result_{row['ticker']}"] = result

                    status_colors = {"INTACT": "\U0001f7e2", "WEAKENED": "\U0001f7e1", "BROKEN": "\U0001f534"}
                    se = status_colors.get(result["thesis_status"], "\u26aa")

                    st.markdown(f"### {se} Thesis: {result['thesis_status']}")
                    st.write(result["thesis_assessment"])

                    if result.get("kill_signals_triggered"):
                        st.markdown("**\u26a0\ufe0f Kill Signals Triggered:**")
                        for ks in result["kill_signals_triggered"]:
                            sev = "\U0001f534" if ks.get("severity") == "CRITICAL" else "\U0001f7e1"
                            st.write(f"{sev} {ks.get('signal', '?')}")
                    else:
                        st.markdown("**\u2705 No kill signals triggered**")

                    if result.get("new_risks"):
                        st.markdown("**\U0001f195 New Risks:**")
                        for risk in result["new_risks"]:
                            st.write(f"\u2022 {risk}")

                    action_emoji = {"HOLD": "\U0001f7e2", "SELL": "\U0001f534", "BUY_MORE": "\U0001f535", "WATCH": "\U0001f7e1"}
                    rec_icon = action_emoji.get(result['overall_action'], '\u26aa')
                    st.markdown(f"**Recommendation:** {rec_icon} {result['overall_action']} (confidence: {result['confidence']:.0%})")

                    # Log triggered kill signals
                    for ks in result.get("kill_signals_triggered", []):
                        log_kill_signal(
                            conn, row["ticker"],
                            "THESIS_CHANGE" if result["thesis_status"] == "BROKEN" else "OTHER",
                            ks.get("severity", "WARNING"),
                            ks.get("signal", ""),
                            result["overall_action"],
                            scored.get("price")
                        )

                    # Auto-update status based on recommendation
                    action_map = {"HOLD": "HOLD", "WATCH": "WATCH", "SELL": "SELL", "BUY_MORE": "BUY_MORE"}
                    new_status = action_map.get(result["overall_action"])
                    if new_status and new_status != row["status"]:
                        update_portfolio_status(conn, row["ticker"], new_status)
                        st.info(f"Status updated: {row['status']} \u2192 {new_status}")

                    # Update score, breakdown, and last check
                    breakdown_json = json.dumps({"scores": scored.get("scores", {}), "passes": scored.get("passes", {})})
                    conn.execute("UPDATE portfolio SET score=?, max_score=?, score_breakdown=?, last_kill_check=datetime('now'), updated_at=datetime('now') WHERE ticker=?",
                                 (scored["total_score"], scored["max_score"], breakdown_json, row['ticker']))
                    conn.commit()
                else:
                    st.error(f"Health check LLM returned no result for {row['ticker']}. Check LLM Settings.")
            else:
                st.warning(f"Could not fetch data for {row['ticker']}")
