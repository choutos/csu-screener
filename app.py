"""
Investment Process App
=======================
Four dashboards: Portfolio, Watchlist, Discovery, Settings.
Run: streamlit run app.py
"""
import streamlit as st
from smart_fetcher import get_data_source

from pages import portfolio, watchlist, discovery, settings

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Invest Process", page_icon="🎩", layout="wide")

# ─── Sidebar ──────────────────────────────────────────────────────────────────
page = st.sidebar.radio("📐 Dashboard", ["📊 Portfolio", "👀 Watchlist", "🧭 Discovery", "⚙️ Settings"])

# Data source indicator
source = get_data_source()
source_emoji = "🏦" if source == "ibkr" else "📈"
source_label = "IB Gateway" if source == "ibkr" else "yfinance"
st.sidebar.caption(f"{source_emoji} Data: {source_label}")

st.sidebar.markdown("---")
st.sidebar.markdown("*Investment Process App*\n🎩")

# ─── Page Router ──────────────────────────────────────────────────────────────
if page == "📊 Portfolio":
    portfolio.render()
elif page == "👀 Watchlist":
    watchlist.render()
elif page == "🧭 Discovery":
    discovery.render()
elif page == "⚙️ Settings":
    settings.render()
