import sqlite3
import tempfile
import unittest

import db
from fetcher import score_company
from smart_fetcher import calculate_buy_under


class CoreFixTests(unittest.TestCase):
    def test_add_to_watchlist_commits_write(self):
        with tempfile.NamedTemporaryFile() as tmp:
            conn = sqlite3.connect(tmp.name)
            conn.row_factory = sqlite3.Row
            conn.executescript(db.SCHEMA)

            db.add_to_watchlist(conn, "TEST", "Test Co", priority="HIGH")

            second_conn = sqlite3.connect(tmp.name)
            row = second_conn.execute(
                "SELECT ticker, name, priority FROM watchlist WHERE ticker=?", ("TEST",)
            ).fetchone()
            self.assertEqual(row, ("TEST", "Test Co", "HIGH"))

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
