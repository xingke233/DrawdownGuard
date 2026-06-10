import json
import tempfile
import unittest
from pathlib import Path

from data_provider import NavDataProvider
from main import build_daily_log_entries, create_skipped_result
from notifier import format_daily_logs, format_report
from storage import Storage
from strategy import DrawdownStrategy


class FailingAkShare:
    def fund_open_fund_info_em(self, symbol, indicator):
        raise RuntimeError(f"akshare unavailable for {symbol}")


class NavDataProviderTest(unittest.TestCase):
    def setUp(self):
        self.config = {
            "data_source": "real",
            "peak_window_trading_days": 250,
            "round_amount_to": 10,
            "bullet_account": {"name": "余额宝", "balance": 2000},
            "replenishment_levels": [
                {"drawdown_percent": 10, "cash_ratio": 0.15},
                {"drawdown_percent": 15, "cash_ratio": 0.25},
                {"drawdown_percent": 20, "cash_ratio": 0.35},
            ],
            "funds": [{"code": "demo", "name": "演示基金", "bullet_balance": 2000}],
        }

    def test_real_failure_falls_back_to_local(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            nav_file = Path(temp_dir) / "nav_data.json"
            nav_file.write_text(
                json.dumps(
                    {
                        "demo": [
                            {"date": "2026-01-01", "nav": 1.0},
                            {"date": "2026-06-09", "nav": 0.88},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            provider = NavDataProvider(nav_file, self.config, akshare_client=FailingAkShare())

            result = provider.get_history("demo")

            self.assertEqual(result["source"], "local")
            self.assertEqual(len(result["history"]), 2)
            self.assertIn("真实净值获取失败", result["warnings"][0])

    def test_insufficient_data_warning_is_rendered_in_report(self):
        config = {**self.config, "data_source": "local"}
        with tempfile.TemporaryDirectory() as temp_dir:
            nav_file = Path(temp_dir) / "nav_data.json"
            nav_file.write_text(
                json.dumps(
                    {
                        "demo": [
                            {"date": "2026-01-01", "nav": 1.0},
                            {"date": "2026-06-09", "nav": 0.88},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            provider = NavDataProvider(nav_file, config)
            nav_data = provider.get_history("demo")
            strategy = DrawdownStrategy(config)
            result = strategy.evaluate_fund(config["funds"][0], nav_data["history"], {})
            result["data_source"] = nav_data["source"]
            result["warnings"] = nav_data["warnings"]

            report = format_report([result], config)

            self.assertIn("净值数据不足250条", report)
            self.assertIn("数据源：local", report)

    def test_real_and_local_failure_returns_empty_history_without_raising(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            nav_file = Path(temp_dir) / "missing_nav_data.json"
            provider = NavDataProvider(nav_file, self.config, akshare_client=FailingAkShare())

            result = provider.get_history("demo")

            self.assertEqual(result["source"], "local")
            self.assertEqual(result["history"], [])
            self.assertTrue(any("真实净值获取失败" in warning for warning in result["warnings"]))
            self.assertTrue(any("本地净值文件不存在" in warning for warning in result["warnings"]))
            self.assertTrue(any("净值数据缺失，已跳过" in warning for warning in result["warnings"]))

    def test_skipped_fund_is_rendered_and_other_fund_can_continue(self):
        strategy = DrawdownStrategy(self.config)
        skipped_nav_data = {
            "source": "local",
            "history": [],
            "warnings": ["净值数据缺失，已跳过。"],
        }
        skipped = create_skipped_result(self.config["funds"][0], skipped_nav_data)
        normal_fund = {"code": "ok", "name": "正常基金", "bullet_balance": 2000}
        normal = strategy.evaluate_fund(
            normal_fund,
            [
                {"date": "2026-01-01", "nav": 1.0},
                {"date": "2026-06-09", "nav": 0.88},
            ],
            {},
        )
        normal["data_source"] = "local"
        normal["warnings"] = []

        report = format_report([skipped, normal], self.config)

        self.assertIn("演示基金", report)
        self.assertIn("状态：净值数据缺失，已跳过", report)
        self.assertIn("正常基金", report)
        self.assertIn("状态：第一档已触发", report)

    def test_storage_migrates_historical_pending_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            records_file = Path(temp_dir) / "records.json"
            records_file.write_text(
                json.dumps(
                    {
                        "demo": {
                            "triggered_levels": {"10": True, "15": True, "20": True},
                            "pending_levels": {"10": True, "15": True, "20": True},
                            "historical_levels": {"10": True, "15": True, "20": True},
                        }
                    }
                ),
                encoding="utf-8",
            )
            storage = Storage(Path(temp_dir))

            records = storage.load_records()

            self.assertEqual(
                records["demo"]["triggered_levels"],
                {"10": False, "15": False, "20": False},
            )
            self.assertEqual(
                records["demo"]["pending_levels"],
                {"10": False, "15": False, "20": False},
            )

    def test_daily_logs_upsert_same_date_and_fund(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))
            first = {
                "date": "2026-06-09",
                "fund_code": "demo",
                "fund_name": "演示基金",
                "nav": 1.0,
                "peak_nav": 1.2,
                "drawdown": -0.1667,
                "status": "第二档已触发",
                "suggestions": {"15": 430},
                "data_source": "local",
                "warnings": [],
            }
            second = {**first, "status": "历史回撤", "suggestions": {}}

            storage.upsert_daily_logs([first])
            storage.upsert_daily_logs([second])
            logs = storage.load_daily_logs()

            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["status"], "历史回撤")
            self.assertEqual(logs[0]["suggestions"], {})

    def test_build_daily_log_entries_for_skipped_and_normal_results(self):
        skipped = create_skipped_result(
            self.config["funds"][0],
            {"source": "local", "warnings": ["净值数据缺失，已跳过。"]},
        )
        normal = {
            "fund_code": "ok",
            "fund_name": "正常基金",
            "current_date": "2026-06-09",
            "current_nav": 0.88,
            "peak_nav": 1.0,
            "drawdown": -0.12,
            "status": "第一档已触发",
            "suggested_amounts": {"10": 300},
            "data_source": "local",
            "warnings": [],
        }

        entries = build_daily_log_entries([skipped, normal])

        self.assertEqual(entries[0]["status"], "净值数据缺失，已跳过")
        self.assertIsNone(entries[0]["nav"])
        self.assertEqual(entries[0]["warnings"], ["净值数据缺失，已跳过。"])
        self.assertEqual(entries[1]["suggestions"], {"10": 300})

    def test_format_daily_logs_shows_recent_ten(self):
        logs = [
            {
                "date": f"2026-06-{day:02d}",
                "fund_code": "demo",
                "fund_name": "演示基金",
                "nav": 1.0,
                "peak_nav": 1.2,
                "drawdown": -0.1,
                "status": "第一档已触发",
                "suggestions": {"10": 300},
                "data_source": "local",
                "warnings": [],
            }
            for day in range(1, 12)
        ]

        output = format_daily_logs(logs)

        self.assertIn("最近10条每日检查日志", output)
        self.assertNotIn("2026-06-01", output)
        self.assertIn("2026-06-11", output)
        self.assertIn("建议 10%:300元", output)


if __name__ == "__main__":
    unittest.main()
