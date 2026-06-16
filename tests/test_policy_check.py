import copy
import unittest

from drawdownguard.real_config import apply_real_profile, run_policy_checks


class PolicyCheckTest(unittest.TestCase):
    def test_allowed_and_blocked_drawdown_funds_are_separated(self):
        config = apply_real_profile(_base_config(), _real_data())
        report = run_policy_checks(config)

        self.assertTrue(report["passed"])
        allowed = set(report["checked_items"]["allowed_drawdown_funds"])
        blocked = set(report["checked_items"]["blocked_drawdown_funds"])
        self.assertFalse(allowed & blocked)
        self.assertFalse(config["life_account"]["participates_in_replenishment"])

    def test_missing_nav_mode_is_reported(self):
        config = apply_real_profile(_base_config(), _real_data())
        config["portfolio_backtest"]["assets"][0].pop("nav_mode")

        report = run_policy_checks(config)

        self.assertIn("nav_mode", {issue["category"] for issue in report["issues"]})

    def test_life_account_investable_is_error(self):
        data = copy.deepcopy(_real_data())
        data["user_profile"]["life_account"]["investable"] = True
        config = apply_real_profile(_base_config(), data)
        config["life_account"]["investable"] = True

        report = run_policy_checks(config)

        self.assertFalse(report["passed"])


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
            "bullet_cash": {"account_name": "余额宝", "amount": 1883},
            "life_account": {"investable": False},
        },
        "current_holdings": {
            "holdings": [
                {
                    "asset_id": "NASDAQ100",
                    "asset_name": "纳斯达克100",
                    "amount": 2181,
                    "weight": 0.2035,
                    "role": "core_growth",
                    "funds": [
                        {"code": "270042", "name": "广发纳指"},
                        {"code": "012752", "name": "建信纳指"},
                    ],
                },
                {
                    "asset_id": "HSTECH",
                    "asset_name": "恒生科技",
                    "amount": 290,
                    "weight": 0.0271,
                    "role": "satellite_opportunity",
                    "funds": [{"code": "012349", "name": "恒生科技"}],
                },
                {
                    "asset_id": "GOLD",
                    "asset_name": "黄金",
                    "amount": 763,
                    "weight": 0.0712,
                    "role": "hedge",
                    "funds": [{"code": "000216", "name": "黄金"}],
                },
            ]
        },
        "dca_plan": {
            "weekly_day_index": 3,
            "weekly": [{"asset_id": "NASDAQ100", "fund_code": "270042", "fund_name": "广发纳指", "amount": 10}],
            "monthly": [{"asset_id": "GOLD", "fund_code": "000216", "fund_name": "黄金", "amount": 40, "day": 1}],
        },
        "policy_config": {
            "drawdown_buy_policy": {
                "allowed_fund_codes": ["270042", "012752", "012349"],
                "blocked_fund_codes": ["000216"],
                "levels": [{"drawdown_percent": 10, "cash_ratio": 0.15}],
            }
        },
    }

