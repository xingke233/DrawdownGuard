import unittest

from drawdownguard.notifier import format_report
from drawdownguard.strategy import DrawdownStrategy


class DrawdownStrategyTest(unittest.TestCase):
    def setUp(self):
        self.config = {
            "peak_window_trading_days": 250,
            "round_amount_to": 10,
            "replenishment_levels": [
                {"drawdown_percent": 10, "cash_ratio": 0.15},
                {"drawdown_percent": 15, "cash_ratio": 0.25},
                {"drawdown_percent": 20, "cash_ratio": 0.35},
            ],
        }
        self.fund = {"code": "demo", "name": "演示基金", "bullet_balance": 2000}

    def test_first_level_triggers_once(self):
        strategy = DrawdownStrategy(self.config)
        records = {}
        history = [
            {"date": "2026-01-01", "nav": 1.5},
            {"date": "2026-06-09", "nav": 1.32},
        ]

        first = strategy.evaluate_fund(self.fund, history, records)
        second = strategy.evaluate_fund(self.fund, history, records)

        self.assertEqual(first["triggered_now"], ["10"])
        self.assertEqual(second["triggered_now"], [])
        self.assertEqual(first["suggested_amounts"]["10"], 300)

    def test_twenty_five_percent_drawdown_still_uses_third_level(self):
        strategy = DrawdownStrategy(self.config)
        records = {}
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-06-09", "nav": 0.74},
        ]

        result = strategy.evaluate_fund(self.fund, history, records)

        self.assertEqual(result["status"], "第三档已触发")
        self.assertEqual(result["triggered_now"], ["10", "15", "20"])
        self.assertEqual(result["suggested_amounts"]["20"], 450)

    def test_new_high_resets_records(self):
        strategy = DrawdownStrategy(self.config)
        records = {
            "demo": {
                "triggered_levels": {"10": True, "15": False, "20": False},
                "pending_levels": {"10": True, "15": False, "20": False},
                "executed_levels": {"10": False, "15": False, "20": False},
            }
        }
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-06-09", "nav": 1.1},
        ]

        result = strategy.evaluate_fund(self.fund, history, records)

        self.assertEqual(result["status"], "观察中")
        self.assertFalse(records["demo"]["triggered_levels"]["10"])

    def test_second_level_triggers_at_fifteen_percent(self):
        strategy = DrawdownStrategy(self.config)
        records = {}
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-06-09", "nav": 0.85},
        ]

        result = strategy.evaluate_fund(self.fund, history, records)

        self.assertEqual(result["triggered_now"], ["10", "15"])
        self.assertEqual(result["status"], "第二档已触发")
        self.assertEqual(result["suggested_amounts"]["10"], 300)
        self.assertEqual(result["suggested_amounts"]["15"], 430)

    def test_multiple_levels_use_remaining_bullet_cash_in_order(self):
        strategy = DrawdownStrategy(self.config)
        records = {}
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-06-09", "nav": 0.74},
        ]

        result = strategy.evaluate_fund(self.fund, history, records)

        self.assertEqual(result["triggered_now"], ["10", "15", "20"])
        self.assertEqual(result["suggested_amounts"]["10"], 300)
        self.assertEqual(result["suggested_amounts"]["15"], 430)
        self.assertEqual(result["suggested_amounts"]["20"], 450)

    def test_strategy_uses_250_day_window(self):
        strategy = DrawdownStrategy(self.config)

        self.assertEqual(strategy.window, 250)

    def test_strategy_thresholds_do_not_include_removed_rules(self):
        strategy = DrawdownStrategy(self.config)

        self.assertEqual(set(strategy.levels), {"10", "15", "20"})
        self.assertNotIn("13", strategy.levels)
        self.assertFalse(hasattr(strategy, "risk_observation_percent"))

    def test_activation_date_blocks_historical_drawdown_levels(self):
        config = {**self.config, "strategy_activation_date": "2026-06-09"}
        strategy = DrawdownStrategy(config)
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-06-09", "nav": 0.88},
        ]

        result = strategy.evaluate_fund(self.fund, history, {})

        self.assertEqual(result["status"], "历史回撤")
        self.assertEqual(result["advice"], "不追补历史档位。")
        self.assertEqual(result["triggered_now"], [])
        self.assertEqual(result["suggested_amounts"], {})
        self.assertTrue(result["historical_levels"]["10"])

    def test_deep_historical_drawdown_does_not_generate_replenishment(self):
        config = {**self.config, "strategy_activation_date": "2026-06-09"}
        strategy = DrawdownStrategy(config)
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-06-09", "nav": 0.7071},
        ]

        result = strategy.evaluate_fund(self.fund, history, {})

        self.assertEqual(result["status"], "深度回撤中")
        self.assertAlmostEqual(result["historical_drawdown"], -0.2929, places=4)
        self.assertEqual(result["advice"], "不追补历史档位，继续观察")
        self.assertEqual(result["triggered_now"], [])
        self.assertEqual(result["suggested_amounts"], {})

    def test_new_post_activation_level_can_trigger_after_historical_level(self):
        config = {**self.config, "strategy_activation_date": "2026-06-09"}
        strategy = DrawdownStrategy(config)
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-06-09", "nav": 0.88},
            {"date": "2026-06-10", "nav": 0.84},
        ]

        result = strategy.evaluate_fund(self.fund, history, {})

        self.assertEqual(result["status"], "第二档已触发")
        self.assertEqual(result["triggered_now"], ["15"])
        self.assertNotIn("10", result["suggested_amounts"])
        self.assertEqual(result["suggested_amounts"]["15"], 500)

    def test_new_high_after_activation_clears_historical_baseline(self):
        config = {**self.config, "strategy_activation_date": "2026-06-09"}
        strategy = DrawdownStrategy(config)
        records = {}
        historical = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-06-09", "nav": 0.88},
        ]
        strategy.evaluate_fund(self.fund, historical, records)

        reset = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-06-09", "nav": 0.88},
            {"date": "2026-06-10", "nav": 1.1},
        ]
        result = strategy.evaluate_fund(self.fund, reset, records)

        self.assertEqual(result["status"], "观察中")
        self.assertFalse(any(result["historical_levels"].values()))
        self.assertTrue(records["demo"]["activation_baseline_cleared"])

    def test_deep_historical_drawdown_report_text(self):
        config = {
            **self.config,
            "strategy_activation_date": "2026-06-09",
            "bullet_account": {"name": "余额宝", "balance": 2000},
        }
        strategy = DrawdownStrategy(config)
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-06-09", "nav": 0.7071},
        ]

        result = strategy.evaluate_fund(self.fund, history, {})
        result["data_source"] = "local"
        result["warnings"] = []
        report = format_report([result], config)

        self.assertIn("状态：深度回撤中", report)
        self.assertIn("历史回撤：-29.29%", report)
        self.assertIn("建议：不追补历史档位，继续观察", report)
        self.assertIn("执行状态：无待确认", report)

    def test_activation_migrates_polluted_pending_levels_to_historical(self):
        config = {
            **self.config,
            "strategy_activation_date": "2026-06-09",
            "bullet_account": {"name": "余额宝", "balance": 2000},
        }
        strategy = DrawdownStrategy(config)
        records = {
            "demo": {
                "triggered_levels": {"10": True, "15": True, "20": True},
                "pending_levels": {"10": True, "15": True, "20": True},
                "executed_levels": {"10": False, "15": False, "20": False},
                "historical_levels": {"10": True, "15": True, "20": True},
                "activation_baseline_cleared": False,
            }
        }
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-06-09", "nav": 0.7071},
        ]

        result = strategy.evaluate_fund(self.fund, history, records)
        result["data_source"] = "local"
        result["warnings"] = []
        report = format_report([result], config)

        self.assertEqual(result["status"], "深度回撤中")
        self.assertEqual(result["suggested_amounts"], {})
        self.assertEqual(result["pending_levels"], {"10": False, "15": False, "20": False})
        self.assertEqual(result["triggered_levels"], {"10": False, "15": False, "20": False})
        self.assertIn("状态：深度回撤中", report)
        self.assertIn("历史回撤：-29.29%", report)
        self.assertIn("建议：不追补历史档位，继续观察", report)
        self.assertIn("执行状态：无待确认", report)
        self.assertNotIn("建议补仓：10% 档", report)
        self.assertNotIn("建议补仓：15% 档", report)
        self.assertNotIn("建议补仓：20% 档", report)


if __name__ == "__main__":
    unittest.main()
