import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from drawdownguard.committee_report import build_committee_report
from drawdownguard.storage import Storage
from drawdownguard.watchlist import (
    add_watchlist_fund,
    analyze_all_watchlist,
    analyze_watchlist_fund,
    promote_watchlist_fund,
    remove_watchlist_fund,
)


class WatchlistTest(unittest.TestCase):
    def test_watchlist_add_writes_defaults(self):
        updated, item = add_watchlist_fund(
            {"funds": []},
            "999999",
            "候选基金",
            role="satellite",
            reason="关注原因",
        )

        self.assertEqual(updated["funds"][0]["fund_code"], "999999")
        self.assertFalse(item["allow_drawdown_buy"])
        self.assertFalse(item["allow_dca"])
        self.assertEqual(item["status"], "watching")

    def test_watchlist_storage_does_not_pollute_current_holdings(self):
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            storage = Storage(base)
            storage.save_watchlist_funds({"funds": [{"fund_code": "999999"}]})
            (base / "data" / "current_holdings.json").write_text(json.dumps({"holdings": []}), encoding="utf-8")

            holdings = json.loads((base / "data" / "current_holdings.json").read_text(encoding="utf-8"))

        self.assertEqual(holdings, {"holdings": []})

    def test_watchlist_analyze_insufficient_data_does_not_crash(self):
        watchlist = {"funds": [{"fund_code": "999999", "fund_name": "候选基金", "candidate_role": "theme", "nav_mode": "unit_nav"}]}

        report = analyze_watchlist_fund(_config(), FakeProvider(_history([1.0, 1.1])), watchlist, "999999")

        self.assertEqual(report["quant_signal"]["status"], "available")
        self.assertIn("净值数据不足120条", " ".join(report["warnings"]))

    def test_promote_does_not_modify_real_config(self):
        watchlist = {"funds": [{"fund_code": "999999", "fund_name": "候选基金", "candidate_role": "satellite", "nav_mode": "unit_nav"}]}

        report = promote_watchlist_fund(watchlist, "999999")

        self.assertIn("不自动修改真实持仓", report["message"])
        self.assertFalse(report["policy_reminder"]["allow_dca"])
        self.assertFalse(report["policy_reminder"]["allow_drawdown_buy"])

    def test_committee_report_can_show_watchlist(self):
        watchlist = {"funds": [{"fund_code": "999999", "fund_name": "候选基金", "candidate_role": "satellite", "nav_mode": "unit_nav"}]}
        analysis = analyze_all_watchlist(_config(), FakeProvider(_history([1 + index * 0.01 for index in range(260)])), watchlist)

        report = build_committee_report(_config(), watchlist_report=analysis)

        self.assertIn("观察基金", report["markdown"])
        self.assertIn("999999 候选基金", report["markdown"])

    def test_remove_watchlist_fund(self):
        updated = remove_watchlist_fund({"funds": [{"fund_code": "999999"}]}, "999999")

        self.assertEqual(updated, {"funds": []})


class FakeProvider:
    def __init__(self, history):
        self.history = history

    def get_full_history(self, fund_code, nav_mode="unit_nav"):
        return {
            "history": self.history,
            "source": "local",
            "warnings": [],
            "nav_mode": nav_mode,
        }


def _history(values):
    return [{"date": f"2026-{index + 1:04d}", "nav": value} for index, value in enumerate(values)]


def _config():
    return {
        "funds": [],
        "bullet_account": {"name": "余额宝", "balance": 1883},
        "holdings": [
            {
                "asset_id": "NASDAQ100",
                "asset_name": "纳斯达克100",
                "role": "core_growth",
                "funds": [{"code": "270042", "name": "广发纳指"}],
            }
        ],
    }
