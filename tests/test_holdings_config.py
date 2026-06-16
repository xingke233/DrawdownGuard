import unittest

from drawdownguard.real_config import apply_real_profile, current_holdings, summarize_holdings


class HoldingsConfigTest(unittest.TestCase):
    def test_holdings_totals_exclude_cleared_assets_and_merge_groups(self):
        config = apply_real_profile(_base_config(), _real_data())
        holdings = current_holdings(config)
        totals = summarize_holdings(config)

        self.assertNotIn("CASH", {asset["asset_id"] for asset in holdings})
        self.assertEqual(totals["nasdaq_amount"], 2181)
        self.assertAlmostEqual(totals["nasdaq_weight"], 0.2035)
        self.assertEqual(totals["bonds_amount"], 3963)
        self.assertAlmostEqual(totals["bonds_weight"], 0.3696)
        self.assertEqual(config["cleared_assets"], ["东方人工智能主题混合C"])

    def test_cash_weight_is_kept_for_profile_summary(self):
        config = apply_real_profile(_base_config(), _real_data())
        cash = next(asset for asset in config["holdings"] if asset["asset_id"] == "CASH")

        self.assertEqual(cash["amount"], 1883)
        self.assertAlmostEqual(cash["weight"], 0.1756)

    def test_profile_asset_categories_follow_committee_definition(self):
        config = apply_real_profile(_base_config(), _real_data())
        totals = summarize_holdings(config)

        self.assertAlmostEqual(totals["cash_weight"], 0.1756)
        self.assertAlmostEqual(totals["core_weight"], 0.2035)
        self.assertAlmostEqual(totals["satellite_weight"], 0.1801)
        self.assertAlmostEqual(totals["defensive_weight"], 0.4408)
        self.assertNotAlmostEqual(totals["core_weight"], 0.2035 + 0.1756)
        self.assertAlmostEqual(
            totals["cash_weight"]
            + totals["core_weight"]
            + totals["satellite_weight"]
            + totals["defensive_weight"],
            1.0,
        )


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
                {"asset_id": "CASH", "asset_name": "余额宝", "amount": 1883, "weight": 0.1756, "role": "bullet_cash", "funds": []},
                {
                    "asset_id": "NASDAQ100",
                    "asset_name": "纳斯达克100",
                    "amount": 2181,
                    "weight": 0.2035,
                    "role": "core_growth",
                    "funds": [
                        {"code": "270042", "name": "广发纳指", "amount": 2038, "weight": 0.1901},
                        {"code": "012752", "name": "建信纳指", "amount": 143, "weight": 0.0134},
                    ],
                },
                {
                    "asset_id": "BONDS",
                    "asset_name": "债券",
                    "amount": 3963,
                    "weight": 0.3696,
                    "role": "bond_stabilizer",
                    "funds": [
                        {"code": "110017", "name": "易方达增强回报债券A", "amount": 2761, "weight": 0.2575},
                    ],
                },
                {
                    "asset_id": "HSTECH",
                    "asset_name": "恒生科技",
                    "amount": 290,
                    "weight": 0.0271,
                    "role": "satellite_opportunity",
                    "funds": [],
                },
                {
                    "asset_id": "CASHFLOW",
                    "asset_name": "自由现金流",
                    "amount": 574,
                    "weight": 0.0536,
                    "role": "quality_factor",
                    "funds": [],
                },
                {
                    "asset_id": "DIVIDEND_LOW_VOL",
                    "asset_name": "红利低波",
                    "amount": 419,
                    "weight": 0.0390,
                    "role": "value_factor",
                    "funds": [],
                },
                {
                    "asset_id": "ACTIVE_ADVANCED_MANUFACTURING",
                    "asset_name": "先进制造",
                    "amount": 542,
                    "weight": 0.0505,
                    "role": "active_fund",
                    "funds": [],
                },
                {
                    "asset_id": "NONFERROUS_METALS",
                    "asset_name": "有色金属",
                    "amount": 106,
                    "weight": 0.0099,
                    "role": "cyclical_theme",
                    "funds": [],
                },
                {
                    "asset_id": "GOLD",
                    "asset_name": "黄金",
                    "amount": 763,
                    "weight": 0.0712,
                    "role": "hedge",
                    "funds": [],
                },
            ],
            "cleared_assets": ["东方人工智能主题混合C"],
        },
        "dca_plan": {},
        "policy_config": {"drawdown_buy_policy": {"levels": []}},
    }
