import unittest

from drawdownguard.take_profit import TakeProfitBacktester, summarize_take_profit_report


class TakeProfitBacktestTest(unittest.TestCase):
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

    def test_conservative_take_profit_first_level_amount(self):
        history = [
            {"date": "2026-01-05", "nav": 1.0},
            {"date": "2026-01-06", "nav": 1.15},
        ]

        report = TakeProfitBacktester(self.config).run(history)

        self.assertEqual(report["trigger_count_sell"], 1)
        self.assertEqual(report["sell_events"][0]["level"], "15")
        self.assertAlmostEqual(report["sell_events"][0]["amount"], 17.25)
        self.assertAlmostEqual(report["sell_events"][0]["shares"], 15)
        self.assertAlmostEqual(report["total_sell_amount"], 17.25)

    def test_total_asset_value_and_return_rate(self):
        history = [
            {"date": "2026-01-05", "nav": 1.0},
            {"date": "2026-01-06", "nav": 1.15},
        ]

        report = TakeProfitBacktester(self.config).run(history)

        self.assertAlmostEqual(report["final_cash"], 2017.25)
        self.assertAlmostEqual(report["final_market_value"], 97.75)
        self.assertAlmostEqual(report["total_asset_value"], 2115.0)
        self.assertAlmostEqual(report["total_profit"], 15.0)
        self.assertAlmostEqual(report["total_return_rate"], 15.0 / 2100)

    def test_upgrade_level_incremental_sells(self):
        history = [
            {"date": "2026-01-05", "nav": 1.0},
            {"date": "2026-01-06", "nav": 1.15},
            {"date": "2026-01-07", "nav": 1.16},
            {"date": "2026-01-08", "nav": 1.25},
        ]

        report = TakeProfitBacktester(self.config).run(history)

        self.assertEqual([event["level"] for event in report["sell_events"]], ["15", "15", "15", "25"])
        self.assertAlmostEqual(report["sell_events"][0]["amount"], 17.25)
        self.assertAlmostEqual(report["sell_events"][1]["amount"], 1.15)
        self.assertAlmostEqual(report["sell_events"][2]["amount"], 9.2)
        self.assertAlmostEqual(report["sell_events"][3]["amount"], 23.0)
        self.assertAlmostEqual(report["total_sell_amount"], 50.6)

    def test_summarize_take_profit_report(self):
        summary = summarize_take_profit_report(
            {
                "start_date": "2026-01-05",
                "end_date": "2026-01-06",
                "total_dca_invested": 100,
                "total_buy_amount": 0,
                "total_sell_amount": 17.25,
                "final_cash": 2017.25,
                "final_market_value": 97.75,
                "total_asset_value": 2115,
                "total_return_rate": 15 / 2100,
                "trigger_count_buy": 0,
                "trigger_count_sell": 1,
            }
        )

        self.assertIn("保守阶梯止盈回测摘要", summary)
        self.assertIn("止盈卖出金额：17.25 元", summary)
        self.assertIn("止盈次数：1", summary)


if __name__ == "__main__":
    unittest.main()
