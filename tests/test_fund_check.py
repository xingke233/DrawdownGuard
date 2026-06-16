import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from drawdownguard.fund_check import run_fund_check, summarize_fund_check_report
from drawdownguard.storage import Storage


class FakeProvider:
    def __init__(self, histories):
        self.histories = histories

    def get_full_history(self, fund_code):
        history = self.histories.get(fund_code, [])
        warnings = [] if history else ["净值数据缺失，已跳过。"]
        return {"history": history, "source": "local", "warnings": warnings}


class FundCheckTest(unittest.TestCase):
    def setUp(self):
        self.config = {
            "funds": [
                {"code": "270042", "name": "广发纳斯达克100ETF联接A"},
                {"code": "008163", "name": "红利低波ETF联接A"},
            ],
            "portfolio_backtest": {
                "start_date": "2018-01-01",
                "assets": [
                    {
                        "asset_id": "NASDAQ100",
                        "asset_name": "纳斯达克100",
                        "representative_fund": "270042",
                    },
                    {
                        "asset_id": "DIVIDEND_LOW_VOL",
                        "asset_name": "红利低波",
                        "representative_fund": "008163",
                    },
                    {
                        "asset_id": "GOLD",
                        "asset_name": "黄金",
                        "representative_fund": "000216",
                    },
                ],
            },
        }
        self.provider = FakeProvider(
            {
                "270042": [
                    {"date": "2013-09-01", "nav": 1.0},
                    {"date": "2026-06-15", "nav": 2.0},
                ],
                "008163": [
                    {"date": "2020-01-15", "nav": 1.0},
                    {"date": "2026-06-15", "nav": 0.9},
                ],
            }
        )

    def test_fund_check_outputs_dates_days_and_current_nav(self):
        report = run_fund_check(self.config, self.provider)
        nasdaq = report["funds"][0]

        self.assertEqual(report["backtest_range"]["start_date"], "2018-01-01")
        self.assertEqual(report["backtest_range"]["end_date"], "2026-06-15")
        self.assertEqual(nasdaq["fund_code"], "270042")
        self.assertEqual(nasdaq["fund_name"], "广发纳斯达克100ETF联接A")
        self.assertEqual(nasdaq["earliest_nav_date"], "2013-09-01")
        self.assertEqual(nasdaq["latest_nav_date"], "2026-06-15")
        self.assertEqual(nasdaq["trading_days"], 2)
        self.assertEqual(nasdaq["current_nav"], 2.0)
        self.assertTrue(nasdaq["covers_backtest_range"])

    def test_warns_when_fund_starts_after_backtest_start(self):
        report = run_fund_check(self.config, self.provider)
        dividend = report["funds"][1]

        self.assertFalse(dividend["covers_backtest_range"])
        self.assertTrue(any("晚于回测起点" in warning for warning in dividend["warnings"]))

    def test_uses_existing_portfolio_report_range_when_available(self):
        portfolio_report = {
            "portfolio_summary": {
                "requested_start_date": "2018-01-01",
                "requested_end_date": None,
                "start_date": "2018-01-02",
                "end_date": "2026-06-15",
            }
        }
        config = {
            **self.config,
            "portfolio_backtest": {
                **self.config["portfolio_backtest"],
                "start_date": "2023-01-01",
            },
        }

        report = run_fund_check(config, self.provider, portfolio_report=portfolio_report)

        self.assertEqual(report["backtest_range"]["start_date"], "2018-01-01")
        self.assertEqual(report["backtest_range"]["end_date"], "2026-06-15")

    def test_missing_history_does_not_crash(self):
        report = run_fund_check(self.config, self.provider)
        gold = report["funds"][2]

        self.assertEqual(gold["fund_code"], "000216")
        self.assertEqual(gold["trading_days"], 0)
        self.assertIsNone(gold["current_nav"])
        self.assertFalse(gold["covers_backtest_range"])
        self.assertTrue(gold["warnings"])

    def test_summarize_fund_check_report(self):
        report = run_fund_check(self.config, self.provider)

        summary = summarize_fund_check_report(report)

        self.assertIn("Portfolio 基金数据检查", summary)
        self.assertIn("270042", summary)
        self.assertIn("最早日期：2013-09-01", summary)
        self.assertIn("是否覆盖当前回测区间：是", summary)
        self.assertIn("WARNING", summary)

    def test_storage_saves_fund_check_report(self):
        report = run_fund_check(self.config, self.provider)
        with TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))

            storage.save_fund_check_report(report)
            saved = json.loads((Path(temp_dir) / "data" / "fund_check_report.json").read_text(encoding="utf-8"))

            self.assertEqual(saved["funds"][0]["fund_code"], "270042")
            self.assertEqual(storage.load_fund_check_report(), saved)


if __name__ == "__main__":
    unittest.main()
