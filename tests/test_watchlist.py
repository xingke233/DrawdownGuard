import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from drawdownguard.committee_report import build_committee_report
from drawdownguard.storage import Storage
from drawdownguard.watchlist import (
    add_watchlist_fund,
    analyze_all_watchlist,
    analyze_portfolio_fit,
    analyze_watchlist_fund,
    promote_watchlist_fund,
    remove_watchlist_fund,
    summarize_watchlist,
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
        self.assertEqual(item["nav_mode"], "unit_nav")
        self.assertEqual(item["notes"], "")

    def test_duplicate_add_does_not_duplicate(self):
        watchlist = {"funds": [{"fund_code": "999999", "fund_name": "候选基金"}]}

        updated, item = add_watchlist_fund(watchlist, "999999", "候选基金")

        self.assertEqual(len(updated["funds"]), 1)
        self.assertTrue(item["already_exists"])

    def test_watchlist_report_empty_does_not_crash(self):
        self.assertIn("当前没有观察基金", summarize_watchlist({"funds": []}))

    def test_watchlist_storage_does_not_pollute_real_configs(self):
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            storage = Storage(base)
            storage.save_watchlist_funds({"funds": [{"fund_code": "999999"}]})
            (base / "data" / "current_holdings.json").write_text(json.dumps({"holdings": []}), encoding="utf-8")
            (base / "data" / "dca_plan.json").write_text(json.dumps({"plans": []}), encoding="utf-8")
            (base / "data" / "policy_config.json").write_text(json.dumps({"drawdown_buy_policy": {}}), encoding="utf-8")

            holdings = json.loads((base / "data" / "current_holdings.json").read_text(encoding="utf-8"))
            dca_plan = json.loads((base / "data" / "dca_plan.json").read_text(encoding="utf-8"))
            policy = json.loads((base / "data" / "policy_config.json").read_text(encoding="utf-8"))

        self.assertEqual(holdings, {"holdings": []})
        self.assertEqual(dca_plan, {"plans": []})
        self.assertEqual(policy, {"drawdown_buy_policy": {}})

    def test_watchlist_file_auto_created_when_missing(self):
        with TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))

            watchlist = storage.load_watchlist_funds()

            self.assertEqual(watchlist, {"funds": []})
            self.assertTrue((Path(temp_dir) / "data" / "watchlist_funds.json").exists())

    def test_watchlist_analyze_insufficient_data_does_not_crash(self):
        watchlist = {"funds": [{"fund_code": "999999", "fund_name": "候选基金", "candidate_role": "theme", "nav_mode": "unit_nav"}]}

        report = analyze_watchlist_fund(_config(), FakeProvider(_history([1.0, 1.1])), watchlist, "999999")

        self.assertEqual(report["quant_signal"]["status"], "available")
        self.assertIn("净值数据不足120条", " ".join(report["warnings"]))
        self.assertEqual(report["portfolio_fit"]["suggested_action"], "need_more_history")

    def test_watchlist_analyze_missing_data_does_not_crash(self):
        watchlist = {"funds": [{"fund_code": "999999", "fund_name": "候选基金", "candidate_role": "theme", "nav_mode": "unit_nav"}]}

        report = analyze_watchlist_fund(_config(), FakeProvider([]), watchlist, "999999")

        self.assertEqual(report["data_check"]["status"], "missing")
        self.assertEqual(report["portfolio_fit"]["suggested_action"], "data_insufficient")

    def test_promote_does_not_modify_real_config(self):
        watchlist = {"funds": [{"fund_code": "999999", "fund_name": "候选基金", "candidate_role": "satellite", "nav_mode": "unit_nav"}]}

        report = promote_watchlist_fund(watchlist, "999999")

        self.assertIn("不自动修改真实持仓", report["message"])
        self.assertFalse(report["policy_reminder"]["allow_dca"])
        self.assertFalse(report["policy_reminder"]["allow_drawdown_buy"])
        self.assertIn("holding-add", report["holding_add_command"])
        self.assertIn("dca-add", report["dca_add_command"])

    def test_committee_report_can_show_watchlist(self):
        watchlist = {"funds": [{"fund_code": "999999", "fund_name": "候选基金", "candidate_role": "satellite", "nav_mode": "unit_nav"}]}
        analysis = analyze_all_watchlist(_config(), FakeProvider(_history([1 + index * 0.01 for index in range(260)])), watchlist)

        report = build_committee_report(_config(), watchlist_report=analysis, watchlist_funds=watchlist)

        self.assertIn("观察基金", report["markdown"])
        self.assertIn("999999 候选基金", report["markdown"])
        self.assertIn("Category", report["markdown"])
        self.assertIn("Overlap", report["markdown"])

    def test_committee_report_can_show_unanalyzed_watchlist(self):
        watchlist = {"funds": [{"fund_code": "999999", "fund_name": "候选基金", "candidate_role": "satellite", "nav_mode": "unit_nav"}]}

        report = build_committee_report(_config(), watchlist_funds=watchlist)

        self.assertIn("999999 候选基金", report["markdown"])
        self.assertIn("尚未分析", report["markdown"])

    def test_analyze_all_watchlist_generates_summary_funds(self):
        watchlist = {"funds": [{"fund_code": "999999", "fund_name": "候选基金", "candidate_role": "satellite", "nav_mode": "unit_nav"}]}

        report = analyze_all_watchlist(_config(), FakeProvider(_history([1 + index * 0.01 for index in range(260)])), watchlist)

        self.assertEqual(report["summary_funds"][0]["fund_code"], "999999")

    def test_no_overlap_does_not_output_duplicate_conclusion(self):
        fit = analyze_portfolio_fit(
            _realistic_config(),
            {"fund_code": "888888", "fund_name": "农业主题基金", "reason": "农业", "candidate_role": "satellite"},
            signal=_signal(quant_score=65),
        )

        self.assertEqual(fit["possible_overlap_assets"], [])
        self.assertEqual(fit["overlap_type"], "none")
        self.assertNotIn("重复", fit["message"])
        self.assertNotEqual(fit["suggested_action"], "consider_replace_existing")

    def test_insufficient_history_priority_over_replace_existing(self):
        fit = analyze_portfolio_fit(
            _realistic_config(),
            {"fund_code": "025857", "fund_name": "电网基金", "reason": "关注电网", "candidate_role": "satellite"},
            signal=_signal(warnings=["净值数据不足250条，当前仅133条，仍按现有数据计算。"]),
        )

        self.assertEqual(fit["candidate_category"], "infrastructure_or_utility")
        self.assertEqual(fit["overlap_type"], "insufficient_history")
        self.assertEqual(fit["suggested_action"], "need_more_history")

    def test_cpo_is_broad_style_not_exact_overlap(self):
        fit = analyze_portfolio_fit(
            _realistic_config(),
            {"fund_code": "018957", "fund_name": "某CPO基金", "reason": "关注CPO", "candidate_role": "satellite"},
            signal=_signal(quant_score=80, drawdown=-0.08),
        )

        self.assertEqual(fit["candidate_category"], "high_risk_tech_theme")
        self.assertEqual(fit["overlap_type"], "broad_style_overlap")
        self.assertEqual(fit["possible_overlap_assets"], ["ACTIVE_ADVANCED_MANUFACTURING", "HSTECH", "NASDAQ100"])
        self.assertNotEqual(fit["suggested_action"], "consider_replace_existing")

    def test_silver_is_not_exact_gold_overlap(self):
        fit = analyze_portfolio_fit(
            _realistic_config(),
            {"fund_code": "161226", "fund_name": "白银基金", "reason": "关注白银", "candidate_role": "satellite"},
            signal=_signal(quant_score=55, drawdown=-0.12),
        )

        self.assertEqual(fit["candidate_category"], "commodity_cycle")
        self.assertEqual(fit["overlap_type"], "broad_commodity_overlap")
        self.assertEqual(fit["possible_overlap_assets"], ["GOLD"])
        self.assertEqual(fit["suggested_action"], "keep_watching")

    def test_nasdaq_candidate_is_exact_overlap(self):
        fit = analyze_portfolio_fit(
            _realistic_config(),
            {"fund_code": "777777", "fund_name": "纳指100联接", "reason": "纳指替代", "candidate_role": "core"},
            signal=_signal(quant_score=70, drawdown=-0.05),
        )

        self.assertEqual(fit["overlap_type"], "exact_overlap")
        self.assertEqual(fit["suggested_action"], "consider_replace_existing")

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


def _realistic_config():
    config = _config()
    config["holdings"].extend(
        [
            {"asset_id": "HSTECH", "asset_name": "恒生科技", "role": "satellite_opportunity", "funds": [{"code": "012349"}]},
            {"asset_id": "ACTIVE_ADVANCED_MANUFACTURING", "asset_name": "先进制造", "role": "active_fund", "funds": [{"code": "018125"}]},
            {"asset_id": "GOLD", "asset_name": "黄金", "role": "hedge", "funds": [{"code": "000216"}]},
            {"asset_id": "DIVIDEND_LOW_VOL", "asset_name": "红利低波", "role": "value_factor", "funds": [{"code": "008163"}]},
        ]
    )
    return config


def _signal(quant_score=50, drawdown=-0.05, warnings=None):
    return {
        "status": "available",
        "quant_score": quant_score,
        "drawdown_from_250d_high": drawdown,
        "tags": [],
        "warnings": warnings or [],
    }
