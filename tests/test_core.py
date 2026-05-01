import importlib.util
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

os.environ["CSU_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "invest.db")

import db
from fetcher import score_company
from smart_fetcher import _parse_ibkr_fundamentals, calculate_buy_under


class CoreFixTests(unittest.TestCase):
    def _new_db(self):
        tmp = tempfile.NamedTemporaryFile()
        conn = sqlite3.connect(tmp.name)
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA)
        return tmp, conn

    def _assert_visible_from_new_connection(self, db_path, query, params=()):
        second_conn = sqlite3.connect(db_path)
        try:
            row = second_conn.execute(query, params).fetchone()
        finally:
            second_conn.close()
        self.assertIsNotNone(row)
        return row

    def test_get_db_uses_autocommit_for_direct_ui_writes(self):
        original_db_path = db.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            db.DB_PATH = Path(tmpdir) / "invest.db"
            try:
                conn = db.get_db()
                conn.executescript(db.SCHEMA)
                conn.execute(
                    "INSERT INTO price_snapshots (ticker, price) VALUES (?, ?)",
                    ("TEST", 123.45),
                )

                row = self._assert_visible_from_new_connection(
                    db.DB_PATH,
                    "SELECT ticker, price FROM price_snapshots WHERE ticker=?",
                    ("TEST",),
                )
                self.assertEqual(row, ("TEST", 123.45))
                self.assertIsNone(conn.isolation_level)
            finally:
                db.DB_PATH = original_db_path
                conn.close()

    def test_write_helpers_commit_their_mutations(self):
        cases = [
            (
                "upsert_scan",
                lambda conn: db.upsert_scan(conn, {"ticker": "UPS", "name": "Upsert Co"}),
                "SELECT ticker FROM scan_results WHERE ticker='UPS'",
            ),
            (
                "add_to_watchlist",
                lambda conn: db.add_to_watchlist(conn, "WAT", "Watch Co", priority="HIGH"),
                "SELECT ticker FROM watchlist WHERE ticker='WAT'",
            ),
            (
                "add_to_portfolio",
                lambda conn: db.add_to_portfolio(conn, "POR", "Portfolio Co", shares=1),
                "SELECT ticker FROM portfolio WHERE ticker='POR'",
            ),
            (
                "log_kill_signal",
                lambda conn: db.log_kill_signal(conn, "SIG", "OTHER", "WARNING", "details", "WATCH"),
                "SELECT ticker FROM kill_signal_log WHERE ticker='SIG'",
            ),
            (
                "update_portfolio_status",
                lambda conn: (
                    db.add_to_portfolio(conn, "STA", "Status Co"),
                    db.update_portfolio_status(conn, "STA", "SELL"),
                ),
                "SELECT ticker FROM portfolio WHERE ticker='STA' AND status='SELL'",
            ),
            (
                "add_to_position",
                lambda conn: (
                    db.add_to_portfolio(conn, "ADD", "Add Co", buy_price=10, shares=2),
                    db.add_to_position(conn, "ADD", 2, 20),
                ),
                "SELECT ticker FROM portfolio WHERE ticker='ADD' AND shares=4 AND buy_price=15",
            ),
            (
                "update_position_cost_basis",
                lambda conn: (
                    db.add_to_portfolio(conn, "BAS", "Basis Co"),
                    db.update_position_cost_basis(conn, "BAS", 3, 42),
                ),
                "SELECT ticker FROM portfolio WHERE ticker='BAS' AND shares=3 AND buy_price=42",
            ),
            (
                "remove_from_watchlist",
                lambda conn: (
                    db.add_to_watchlist(conn, "RWL", "Remove Watch Co"),
                    db.remove_from_watchlist(conn, "RWL"),
                ),
                "SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM watchlist WHERE ticker='RWL')",
            ),
            (
                "remove_from_portfolio",
                lambda conn: (
                    db.add_to_portfolio(conn, "RPF", "Remove Portfolio Co"),
                    db.remove_from_portfolio(conn, "RPF"),
                ),
                "SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM portfolio WHERE ticker='RPF')",
            ),
            (
                "move_to_portfolio",
                lambda conn: (
                    db.add_to_watchlist(conn, "MTP", "Move Portfolio Co"),
                    db.move_to_portfolio(conn, "MTP", buy_price=9, shares=1),
                ),
                "SELECT ticker FROM portfolio WHERE ticker='MTP'",
            ),
            (
                "move_to_watchlist",
                lambda conn: (
                    db.upsert_scan(conn, {"ticker": "MTW", "name": "Move Watch Co"}),
                    db.move_to_watchlist(conn, "MTW", buy_under=8),
                ),
                "SELECT ticker FROM watchlist WHERE ticker='MTW'",
            ),
        ]

        for name, op, query in cases:
            with self.subTest(name=name):
                tmp, conn = self._new_db()
                try:
                    op(conn)
                    self._assert_visible_from_new_connection(tmp.name, query)
                finally:
                    conn.close()
                    tmp.close()

    def test_init_db_migrates_revenue_and_legacy_debt_to_equity(self):
        original_db_path = db.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            db.DB_PATH = Path(tmpdir) / "legacy.db"
            conn = sqlite3.connect(db.DB_PATH)
            try:
                conn.execute("""
                    CREATE TABLE scan_results (
                        ticker TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        debt_to_equity REAL
                    )
                """)
                conn.execute(
                    "INSERT INTO scan_results (ticker, name, debt_to_equity) VALUES (?, ?, ?)",
                    ("OLD", "Legacy Co", 75),
                )
                conn.commit()
            finally:
                conn.close()

            try:
                db.init_db()
                migrated = sqlite3.connect(db.DB_PATH)
                try:
                    columns = [
                        row[1]
                        for row in migrated.execute("PRAGMA table_info(scan_results)").fetchall()
                    ]
                    row = migrated.execute(
                        "SELECT debt_to_equity, total_revenue_m FROM scan_results WHERE ticker='OLD'"
                    ).fetchone()
                finally:
                    migrated.close()

                self.assertIn("total_revenue_m", columns)
                self.assertEqual(row, (0.75, None))
            finally:
                db.DB_PATH = original_db_path

    def test_settings_import_uses_root_watchlist_path(self):
        streamlit_stub = types.ModuleType("streamlit")
        streamlit_stub.cache_resource = lambda func=None, **_kwargs: (
            func if func is not None else lambda wrapped: wrapped
        )
        llm_stub = types.ModuleType("llm_advisor")
        llm_stub.load_config = lambda: {}
        llm_stub.save_config = lambda config: None
        llm_stub.test_connection = lambda config: False

        original_streamlit = sys.modules.get("streamlit")
        original_llm = sys.modules.get("llm_advisor")
        sys.modules["streamlit"] = streamlit_stub
        sys.modules["llm_advisor"] = llm_stub
        try:
            settings_path = Path(__file__).resolve().parents[1] / "views" / "settings.py"
            spec = importlib.util.spec_from_file_location("settings_under_test", settings_path)
            settings = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(settings)

            self.assertEqual(
                settings.WATCHLIST_IMPORT_PATH,
                Path(__file__).resolve().parents[1] / "watchlist.json",
            )
            self.assertTrue(settings.WATCHLIST_IMPORT_PATH.exists())
        finally:
            if original_streamlit is None:
                sys.modules.pop("streamlit", None)
            else:
                sys.modules["streamlit"] = original_streamlit
            if original_llm is None:
                sys.modules.pop("llm_advisor", None)
            else:
                sys.modules["llm_advisor"] = original_llm

    def test_ibkr_debt_to_equity_is_normalized_like_yfinance(self):
        percent_result = _parse_ibkr_fundamentals("<DebtToEquity>75</DebtToEquity>")
        ratio_result = _parse_ibkr_fundamentals("<DebtToEquity>0.75</DebtToEquity>")

        self.assertEqual(percent_result["debt_to_equity"], 0.75)
        self.assertEqual(ratio_result["debt_to_equity"], 0.75)

    def test_debt_to_equity_threshold_expects_ratio_not_percent(self):
        scored = score_company(
            {
                "ticker": "TEST",
                "gross_margin": 0.6,
                "fcf_margin": 0.2,
                "fcf_yield": 0.04,
                "debt_to_equity": 0.75,
                "revenue_growth_3y": 0.08,
                "revenue_volatility": 0.1,
                "market_cap_m": 1_000,
                "sector": "Technology",
            }
        )

        self.assertTrue(scored["passes"]["debt_discipline"])
        self.assertEqual(scored["scores"]["debt_discipline"], 2)

    def test_buy_under_uses_revenue_when_fcf_yield_missing(self):
        result = calculate_buy_under(
            "TEST",
            {
                "ticker": "TEST",
                "price": 10,
                "market_cap_m": 1_000,
                "total_revenue_m": 500,
                "fcf_margin": 0.2,
                "fcf_yield": None,
                "revenue_growth_3y": 0.05,
            },
        )

        self.assertIsNotNone(result)
        self.assertGreater(result["buy_under_per_share"], 0)

    def test_upsert_scan_persists_total_revenue_for_buy_under_round_trip(self):
        tmp, conn = self._new_db()
        try:
            db.upsert_scan(
                conn,
                {
                    "ticker": "REV",
                    "name": "Revenue Co",
                    "price": 10,
                    "market_cap_m": 1_000,
                    "total_revenue_m": 500,
                    "fcf_margin": 0.2,
                    "fcf_yield": None,
                    "revenue_growth_3y": 0.05,
                },
            )
            row = conn.execute("SELECT * FROM scan_results WHERE ticker='REV'").fetchone()
            result = calculate_buy_under("REV", dict(row))
        finally:
            conn.close()
            tmp.close()

        self.assertIsNotNone(result)
        self.assertGreater(result["buy_under_per_share"], 0)

    def test_buy_under_refuses_margin_market_cap_fallback(self):
        result = calculate_buy_under(
            "TEST",
            {
                "ticker": "TEST",
                "price": 10,
                "market_cap_m": 1_000,
                "fcf_margin": 0.2,
                "fcf_yield": None,
                "revenue_growth_3y": 0.05,
            },
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
