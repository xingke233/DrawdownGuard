import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from drawdownguard.portfolio_strategy import (
    calculate_strategy_scores,
    classify_asset,
    drawdown_actions,
    normalize_weights,
    run_portfolio_strategy_synth,
)
from drawdownguard.storage import Storage


class PortfolioStrategySynthTest(unittest.TestCase):
    def setUp(self):
        self.portfolio_report = {
            "portfolio_summary": {"total_return_rate": 0.2},
            "assets": [
                {
                    "asset_id": "NASDAQ100",
                    "asset_name": "纳斯达克100",
                    "representative_fund": "270042",
                    "total_invested": 100,
                    "final_market_value": 150,
                    "total_profit": 50,
                    "total_return_rate": 0.5,
                    "series": [{"nav": 1.0}, {"nav": 1.5}, {"nav": 1.2}],
                },
                {
                    "asset_id": "GOLD",
                    "asset_name": "黄金",
                    "representative_fund": "000216",
                    "total_invested": 100,
                    "final_market_value": 120,
                    "total_profit": 20,
                    "total_return_rate": 0.2,
                    "series": [{"nav": 1.0}, {"nav": 1.1}, {"nav": 1.05}],
                },
                {
                    "asset_id": "DIVIDEND_LOW_VOL",
                    "asset_name": "红利低波",
                    "representative_fund": "008163",
                    "total_invested": 100,
                    "final_market_value": 90,
                    "total_profit": -10,
                    "total_return_rate": -0.1,
                    "series": [{"nav": 1.0}, {"nav": 0.95}, {"nav": 0.9}],
                },
            ],
        }
        best_strategy = {
            "frequency": "weekly",
            "amount_mode": "fixed",
            "drawdown_rule": "none",
            "high_level_rule": "none",
            "total_return_rate": 0.1,
            "max_drawdown": -0.1,
            "volatility": 0.02,
            "sharpe_like_ratio": 5,
        }
        self.dca_report = {
            "assets": [
                {"asset_id": "NASDAQ100", "best_strategy": best_strategy},
                {"asset_id": "GOLD", "best_strategy": {**best_strategy, "amount_mode": "decreasing"}},
                {"asset_id": "DIVIDEND_LOW_VOL", "best_strategy": {**best_strategy, "amount_mode": "volatility_scaled"}},
            ]
        }

    def test_asset_classification(self):
        self.assertEqual(classify_asset("NASDAQ100"), "growth")
        self.assertEqual(classify_asset("GOLD"), "hedge")
        self.assertEqual(classify_asset("DIVIDEND_LOW_VOL"), "defensive")
        self.assertEqual(classify_asset("HSTECH"), "satellite")
        self.assertEqual(classify_asset("CASHFLOW"), "experimental")

    def test_weight_normalization(self):
        weights = normalize_weights({"A": 2, "B": 1})

        self.assertAlmostEqual(sum(weights.values()), 1)
        self.assertAlmostEqual(weights["A"], 2 / 3)

    def test_drawdown_trigger_actions(self):
        self.assertIn("暂停卫星资产定投", drawdown_actions(-0.10)["actions"])
        self.assertIn("削减非核心资产", drawdown_actions(-0.15)["actions"])
        self.assertIn("全部资金集中纳指 + 黄金", drawdown_actions(-0.20)["actions"])

    def test_strategy_score_calculation(self):
        scores = calculate_strategy_scores(0.2, -0.1, 0.05, 0.6, 0.4)

        self.assertGreater(scores["stability_score"], 0)
        self.assertGreater(scores["growth_score"], 0)
        self.assertAlmostEqual(scores["sharpe_like_ratio"], 4.0)

    def test_report_json_completeness(self):
        report = run_portfolio_strategy_synth(self.portfolio_report, self.dca_report)

        self.assertIn("asset_roles", report)
        self.assertIn("strategies", report)
        self.assertEqual(len(report["strategies"]), 3)
        self.assertIn("best_strategy_by_return", report["rankings"])
        self.assertIn("structure_healthy", report["conclusion"])
        self.assertIn("asset_weights", report["strategies"][0])
        self.assertIn("cash_allocation", report["strategies"][0])

    def test_storage_saves_portfolio_strategy_report(self):
        report = run_portfolio_strategy_synth(self.portfolio_report, self.dca_report)
        with TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))

            storage.save_portfolio_strategy_report(report)
            saved = json.loads((Path(temp_dir) / "data" / "portfolio_strategy_report.json").read_text(encoding="utf-8"))

            self.assertEqual(storage.load_portfolio_strategy_report(), saved)


if __name__ == "__main__":
    unittest.main()
