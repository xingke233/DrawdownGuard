import unittest

from drawdownguard.backtest import PortfolioBacktester
from drawdownguard.real_config import apply_real_profile, run_policy_checks
from main import collect_portfolio_histories


class FakePortfolioProvider:
    def __init__(self, histories):
        self.histories = histories

    def get_full_history(self, fund_code, nav_mode="unit_nav"):
        return {
            "history": self.histories.get(fund_code, []),
            "warnings": [],
            "nav_mode": nav_mode,
        }


class PortfolioRealConfigTest(unittest.TestCase):
    def test_portfolio_backtest_runs_with_real_config_and_fallback_schedule(self):
        config = apply_real_profile(_base_config(), _real_data())
        config["portfolio_backtest"]["start_date"] = "2026-01-01"
        histories = {
            "270042": [
                {"date": "2026-01-01", "nav": 1.0},
                {"date": "2026-01-08", "nav": 2.0},
            ],
            "012349": [
                {"date": "2026-01-01", "nav": 1.0},
                {"date": "2026-01-08", "nav": 1.0},
            ],
        }

        collected, warnings = collect_portfolio_histories(
            config["portfolio_backtest"],
            FakePortfolioProvider(histories),
        )
        report = PortfolioBacktester(config).run(collected)
        nasdaq = next(asset for asset in report["assets"] if asset["asset_id"] == "NASDAQ100")

        self.assertEqual(nasdaq["status"], "active")
        self.assertEqual(nasdaq["dca_invested"], 100)
        self.assertEqual([event["amount"] for event in nasdaq["events"] if event["type"] == "dca"], [10, 40, 10, 40])
        self.assertIn("012752", {event.get("fund_code") for event in nasdaq["events"]})
        self.assertTrue(any("012752" in warning["fund_code"] for warning in warnings if isinstance(warning, dict)))

    def test_missing_representative_history_skips_asset_without_crashing(self):
        config = apply_real_profile(_base_config(), _real_data())
        report = PortfolioBacktester(config).run({})

        self.assertTrue(all(asset["status"] == "skipped" for asset in report["assets"]))
        self.assertEqual(report["portfolio_summary"]["total_invested"], 0)

    def test_policy_check_passes_for_real_like_config(self):
        config = apply_real_profile(_base_config(), _real_data())
        report = run_policy_checks(config)

        self.assertTrue(report["passed"])


def _base_config():
    return {
        "peak_window_trading_days": 250,
        "round_amount_to": 10,
        "funds": [],
        "bullet_account": {"name": "余额宝", "balance": 0},
        "replenishment_levels": [{"drawdown_percent": 10, "cash_ratio": 0.15}],
        "portfolio_backtest": {"start_date": "2026-01-01"},
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
                    "asset_id": "CASHFLOW",
                    "asset_name": "自由现金流",
                    "amount": 574,
                    "weight": 0.0536,
                    "role": "quality_factor",
                    "funds": [{"code": "023918", "name": "自由现金流"}],
                },
                {
                    "asset_id": "DIVIDEND_LOW_VOL",
                    "asset_name": "红利低波",
                    "amount": 419,
                    "weight": 0.039,
                    "role": "value_factor",
                    "nav_mode": "accumulated_nav",
                    "funds": [{"code": "008163", "name": "红利低波"}],
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
            "weekly": [
                {"asset_id": "NASDAQ100", "fund_code": "270042", "fund_name": "广发纳指", "amount": 10},
                {"asset_id": "NASDAQ100", "fund_code": "012752", "fund_name": "建信纳指", "amount": 40},
                {"asset_id": "HSTECH", "fund_code": "012349", "fund_name": "恒生科技", "amount": 25},
            ],
            "monthly": [{"asset_id": "GOLD", "fund_code": "000216", "fund_name": "黄金", "amount": 40, "day": 1}],
        },
        "policy_config": {
            "drawdown_buy_policy": {
                "allowed_fund_codes": ["270042", "012752", "012349"],
                "blocked_fund_codes": ["023918", "008163", "000216"],
                "levels": [{"drawdown_percent": 10, "cash_ratio": 0.15}],
            }
        },
    }

