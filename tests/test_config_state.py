import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from drawdownguard.backtest import PortfolioBacktester
from drawdownguard.config_manager import ConfigManager
from drawdownguard.real_config import apply_real_profile, summarize_dca_report, summarize_holdings_report, summarize_profile
from drawdownguard.rebalance_advisor import build_rebalance_advice


class ConfigStateEnforcementTest(unittest.TestCase):
    def test_paused_dca_does_not_participate_in_portfolio_backtest(self):
        config = _config_with_state(dca_status="paused")
        histories = {"270042": _history()}

        report = PortfolioBacktester(config).run(histories)

        asset = report["assets"][0]
        self.assertEqual(asset["dca_invested"], 0)

    def test_resumed_dca_participates_in_portfolio_backtest(self):
        config = _config_with_state(dca_status="active")
        histories = {"270042": _history()}

        report = PortfolioBacktester(config).run(histories)

        asset = report["assets"][0]
        self.assertGreater(asset["dca_invested"], 0)

    def test_missing_dca_status_defaults_to_active(self):
        config = _config_with_state(dca_status=None)
        histories = {"270042": _history()}

        report = PortfolioBacktester(config).run(histories)

        self.assertGreater(report["assets"][0]["dca_invested"], 0)

    def test_paused_dca_appears_in_dca_report(self):
        config = _config_with_state(dca_status="paused")

        text = summarize_dca_report(config)

        self.assertIn("paused 定投", text)
        self.assertIn("012752", text)
        self.assertIn("暂停定投数量：1", text)

    def test_profile_report_separates_active_and_paused_dca(self):
        config = _config_with_state(dca_status="paused")

        text = summarize_profile(config)

        self.assertIn("当前 active 定投计划", text)
        self.assertIn("已暂停定投计划", text)

    def test_removed_holding_not_in_current_weights_or_rebalance(self):
        config = _config_with_removed_holding()

        totals = config["portfolio_backtest"]["assets"]
        advice = build_rebalance_advice(config)

        self.assertFalse(any(asset["asset_id"] == "NONFERROUS_METALS" for asset in totals))
        self.assertFalse(any(item["asset_id"] == "NONFERROUS_METALS" for item in advice["asset_advice"]))

    def test_removed_holding_appears_in_holdings_history_section(self):
        config = _config_with_removed_holding()

        text = summarize_holdings_report(config)

        self.assertIn("历史/已移除持仓", text)
        self.assertIn("NONFERROUS_METALS", text)

    def test_watchlist_does_not_enter_real_portfolio_config(self):
        config = _config_with_state(dca_status="active")

        self.assertFalse(any(asset.get("asset_id") == "WATCHLIST" for asset in config.get("portfolio_backtest", {}).get("assets", [])))
        self.assertFalse(any(asset.get("asset_id") == "WATCHLIST" for asset in config.get("holdings", [])))

    def test_dca_report_active_totals(self):
        config = _config_with_state(dca_status="active")

        text = summarize_dca_report(config)

        self.assertIn("每周 active 定投总额：40.00 元", text)
        self.assertIn("每月 active 定投总额：0.00 元", text)

    def test_config_change_log_records_state_changes(self):
        with TemporaryDirectory() as temp_dir:
            base = _write_config(Path(temp_dir))
            manager = ConfigManager(base)
            result = manager.set_dca_status("012752", "paused")
            manager.log_change(result["operation"], result["target"], result["before"], result["after"], result["backup_path"], {"passed": True})
            logs = manager.recent_logs()

        self.assertEqual(logs[-1]["operation"], "dca-pause")
        self.assertEqual(logs[-1]["before"]["status"], "active")
        self.assertEqual(logs[-1]["after"]["status"], "paused")

    def test_holding_remove_marks_removed_instead_of_deleting(self):
        with TemporaryDirectory() as temp_dir:
            base = _write_config(Path(temp_dir))
            ConfigManager(base).remove_holding("016708")
            config = apply_real_profile(_base_config(), _real_data_from_files(base))

        self.assertTrue(config["removed_holdings"])
        self.assertFalse(any(asset.get("asset_id") == "NONFERROUS_METALS" for asset in config["holdings"]))


def _config_with_state(dca_status="active"):
    dca_item = {
        "asset_id": "NASDAQ100",
        "fund_code": "012752",
        "fund_name": "建信纳指",
        "amount": 40,
    }
    if dca_status is not None:
        dca_item["status"] = dca_status
    return apply_real_profile(
        _base_config(),
        {
            "user_profile": {"bullet_cash": {"amount": 1883}, "life_account": {}, "target_allocation": {}},
            "current_holdings": {
                "holdings": [
                    {"asset_id": "CASH", "asset_name": "现金", "amount": 1000, "weight": 0.3, "role": "bullet_cash", "funds": []},
                    {
                        "asset_id": "NASDAQ100",
                        "asset_name": "纳斯达克100",
                        "amount": 2000,
                        "weight": 0.7,
                        "role": "core_growth",
                        "funds": [{"code": "270042", "name": "广发纳指", "amount": 2000, "weight": 0.7}],
                    },
                ]
            },
            "dca_plan": {"weekly_day_index": 3, "weekly": [dca_item], "monthly": []},
            "policy_config": {"drawdown_buy_policy": {"allowed_fund_codes": ["270042"], "blocked_fund_codes": [], "levels": []}},
        },
    )


def _config_with_removed_holding():
    return apply_real_profile(
        _base_config(),
        {
            "user_profile": {"bullet_cash": {"amount": 1883}, "life_account": {}, "target_allocation": {}},
            "current_holdings": {
                "holdings": [
                    {"asset_id": "CASH", "asset_name": "现金", "amount": 1000, "weight": 0.5, "role": "bullet_cash", "funds": []},
                    {
                        "asset_id": "NONFERROUS_METALS",
                        "asset_name": "有色金属",
                        "amount": 106,
                        "weight": 0.5,
                        "role": "cyclical_theme",
                        "status": "removed",
                        "archived": True,
                        "funds": [{"code": "016708", "name": "有色", "amount": 106, "weight": 0.5, "status": "removed", "archived": True}],
                    },
                ]
            },
            "dca_plan": {"weekly": [], "monthly": []},
            "policy_config": {"drawdown_buy_policy": {"allowed_fund_codes": [], "blocked_fund_codes": [], "levels": []}},
        },
    )


def _base_config():
    return {
        "funds": [],
        "bullet_account": {"name": "余额宝", "balance": 0},
        "replenishment_levels": [],
        "portfolio_backtest": {"start_date": "2026-01-01"},
    }


def _history():
    return [{"date": f"2026-01-{day:02d}", "nav": 1 + day * 0.01} for day in range(1, 29)]


def _write_config(base):
    data = base / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "user_profile.json").write_text('{"bullet_cash":{"amount":1883}}', encoding="utf-8")
    (data / "current_holdings.json").write_text(
        '{"holdings":[{"asset_id":"NONFERROUS_METALS","asset_name":"有色金属","amount":106,"weight":1,"role":"cyclical_theme","funds":[{"code":"016708","name":"有色","amount":106,"weight":1}]}]}',
        encoding="utf-8",
    )
    (data / "dca_plan.json").write_text('{"weekly":[{"asset_id":"NONFERROUS_METALS","fund_code":"012752","fund_name":"建信纳指","amount":40}],"monthly":[]}', encoding="utf-8")
    (data / "policy_config.json").write_text('{"drawdown_buy_policy":{"allowed_fund_codes":[],"blocked_fund_codes":[],"levels":[]}}', encoding="utf-8")
    (data / "watchlist_funds.json").write_text('{"funds":[]}', encoding="utf-8")
    return base


def _real_data_from_files(base):
    import json

    data = base / "data"
    return {
        "user_profile": json.loads((data / "user_profile.json").read_text(encoding="utf-8")),
        "current_holdings": json.loads((data / "current_holdings.json").read_text(encoding="utf-8")),
        "dca_plan": json.loads((data / "dca_plan.json").read_text(encoding="utf-8")),
        "policy_config": json.loads((data / "policy_config.json").read_text(encoding="utf-8")),
    }
