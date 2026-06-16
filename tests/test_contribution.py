import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from drawdownguard.contribution import run_contribution_analysis, summarize_contribution_report
from drawdownguard.storage import Storage


class ContributionReportTest(unittest.TestCase):
    def setUp(self):
        self.portfolio_report = {
            "portfolio_summary": {
                "total_invested": 300,
                "final_market_value": 340,
                "total_profit": 40,
                "total_return_rate": 40 / 300,
            },
            "assets": [
                {
                    "asset_id": "NASDAQ100",
                    "asset_name": "纳斯达克100",
                    "representative_fund": "270042",
                    "status": "active",
                    "total_invested": 200,
                    "final_market_value": 250,
                    "total_profit": 50,
                    "total_return_rate": 0.25,
                    "events": [
                        {
                            "date": "2026-01-01",
                            "type": "dca",
                            "nav": 1.0,
                            "amount": 100,
                            "shares": 100,
                        }
                    ],
                    "series": [
                        {"date": "2026-01-01", "nav": 1.0},
                        {"date": "2026-01-02", "nav": 1.5},
                        {"date": "2026-01-03", "nav": 1.2},
                    ],
                },
                {
                    "asset_id": "GOLD",
                    "asset_name": "黄金",
                    "representative_fund": "000216",
                    "status": "active",
                    "total_invested": 100,
                    "final_market_value": 90,
                    "total_profit": -10,
                    "total_return_rate": -0.1,
                    "events": [],
                    "series": [
                        {"date": "2026-01-01", "nav": 1.0},
                        {"date": "2026-01-02", "nav": 0.95},
                    ],
                },
            ],
            "warnings": [],
        }

    def test_profit_contribution_and_weights(self):
        report = run_contribution_analysis(self.portfolio_report)
        nasdaq = report["assets"][0]
        gold = report["assets"][1]

        self.assertAlmostEqual(nasdaq["profit_contribution_percent"], 1.25)
        self.assertAlmostEqual(gold["profit_contribution_percent"], -0.25)
        self.assertAlmostEqual(nasdaq["investment_weight"], 200 / 300)
        self.assertAlmostEqual(gold["market_value_weight"], 90 / 340)

    def test_identifies_best_worst_and_risk_metrics(self):
        report = run_contribution_analysis(self.portfolio_report)
        summary = report["portfolio_summary"]
        nasdaq = report["assets"][0]

        self.assertEqual(summary["best_profit_contributor"]["asset_id"], "NASDAQ100")
        self.assertEqual(summary["worst_profit_contributor"]["asset_id"], "GOLD")
        self.assertEqual(summary["highest_return_asset"]["asset_id"], "NASDAQ100")
        self.assertEqual(summary["lowest_return_asset"]["asset_id"], "GOLD")
        self.assertAlmostEqual(nasdaq["max_drawdown"], -0.2)
        self.assertGreater(nasdaq["volatility"], 0)
        self.assertIsNotNone(nasdaq["sharpe_like_ratio"])

    def test_insufficient_data_does_not_crash(self):
        sparse_report = {
            "portfolio_summary": {"total_invested": 0, "final_market_value": 0, "total_profit": 0},
            "assets": [
                {
                    "asset_id": "CASHFLOW",
                    "asset_name": "自由现金流",
                    "status": "skipped",
                    "skip_reason": "净值数据缺失",
                    "total_invested": 0,
                    "final_market_value": 0,
                    "total_profit": 0,
                    "events": [],
                    "series": [],
                }
            ],
        }

        report = run_contribution_analysis(sparse_report)

        self.assertEqual(report["assets"][0]["profit_contribution_percent"], None)
        self.assertEqual(report["assets"][0]["investment_weight"], 0)
        self.assertEqual(report["assets"][0]["market_value_weight"], 0)
        self.assertIsNone(report["assets"][0]["max_drawdown"])
        self.assertIn("风险指标数据不足", report["assets"][0]["warnings"][0])

    def test_storage_saves_contribution_report(self):
        report = run_contribution_analysis(self.portfolio_report)
        with TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))

            storage.save_contribution_report(report)
            saved = json.loads(
                (Path(temp_dir) / "data" / "contribution_report.json").read_text(encoding="utf-8")
            )

            self.assertEqual(saved["portfolio_summary"]["best_profit_contributor"]["asset_id"], "NASDAQ100")
            self.assertEqual(storage.load_contribution_report(), saved)

    def test_summarize_contribution_report(self):
        report = run_contribution_analysis(self.portfolio_report)

        summary = summarize_contribution_report(report)
        detail = summarize_contribution_report(report, detail=True)

        self.assertIn("资产贡献分析报告", summary)
        self.assertIn("最大收益贡献资产：NASDAQ100", summary)
        self.assertIn("各资产贡献：", summary)
        self.assertIn("事件数量", detail)


if __name__ == "__main__":
    unittest.main()
