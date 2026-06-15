import unittest
from unittest.mock import patch

import pandas as pd

from core import data_fetcher


class _FakeResultSet:
    def __init__(self, fields, rows):
        self.error_code = "0"
        self.error_msg = "success"
        self.fields = fields
        self._rows = rows
        self._index = -1

    def next(self):
        self._index += 1
        return self._index < len(self._rows)

    def get_row_data(self):
        return self._rows[self._index]


def _fake_history_result():
    rows = []
    for day in range(1, 90):
        close = 10 + day * 0.1
        rows.append(
            [
                f"2025-01-{(day % 28) + 1:02d}",
                "sz.000001",
                f"{close - 0.2:.2f}",
                f"{close + 0.3:.2f}",
                f"{close - 0.4:.2f}",
                f"{close:.2f}",
                f"{close - 0.1:.2f}",
                str(1_000_000 + day * 1_000),
                str(12_000_000 + day * 50_000),
                "3",
                "4.2",
                "1",
                "2.1",
                "15.5",
                "1.7",
                "2.6",
                "1.1",
                "0",
            ]
        )
    return _FakeResultSet(
        [
            "date",
            "code",
            "open",
            "high",
            "low",
            "close",
            "preclose",
            "volume",
            "amount",
            "adjustflag",
            "turn",
            "tradestatus",
            "pctChg",
            "peTTM",
            "pbMRQ",
            "psTTM",
            "pcfNcfTTM",
            "isST",
        ],
        rows,
    )


class BaostockMigrationTest(unittest.TestCase):
    def test_get_stock_data_yf_uses_baostock_for_a_share_core_fields(self):
        def fake_query_history(*args, **kwargs):
            return _fake_history_result()

        def fake_query_stock_basic(code=None):
            return _FakeResultSet(
                ["code", "code_name", "ipoDate", "outDate", "type", "status"],
                [[code or "sz.000001", "平安银行", "1991-04-03", "", "1", "1"]],
            )

        def fake_query_profit_data(code=None, year=None, quarter=None):
            return _FakeResultSet(
                [
                    "code",
                    "pubDate",
                    "statDate",
                    "roeAvg",
                    "npMargin",
                    "gpMargin",
                    "netProfit",
                    "epsTTM",
                    "MBRevenue",
                    "totalShare",
                    "liqaShare",
                ],
                [
                    [
                        code,
                        "2025-04-30",
                        "2025-03-31",
                        "0.165",
                        "0.2",
                        "0.36",
                        "5000000000",
                        "1.2",
                        "",
                        "19405918198",
                        "19405918198",
                    ]
                ],
            )

        def fake_query_growth_data(code=None, year=None, quarter=None):
            return _FakeResultSet(
                [
                    "code",
                    "pubDate",
                    "statDate",
                    "YOYEquity",
                    "YOYAsset",
                    "YOYNI",
                    "YOYEPSBasic",
                    "YOYPNI",
                ],
                [
                    [
                        code,
                        "2025-04-30",
                        "2025-03-31",
                        "0.1",
                        "0.08",
                        "0.24",
                        "0.18",
                        "0.22",
                    ]
                ],
            )

        def fake_query_cash_flow_data(code=None, year=None, quarter=None):
            return _FakeResultSet(
                [
                    "code",
                    "pubDate",
                    "statDate",
                    "CAToAsset",
                    "NCAToAsset",
                    "tangibleAssetToAsset",
                    "ebitToInterest",
                    "CFOToOR",
                    "CFOToNP",
                    "CFOToGr",
                ],
                [
                    [
                        code,
                        "2025-04-30",
                        "2025-03-31",
                        "",
                        "",
                        "",
                        "",
                        "0.12",
                        "1.35",
                        "0.15",
                    ]
                ],
            )

        def fake_query_dupont_data(code=None, year=None, quarter=None):
            return _FakeResultSet(
                [
                    "code",
                    "pubDate",
                    "statDate",
                    "dupontROE",
                    "dupontAssetStoEquity",
                    "dupontAssetTurn",
                    "dupontPnitoni",
                    "dupontNitogr",
                    "dupontTaxBurden",
                    "dupontIntburden",
                    "dupontEbittogr",
                ],
                [
                    [
                        code,
                        "2025-04-30",
                        "2025-03-31",
                        "0.165",
                        "4.1",
                        "0.7",
                        "0.98",
                        "0.25",
                        "0.93",
                        "",
                        "",
                    ]
                ],
            )

        fake_index_hist = pd.DataFrame({"Close": [10 + i * 0.02 for i in range(90)]})

        with (
            patch.object(data_fetcher, "_baostock_initialized", True),
            patch.object(
                data_fetcher.bs,
                "query_history_k_data_plus",
                side_effect=fake_query_history,
            ),
            patch.object(
                data_fetcher.bs, "query_stock_basic", side_effect=fake_query_stock_basic
            ),
            patch.object(
                data_fetcher.bs, "query_profit_data", side_effect=fake_query_profit_data
            ),
            patch.object(
                data_fetcher.bs, "query_growth_data", side_effect=fake_query_growth_data
            ),
            patch.object(
                data_fetcher.bs,
                "query_cash_flow_data",
                side_effect=fake_query_cash_flow_data,
            ),
            patch.object(
                data_fetcher.bs, "query_dupont_data", side_effect=fake_query_dupont_data
            ),
            patch.object(
                data_fetcher,
                "get_money_flow_data",
                return_value={"main_net_in": 1000000, "hsgt_hold_change": 2000000},
            ),
            patch.object(
                data_fetcher.ak,
                "stock_zh_a_spot_em",
                side_effect=RuntimeError("skip ak name lookup"),
            ),
            patch.object(
                data_fetcher.yf,
                "Ticker",
                side_effect=AssertionError("yfinance should not be used"),
            ),
        ):
            result = data_fetcher.get_stock_data_yf(
                "000001", index_hist=fake_index_hist
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "平安银行")
        self.assertGreater(result["price"], 0)
        self.assertGreater(result["turnover_rate"], 0)
        self.assertAlmostEqual(result["roe"], 0.165)
        self.assertAlmostEqual(result["gross_margin"], 0.36)
        self.assertAlmostEqual(result["earnings_growth"], 0.24)
        self.assertGreater(result["operating_cashflow"], 0)
        self.assertIn("ma20", result["ma"])
        self.assertIn("Close", result["hist"].columns)


if __name__ == "__main__":
    unittest.main()
