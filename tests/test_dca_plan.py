import unittest

from drawdownguard.real_config import apply_real_profile


class DcaPlanConfigTest(unittest.TestCase):
    def test_weekly_thursday_and_monthly_gold_schedules(self):
        config = apply_real_profile(_base_config(), _real_data())
        assets = {asset["asset_id"]: asset for asset in config["portfolio_backtest"]["assets"]}

        nasdaq_schedules = assets["NASDAQ100"]["dca_schedules"]
        self.assertEqual(sum(item["amount"] for item in nasdaq_schedules), 50)
        self.assertEqual({item["fund_code"] for item in nasdaq_schedules}, {"270042", "012752"})
        self.assertEqual({item["weekday"] for item in nasdaq_schedules}, {3})

        gold_schedule = assets["GOLD"]["dca_schedules"][0]
        self.assertEqual(gold_schedule["frequency"], "monthly")
        self.assertEqual(gold_schedule["day"], 1)
        self.assertEqual(gold_schedule["amount"], 40)


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
                {"asset_id": "NASDAQ100", "asset_name": "纳斯达克100", "amount": 2181, "weight": 0.2035, "role": "core_growth", "funds": []},
                {"asset_id": "GOLD", "asset_name": "黄金", "amount": 763, "weight": 0.0712, "role": "hedge", "funds": []},
            ]
        },
        "dca_plan": {
            "weekly_day_index": 3,
            "weekly": [
                {"asset_id": "NASDAQ100", "fund_code": "270042", "fund_name": "广发纳指", "amount": 10},
                {"asset_id": "NASDAQ100", "fund_code": "012752", "fund_name": "建信纳指", "amount": 40},
            ],
            "monthly": [
                {"asset_id": "GOLD", "fund_code": "000216", "fund_name": "黄金", "amount": 40, "day": 1},
            ],
        },
        "policy_config": {"drawdown_buy_policy": {"levels": []}},
    }

