import unittest

from drawdownguard.risk_compare import (
    build_conclusion,
    max_drawdown,
    run_risk_compare,
    summarize_risk_compare_report,
    volatility,
)


class RiskCompareTest(unittest.TestCase):
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

    def test_risk_compare_outputs_required_metrics(self):
        history = [
            {"date": "2026-01-05", "nav": 1.0},
            {"date": "2026-01-06", "nav": 1.2},
            {"date": "2026-01-07", "nav": 0.9},
            {"date": "2026-01-12", "nav": 1.3},
        ]

        report = run_risk_compare(self.config, history)
        strategies = {item["strategy_id"]: item for item in report["strategies"]}

        self.assertEqual(set(strategies), {"original", "take_profit"})
        for item in strategies.values():
            for key in [
                "total_invested",
                "final_market_value",
                "final_cash",
                "total_asset_value",
                "total_profit",
                "total_return_rate",
                "max_drawdown",
                "volatility",
                "cash_ratio_final",
                "buy_count",
                "sell_count",
            ]:
                self.assertIn(key, item)
        self.assertEqual(strategies["original"]["sell_count"], 0)
        self.assertGreater(strategies["take_profit"]["sell_count"], 0)
        self.assertIn("return_rate_difference", report["comparison"])

    def test_drawdown_and_volatility_calculation(self):
        series = [
            {"total_asset_value": 100},
            {"total_asset_value": 120},
            {"total_asset_value": 90},
            {"total_asset_value": 99},
        ]

        self.assertAlmostEqual(max_drawdown(series), -0.25)
        self.assertGreater(volatility(series), 0)

    def test_conclusion_rules(self):
        self.assertEqual(build_conclusion(-0.01, 0.04, 0.01), "止盈有效")
        self.assertEqual(build_conclusion(-0.05, 0.01, 0.0), "止盈不划算")

    def test_summarize_risk_compare_report(self):
        report = {
            "strategies": [
                {
                    "strategy_id": "original",
                    "total_return_rate": 0.2,
                    "max_drawdown": -0.3,
                },
                {
                    "strategy_id": "take_profit",
                    "total_return_rate": 0.18,
                    "max_drawdown": -0.2,
                },
            ],
            "comparison": {
                "max_drawdown_improvement": 0.1,
                "volatility_reduction": 0.02,
                "return_rate_difference": -0.02,
                "conclusion": "止盈有效",
            },
        }

        summary = summarize_risk_compare_report(report)

        self.assertIn("原始策略收益率：20.00%", summary)
        self.assertIn("止盈策略最大回撤：-20.00%", summary)
        self.assertIn("结论：止盈有效", summary)


if __name__ == "__main__":
    unittest.main()
