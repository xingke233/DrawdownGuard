import unittest

from drawdownguard.dca_strategy_lab import (
    calculate_max_drawdown,
    calculate_volatility,
    generate_dca_strategy_combinations,
    run_dca_strategy_lab,
    simulate_dca_strategy,
)


class DcaStrategyLabTest(unittest.TestCase):
    def setUp(self):
        self.asset = {
            "asset_id": "NASDAQ100",
            "asset_name": "纳斯达克100",
            "representative_fund": "270042",
            "weekly_dca_amount": 100,
        }
        self.history = [
            {"date": "2026-01-05", "nav": 1.0},
            {"date": "2026-01-12", "nav": 2.0},
            {"date": "2026-01-19", "nav": 1.0},
            {"date": "2026-01-26", "nav": 2.0},
            {"date": "2026-02-02", "nav": 1.0},
        ]

    def test_generate_strategy_combinations(self):
        quick = generate_dca_strategy_combinations("quick")
        full = generate_dca_strategy_combinations("full")

        self.assertEqual(len(quick), 6)
        self.assertEqual(len(full), 108)
        self.assertIn(
            {
                "frequency": "weekly",
                "amount_mode": "fixed",
                "drawdown_rule": "none",
                "high_level_rule": "none",
            },
            quick,
        )

    def test_fixed_weekly_dca_calculation(self):
        result = simulate_dca_strategy(
            self.asset,
            self.history,
            {
                "frequency": "weekly",
                "amount_mode": "fixed",
                "drawdown_rule": "none",
                "high_level_rule": "none",
            },
            start_date="2026-01-05",
        )

        self.assertEqual(result["buy_count"], 5)
        self.assertEqual(result["total_invested"], 500)
        expected_shares = 100 / 1 + 100 / 2 + 100 / 1 + 100 / 2 + 100 / 1
        self.assertAlmostEqual(result["final_value"], expected_shares * 1.0)
        self.assertAlmostEqual(result["total_return_rate"], (expected_shares - 500) / 500)

    def test_drawdown_rule_increases_buy_amount(self):
        none_result = simulate_dca_strategy(
            self.asset,
            self.history,
            {
                "frequency": "weekly",
                "amount_mode": "fixed",
                "drawdown_rule": "none",
                "high_level_rule": "none",
            },
            start_date="2026-01-05",
        )
        aggressive_result = simulate_dca_strategy(
            self.asset,
            self.history,
            {
                "frequency": "weekly",
                "amount_mode": "fixed",
                "drawdown_rule": "aggressive",
                "high_level_rule": "none",
            },
            start_date="2026-01-05",
        )

        self.assertGreater(aggressive_result["total_invested"], none_result["total_invested"])

    def test_max_drawdown_calculation(self):
        series = [
            {"total_asset_value": 100},
            {"total_asset_value": 150},
            {"total_asset_value": 120},
        ]

        self.assertAlmostEqual(calculate_max_drawdown(series), -0.2)

    def test_volatility_and_sharpe_like_ratio(self):
        result = simulate_dca_strategy(
            self.asset,
            self.history,
            {
                "frequency": "weekly",
                "amount_mode": "fixed",
                "drawdown_rule": "none",
                "high_level_rule": "none",
            },
            start_date="2026-01-05",
        )

        self.assertGreater(result["volatility"], 0)
        self.assertIsNotNone(result["sharpe_like_ratio"])
        self.assertGreater(calculate_volatility([{"total_asset_value": 100}, {"total_asset_value": 120}, {"total_asset_value": 110}]), 0)

    def test_run_dca_strategy_lab_outputs_asset_rankings(self):
        config = {
            "portfolio_backtest": {
                "start_date": "2026-01-05",
                "assets": [self.asset],
            }
        }

        report = run_dca_strategy_lab(
            config,
            {"270042": self.history},
            preset="quick",
            workers=1,
            start_date="2026-01-05",
        )

        self.assertEqual(report["tested_count"], 6)
        self.assertEqual(report["assets"][0]["asset_id"], "NASDAQ100")
        self.assertIn("highest_return", report["assets"][0]["rankings"])
        self.assertIn("split_strategy_recommended", report["conclusion"])


if __name__ == "__main__":
    unittest.main()
