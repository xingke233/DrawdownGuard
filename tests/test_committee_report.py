import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from drawdownguard.committee_report import build_committee_report
from drawdownguard.real_config import apply_real_profile
from drawdownguard.rebalance_advisor import build_rebalance_advice
from drawdownguard.storage import Storage


class CommitteeReportTest(unittest.TestCase):
    def test_missing_reports_do_not_crash(self):
        config = apply_real_profile(_base_config(), _real_data())

        report = build_committee_report(config)

        self.assertEqual(report["sections"]["daily_drawdown_check"]["status"], "missing")
        self.assertEqual(report["sections"]["portfolio_backtest_summary"]["status"], "missing")
        self.assertEqual(report["sections"]["contribution_analysis"]["status"], "missing")
        self.assertEqual(report["sections"]["rebalance_advice"]["status"], "missing")
        self.assertIn("暂无数据", report["markdown"])

    def test_markdown_and_json_are_saved(self):
        config = apply_real_profile(_base_config(), _real_data())
        rebalance = build_rebalance_advice(config)
        report = build_committee_report(config, rebalance_advice=rebalance)

        with TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))
            storage.save_committee_report(report)

            md_path = Path(temp_dir) / "data" / "committee_report.md"
            json_path = Path(temp_dir) / "data" / "committee_report.json"

            self.assertTrue(md_path.exists())
            self.assertTrue(json_path.exists())
            self.assertIn("DrawdownGuard 个人投委会报告", md_path.read_text(encoding="utf-8"))
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertIn("sections", saved)
            self.assertNotIn("markdown", saved)

    def test_conclusion_contains_core_advice(self):
        config = apply_real_profile(_base_config(), _real_data())
        rebalance = build_rebalance_advice(config)

        report = build_committee_report(config, rebalance_advice=rebalance)
        conclusion = "\n".join(report["sections"]["committee_conclusion"])

        self.assertIn("NASDAQ100 仍是长期核心", conclusion)
        self.assertIn("子弹仓应保留", conclusion)
        self.assertIn("HSTECH 不追补历史回撤", conclusion)
        self.assertIn("债券不新增或少新增", conclusion)

    def test_available_sections_are_rendered(self):
        config = apply_real_profile(_base_config(), _real_data())
        daily_logs = [
            {
                "date": "2026-06-16",
                "fund_code": "270042",
                "fund_name": "广发纳指",
                "drawdown": -0.08,
                "status": "未触发",
                "suggestions": {},
                "warnings": ["历史回撤不追补"],
            }
        ]
        portfolio_report = {
            "portfolio_summary": {
                "start_date": "2018-01-01",
                "end_date": "2026-06-16",
                "total_invested": 1000,
                "final_market_value": 1200,
                "total_return_rate": 0.2,
                "trigger_count_total": 3,
                "total_bullet_invested": 300,
                "bullet_cash_initial": 1883,
                "bullet_cash_final": 1583,
            }
        }
        contribution_report = {
            "portfolio_summary": {
                "best_profit_contributor": {"asset_id": "NASDAQ100", "asset_name": "纳斯达克100"},
                "worst_profit_contributor": {"asset_id": "HSTECH", "asset_name": "恒生科技"},
            },
            "assets": [
                {
                    "asset_id": "NASDAQ100",
                    "asset_name": "纳斯达克100",
                    "total_profit": 200,
                    "profit_contribution_percent": 1.0,
                    "total_return_rate": 0.2,
                }
            ],
        }
        rebalance = build_rebalance_advice(config)

        report = build_committee_report(
            config,
            daily_logs=daily_logs,
            portfolio_backtest_report=portfolio_report,
            contribution_report=contribution_report,
            rebalance_advice=rebalance,
        )

        self.assertIn("今日补仓检查", report["markdown"])
        self.assertIn("组合回测摘要", report["markdown"])
        self.assertIn("资产贡献分析", report["markdown"])
        self.assertIn("再平衡建议", report["markdown"])


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
            "investor_profile": {
                "age": 20,
                "style": "growth",
                "target_annual_return": 0.10,
                "max_account_drawdown_tolerance": 0.30,
            },
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
        "dca_plan": {},
        "policy_config": {
            "drawdown_buy_policy": {
                "allowed_fund_codes": ["270042", "012752", "012349"],
                "blocked_fund_codes": [],
                "levels": [],
            }
        },
    }

