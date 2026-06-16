import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from drawdownguard.risk_compare import max_drawdown
from drawdownguard.take_profit_optimizer import (
    default_worker_count,
    generate_take_profit_combinations,
    run_take_profit_optimizer,
    summarize_take_profit_optimizer_report,
)


class TakeProfitOptimizerTest(unittest.TestCase):
    def setUp(self):
        self.config = {
            "peak_window_trading_days": 250,
            "round_amount_to": 10,
            "bullet_account": {"name": "余额宝", "balance": 9999},
            "replenishment_levels": [
                {"drawdown_percent": 10, "cash_ratio": 0.15},
                {"drawdown_percent": 15, "cash_ratio": 0.25},
                {"drawdown_percent": 20, "cash_ratio": 0.35},
            ],
            "portfolio_backtest": {
                "enabled": True,
                "start_date": "2026-01-05",
                "bullet_cash_initial": 2000,
                "bullet_cash_monthly_addition": 0,
                "assets": [
                    {
                        "asset_id": "NASDAQ100",
                        "asset_name": "纳斯达克100",
                        "representative_fund": "270042",
                        "strategy": "drawdown_plus_dca",
                        "weekly_dca_amount": 100,
                        "drawdown_levels": [
                            {"level": 10, "cash_ratio": 0.15},
                            {"level": 15, "cash_ratio": 0.25},
                            {"level": 20, "cash_ratio": 0.35},
                        ],
                    }
                ],
            },
        }
        self.history = [
            {"date": "2026-01-05", "nav": 1.0},
            {"date": "2026-01-06", "nav": 1.15},
            {"date": "2026-01-07", "nav": 0.9},
            {"date": "2026-01-12", "nav": 1.3},
        ]

    def test_generate_take_profit_combinations(self):
        combinations = generate_take_profit_combinations()

        self.assertTrue(combinations)
        self.assertEqual(len(combinations), 27)
        first = combinations[0]
        self.assertEqual(first["levels"], [10, 20, 30])
        self.assertEqual(first["sell_percents"], [5, 10, 15])
        self.assertEqual(first["step_sell_percent"], 1)
        self.assertTrue(all(item["levels"][0] < item["levels"][1] < item["levels"][2] for item in combinations))

    def test_generate_full_take_profit_combinations(self):
        combinations = generate_take_profit_combinations(preset="full")

        self.assertEqual(len(combinations), 50240)
        self.assertTrue(all(item["levels"][0] < item["levels"][1] < item["levels"][2] for item in combinations))

    def test_default_worker_count_uses_cpu_minus_one_floor(self):
        self.assertGreaterEqual(default_worker_count(), 1)

    def test_max_drawdown_calculation_for_optimizer_series(self):
        series = [
            {"total_asset_value": 100},
            {"total_asset_value": 130},
            {"total_asset_value": 104},
        ]

        self.assertAlmostEqual(max_drawdown(series), -0.2)

    def test_optimizer_outputs_return_rate_and_recommendation(self):
        combinations = [
            {
                "levels": [10, 20, 30],
                "sell_percents": [5, 10, 15],
                "step_sell_percent": 1,
                "rules": [
                    {"level": 10, "base_sell_percent": 5, "step_sell_percent": 1},
                    {"level": 20, "base_sell_percent": 10, "step_sell_percent": 1},
                    {"level": 30, "base_sell_percent": 15, "step_sell_percent": 0},
                ],
            },
            {
                "levels": [20, 29, 40],
                "sell_percents": [20, 25, 30],
                "step_sell_percent": 5,
                "rules": [
                    {"level": 20, "base_sell_percent": 20, "step_sell_percent": 5},
                    {"level": 29, "base_sell_percent": 25, "step_sell_percent": 5},
                    {"level": 40, "base_sell_percent": 30, "step_sell_percent": 0},
                ],
            },
        ]

        report = run_take_profit_optimizer(self.config, self.history, combinations=combinations, workers=1)

        self.assertEqual(report["tested_count"], 2)
        self.assertEqual(report["workers"], 1)
        self.assertIn("total_return_rate", report["results"][0])
        self.assertIn("max_drawdown", report["results"][0])
        self.assertIn("recommended", report)
        self.assertEqual(report["recommended"]["scenario_id"], report["rankings"]["risk_return"][0]["scenario_id"])

    def test_optimizer_runs_with_process_workers(self):
        combinations = generate_take_profit_combinations()[:2]

        report = run_take_profit_optimizer(self.config, self.history, combinations=combinations, workers=2)

        self.assertEqual(report["tested_count"], 2)
        self.assertEqual(report["workers"], 2)
        self.assertEqual([item["scenario_id"] for item in report["results"]], ["TP00001", "TP00002"])

    def test_optimizer_writes_partial_report(self):
        combinations = generate_take_profit_combinations()[:2]
        with TemporaryDirectory() as temp_dir:
            partial_path = Path(temp_dir) / "take_profit_optimizer_partial.json"

            report = run_take_profit_optimizer(
                self.config,
                self.history,
                combinations=combinations,
                workers=1,
                partial_report_path=partial_path,
            )

            self.assertEqual(report["tested_count"], 2)
            self.assertTrue(partial_path.exists())
            self.assertIn('"partial": true', partial_path.read_text(encoding="utf-8"))

    def test_summarize_take_profit_optimizer_report(self):
        report = run_take_profit_optimizer(
            self.config,
            self.history,
            workers=1,
            combinations=[
                {
                    "levels": [10, 20, 30],
                    "sell_percents": [5, 10, 15],
                    "step_sell_percent": 1,
                    "rules": [
                        {"level": 10, "base_sell_percent": 5, "step_sell_percent": 1},
                        {"level": 20, "base_sell_percent": 10, "step_sell_percent": 1},
                        {"level": 30, "base_sell_percent": 15, "step_sell_percent": 0},
                    ],
                }
            ],
        )

        summary = summarize_take_profit_optimizer_report(report)

        self.assertIn("阶梯止盈档位优化摘要", summary)
        self.assertIn("测试组合数量：1", summary)
        self.assertIn("workers：1", summary)
        self.assertIn("推荐组合：", summary)


if __name__ == "__main__":
    unittest.main()
