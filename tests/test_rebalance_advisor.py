import unittest

from drawdownguard.real_config import apply_real_profile
from drawdownguard.rebalance_advisor import build_rebalance_advice, build_category_summary


class RebalanceAdvisorTest(unittest.TestCase):
    def test_category_weights_are_correct(self):
        config = apply_real_profile(_base_config(), _real_data())
        summary = build_category_summary(config)

        self.assertAlmostEqual(summary["CASH"]["current_weight"], 0.1756)
        self.assertAlmostEqual(summary["CORE"]["current_weight"], 0.2035)
        self.assertAlmostEqual(summary["SATELLITE"]["current_weight"], 0.1801)
        self.assertAlmostEqual(summary["DEFENSIVE"]["current_weight"], 0.4408)
        self.assertAlmostEqual(sum(item["current_weight"] for item in summary.values()), 1.0)

    def test_cash_is_not_counted_as_core(self):
        config = apply_real_profile(_base_config(), _real_data())
        summary = build_category_summary(config)

        self.assertNotAlmostEqual(summary["CORE"]["current_weight"], 0.2035 + 0.1756)
        self.assertEqual(summary["CASH"]["health"], "healthy")

    def test_core_underweight_increases_dca(self):
        config = apply_real_profile(_base_config(), _real_data())
        report = build_rebalance_advice(config)

        self.assertEqual(report["category_summary"]["CORE"]["status"], "underweight")
        self.assertEqual(report["category_summary"]["CORE"]["action"], "increase_dca")

    def test_defensive_above_target_does_not_force_sell(self):
        config = apply_real_profile(_base_config(), _real_data())
        report = build_rebalance_advice(config)

        defensive = report["category_summary"]["DEFENSIVE"]
        self.assertEqual(defensive["status"], "neutral")
        self.assertEqual(defensive["action"], "maintain")
        self.assertFalse(report["conclusion"]["sell_recommended"])

    def test_hstech_does_not_use_bullet_cash(self):
        config = apply_real_profile(_base_config(), _real_data())
        report = build_rebalance_advice(config)
        hstech = _asset(report, "HSTECH")

        self.assertEqual(hstech["action"], "watch")
        self.assertIn("不使用子弹仓", hstech["reason"])

    def test_bonds_tilt_to_core(self):
        config = apply_real_profile(_base_config(), _real_data())
        report = build_rebalance_advice(config)
        bonds = _asset(report, "BONDS")

        self.assertEqual(bonds["action"], "future_dca_tilt_to_core")
        self.assertIn("不建议立即卖出", bonds["reason"])

    def test_output_json_is_complete_without_optional_reports(self):
        config = apply_real_profile(_base_config(), _real_data())
        report = build_rebalance_advice(config)

        self.assertIn("target_allocation", report)
        self.assertIn("category_summary", report)
        self.assertIn("asset_advice", report)
        self.assertIn("dca_review", report)
        self.assertIn("suggested_future_dca_tilt", report)
        self.assertIn("conclusion", report)
        self.assertEqual(
            report["optional_reports_loaded"],
            {
                "portfolio_strategy_report": False,
                "portfolio_optimize_report": False,
                "contribution_report": False,
            },
        )


def _asset(report, asset_id):
    return next(item for item in report["asset_advice"] if item["asset_id"] == asset_id)


def _base_config():
    return {
        "funds": [],
        "bullet_account": {"name": "余额宝", "balance": 0},
        "replenishment_levels": [],
        "portfolio_backtest": {},
    }


def _real_data():
    return {
        "user_profile": {
            "version": "2026-06 投委会最终版",
            "bullet_cash": {"account_name": "余额宝", "amount": 1883},
            "life_account": {"investable": False},
            "target_allocation": {
                "CASH": {"target": 0.15, "min": 0.10, "max": 0.25},
                "CORE": {"target": 0.35, "min": 0.25, "max": 0.50},
                "SATELLITE": {"target": 0.20, "min": 0.10, "max": 0.30},
                "DEFENSIVE": {"target": 0.30, "min": 0.20, "max": 0.45},
            },
        },
        "current_holdings": {
            "holdings": [
                {"asset_id": "CASH", "asset_name": "余额宝", "amount": 1883, "weight": 0.1756, "role": "bullet_cash", "funds": []},
                {"asset_id": "NASDAQ100", "asset_name": "纳斯达克100", "amount": 2181, "weight": 0.2035, "role": "core_growth", "funds": []},
                {"asset_id": "HSTECH", "asset_name": "恒生科技", "amount": 290, "weight": 0.0271, "role": "satellite_opportunity", "funds": []},
                {"asset_id": "CASHFLOW", "asset_name": "自由现金流", "amount": 574, "weight": 0.0536, "role": "quality_factor", "funds": []},
                {"asset_id": "DIVIDEND_LOW_VOL", "asset_name": "红利低波", "amount": 419, "weight": 0.0390, "role": "value_factor", "nav_mode": "accumulated_nav", "funds": []},
                {"asset_id": "ACTIVE_ADVANCED_MANUFACTURING", "asset_name": "先进制造", "amount": 542, "weight": 0.0505, "role": "active_fund", "funds": []},
                {"asset_id": "NONFERROUS_METALS", "asset_name": "有色金属", "amount": 106, "weight": 0.0099, "role": "cyclical_theme", "funds": []},
                {"asset_id": "GOLD", "asset_name": "黄金", "amount": 763, "weight": 0.0712, "role": "hedge", "funds": []},
                {"asset_id": "BONDS", "asset_name": "债券", "amount": 3963, "weight": 0.3696, "role": "bond_stabilizer", "funds": []},
            ]
        },
        "dca_plan": {
            "weekly": [
                {"asset_id": "NASDAQ100", "fund_code": "270042", "fund_name": "广发纳指", "amount": 10},
                {"asset_id": "NASDAQ100", "fund_code": "012752", "fund_name": "建信纳指", "amount": 40},
                {"asset_id": "HSTECH", "fund_code": "012349", "fund_name": "恒科", "amount": 25},
            ],
            "monthly": [{"asset_id": "GOLD", "fund_code": "000216", "fund_name": "黄金", "amount": 40, "day": 1}],
        },
        "policy_config": {"drawdown_buy_policy": {"levels": []}},
    }

