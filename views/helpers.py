"""Shared UI helpers for dashboard pages."""
import streamlit as st
import json
from db import get_db


KPI_LABELS = {
    'fcf_margin': ('FCF Margin', '\u226510%'),
    'gross_margin': ('Gross Margin', '\u226540%'),
    'revenue_stability': ('Rev Stability', '\u226425% vol'),
    'growth_profile': ('Growth', '\u22125% to 25%'),
    'fcf_yield': ('FCF Yield', '\u22652%'),
    'debt_discipline': ('Debt Discipline', 'D/E \u22642.0'),
    'size_fit': ('Size Fit', '\u2265$200M'),
    'moat_quality': ('Moat', '\u226540% GM'),
}


@st.cache_resource
def get_shared_db():
    """Single cached connection -- avoids 'database is locked' from overlapping connections."""
    return get_db()


def needs_metadata_backfill(row):
    """True when a stored row has no proper human-readable name or metadata."""
    name = (row["name"] or "").strip()
    ticker = (row["ticker"] or "").strip()
    if not name or name.upper() == ticker.upper():
        return True
    if not (row.get("sector") or "").strip() and not (row.get("industry") or "").strip():
        return True
    return False


_BACKFILL_TABLES = {"watchlist", "portfolio"}


def backfill_metadata(conn, table, ticker, fetched):
    """Update name/sector/industry when stored metadata is blank or ticker-like."""
    if table not in _BACKFILL_TABLES:
        raise ValueError(f"unsupported table: {table}")
    row = conn.execute(f"SELECT name, sector, industry FROM {table} WHERE ticker=?", (ticker,)).fetchone()
    if not row:
        return

    updates, vals = [], []
    stored_name = (row["name"] or "").strip()
    fetched_name = (fetched.get("name") or "").strip()

    if fetched_name and (not stored_name or stored_name.upper() == ticker.upper()):
        updates.append("name=?")
        vals.append(fetched_name)
    if fetched.get("sector") and not (row["sector"] or "").strip():
        updates.append("sector=?")
        vals.append(fetched["sector"])
    if fetched.get("industry") and not (row["industry"] or "").strip():
        updates.append("industry=?")
        vals.append(fetched["industry"])

    if updates:
        vals.append(ticker)
        conn.execute(f"UPDATE {table} SET {', '.join(updates)}, updated_at=datetime('now') WHERE ticker=?", vals)


def render_score_breakdown(row, expander_label=None):
    """Render the 8-KPI score breakdown expander for a portfolio or watchlist row."""
    breakdown_raw = row['score_breakdown'] if 'score_breakdown' in row.keys() else None
    if not breakdown_raw:
        return
    try:
        bd = json.loads(breakdown_raw)
        scores = bd.get('scores', {})
        passes = bd.get('passes', {})
        label = expander_label or f"\U0001f4ca Breakdown ({row['score']}/{row['max_score']})"
        with st.expander(label):
            for kpi, (name, threshold) in KPI_LABELS.items():
                s = scores.get(kpi)
                p = passes.get(kpi, False)
                if s is None:
                    st.write(f"\u26aa **{name}**: N/A \u2014 {threshold}")
                else:
                    icon = '\u2705' if p else '\u274c'
                    st.write(f"{icon} **{name}**: {s}/3 \u2014 {threshold}")
    except (json.JSONDecodeError, KeyError):
        pass
