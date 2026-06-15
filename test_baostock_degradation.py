import unittest
from unittest.mock import patch

import pandas as pd

from core.scorer import calculate_score
from core.stock_screener import deep_screen_stock


def _base_hist():
    values = [10 + i * 0.1 for i in range(80)]
    return pd.DataFrame(
        {
            "High": [v + 0.3 for v in values],
            "Low": [v - 0.2 for v in values],
            "Close": values,
            "Volume": [1_000_000 + i * 1_000 for i in range(80)],
        }
    )


def _base_data():
    hist = _base_hist()
    return {
        "code": "000001",
        "name": "平安银行",
        "price": float(hist["Close"].iloc[-1]),
        "roe": 0.16,
        "gross_margin": 0.36,
        "operating_cashflow": 1_000_000_000,
        "earnings_growth": 0.24,
        "market_cap": 350e8,
        "pe_ttm": 12.0,
        "turnover_rate": 4.2,
        "roic": 0.17,
        "fcf": 900_000_000,
        "ma": {"ma5": 17.5, "ma10": 17.0, "ma20": 16.0, "ma60": 14.0},
        "vwap": 17.6,
        "vcp_ratio": 0.85,
        "rps": 1.1,
        "adx": 26.0,
        "boll_pct_b": 0.45,
        "hist": hist,
        "money_flow": {"main_net_in": 1_200_000, "hsgt_hold_change": 2_000_000},
        "short_ratio": None,
    }


class BaostockDegradationTest(unittest.TestCase):
    def test_deep_screen_stock_uses_source_agnostic_empty_data_message(self):
        with patch("core.stock_screener.get_stock_data_yf", return_value=None):
            passed, reason, data = deep_screen_stock("000001")

        self.assertFalse(passed)
        self.assertEqual(reason, "核心行情/财务数据不足")
        self.assertIsNone(data)

    def test_deep_screen_stock_allows_missing_sparse_financial_fields(self):
        payload = _base_data()
        payload["gross_margin"] = None
        payload["operating_cashflow"] = None

        with patch("core.stock_screener.get_stock_data_yf", return_value=payload):
            passed, reason, data = deep_screen_stock("000001")

        self.assertTrue(passed)
        self.assertEqual(reason, "通过")
        self.assertIsNotNone(data)

    def test_deep_screen_stock_still_rejects_truly_bad_values(self):
        payload = _base_data()
        payload["gross_margin"] = 0.05
        payload["operating_cashflow"] = -100

        with patch("core.stock_screener.get_stock_data_yf", return_value=payload):
            passed, reason, _ = deep_screen_stock("000001")

        self.assertFalse(passed)
        self.assertIn("毛利率低", reason)

    def test_calculate_score_neutralizes_missing_sparse_provider_fields(self):
        payload = _base_data()
        payload["gross_margin"] = None
        payload["roic"] = None
        payload["fcf"] = None
        payload["market_cap"] = None

        result = calculate_score("000001", {"sectors": ["银行"]}, payload)
        report = {row["name"]: row for row in result["report"]}

        self.assertEqual(report["2.4 毛利趋势"]["score"], 5)
        self.assertIn("数据稀疏", report["2.4 毛利趋势"]["res"])
        self.assertEqual(report["2.5 ROIC"]["score"], 5)
        self.assertEqual(report["2.6 现金流"]["score"], 5)
        self.assertEqual(report["2.7 行业位"]["score"], 5)


if __name__ == "__main__":
    unittest.main()
