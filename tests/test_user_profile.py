import unittest

from drawdownguard.real_config import apply_real_profile


class UserProfileConfigTest(unittest.TestCase):
    def test_investor_profile_loads_and_life_account_is_excluded(self):
        config = _base_config()
        result = apply_real_profile(config, _real_data())

        self.assertEqual(result["investor_profile"]["age"], 20)
        self.assertEqual(result["investor_profile"]["style"], "growth")
        self.assertFalse(result["life_account"]["investable"])
        self.assertFalse(result["life_account"]["participates_in_replenishment"])
        self.assertEqual(result["bullet_account"]["balance"], 1883)


def _base_config():
    return {
        "funds": [],
        "bullet_account": {"name": "余额宝", "balance": 0},
        "replenishment_levels": [],
        "portfolio_backtest": {"start_date": "2026-01-01"},
    }


def _real_data():
    return {
        "user_profile": {
            "version": "2026-06 投委会最终版",
            "investor_profile": {
                "age": 20,
                "style": "growth",
                "horizon_years": "10+",
                "target_annual_return": 0.10,
                "max_account_drawdown_tolerance": 0.30,
            },
            "bullet_cash": {"account_name": "余额宝", "amount": 1883, "investable": True},
            "life_account": {"investable": False},
        },
        "current_holdings": {"holdings": []},
        "dca_plan": {},
        "policy_config": {"drawdown_buy_policy": {"levels": []}},
    }

