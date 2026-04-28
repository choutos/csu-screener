"""Settings dashboard — DB stats, imports, LLM configuration."""
import streamlit as st
import json
from pathlib import Path

from db import add_to_watchlist
from llm_advisor import (load_config as load_llm_config, save_config as save_llm_config,
                          test_connection as test_llm_connection)
from views.helpers import get_shared_db


def render():
    st.title("\u2699\ufe0f Settings")

    conn = get_shared_db()

    _render_db_stats(conn)
    st.markdown("---")
    _render_bulk_import(conn)
    st.markdown("---")
    _render_seed_picks(conn)
    st.markdown("---")
    _render_llm_settings()
    st.markdown("---")
    _render_danger_zone(conn)


def _render_db_stats(conn):
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


def _render_bulk_import(conn):
    st.subheader("Bulk Import from Screener")
    st.caption("Import tickers from the csu-screener watchlist.json")

    if st.button("Import Watchlist from Screener"):
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


def _render_seed_picks(conn):
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


def _render_llm_settings():
    st.subheader("\U0001f9e0 LLM Advisor")
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
        if st.button("\U0001f4be Save LLM Settings"):
            save_llm_config({
                "provider": llm_provider,
                "base_url": llm_base_url,
                "model": llm_model,
                "api_key": llm_api_key,
                "enabled": llm_enabled,
            })
            st.success("LLM settings saved!")
    with llm_btn_col2:
        if st.button("\U0001f9ea Test Connection"):
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


def _render_danger_zone(conn):
    st.subheader("Danger Zone")

    if st.button("\U0001f5d1\ufe0f Clear All Scan Results"):
        conn.execute("DELETE FROM scan_results")
        conn.commit()
        st.warning("Cleared all scan results.")
        st.rerun()
