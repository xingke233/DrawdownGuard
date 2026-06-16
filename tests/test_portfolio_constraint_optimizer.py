import unittest

from drawdownguard.portfolio_constraint_optimizer import (
    check_constraints,
    generate_weight_candidates,
    normalize_weights,
    run_portfolio_constraint_optimizer,
    score_portfolio,
)


class PortfolioConstraintOptimizerTest(unittest.TestCase):
    def setUp(self):
        self.portfolio_report = {
            "assets": [
                {
                    "asset_id": "NASDAQ100",
                    "total_return_rate": 0.5,
                    "series": [{"nav": 1.0}, {"nav": 1.5}, {"nav": 1.2}],
                },
                {
                    "asset_id": "GOLD",
                    "total_return_rate": 0.2,
                    "series": [{"nav": 1.0}, {"nav": 1.1}, {"nav": 1.05}],
                },
                {
                    "asset_id": "HSTECH",
                    "total_return_rate": -0.1,
                    "series": [{"nav": 1.0}, {"nav": 0.8}, {"nav": 0.9}],
                },
                {
                    "asset_id": "CASHFLOW",
                    "total_return_rate": 0.05,
                    "series": [{"nav": 1.0}, {"nav": 1.02}, {"nav": 1.01}],
                },
                {
                    "asset_id": "DIVIDEND_LOW_VOL",
                    "total_return_rate": 0.1,
                    "series": [{"nav": 1.0}, {"nav": 0.95}, {"nav": 1.03}],
                },
            ]
        }
        self.dca_report = {
            "assets": [
                {
                    "asset_id": "NASDAQ100",
                    "best_strategy": {"total_return_rate": 0.6, "max_drawdown": -0.2, "volatility": 0.04},
                },
                {
                    "asset_id": "GOLD",
                    "best_strategy": {"total_return_rate": 0.3, "max_drawdown": -0.1, "volatility": 0.02},
                },
                {
                    "asset_id": "HSTECH",
                    "best_strategy": {"total_return_rate": -0.05, "max_drawdown": -0.3, "volatility": 0.05},
                },
                {
                    "asset_id": "CASHFLOW",
                    "best_strategy": {"total_return_rate": 0.08, "max_drawdown": -0.05, "volatility": 0.01},
                },
                {
                    "asset_id": "DIVIDEND_LOW_VOL",
                    "best_strategy": {"total_return_rate": 0.12, "max_drawdown": -0.08, "volatility": 0.015},
                },
            ]
        }

    def test_weight_normalization(self):
        weights = normalize_weights({"A": 2, "B": 1})

        self.assertAlmostEqual(sum(weights.values()), 1)
        self.assertAlmostEqual(weights["A"], 2 / 3)

    def test_constraints_satisfied_and_violated(self):
        good = {
            "NASDAQ100": 0.55,
            "HSTECH": 0.05,
            "GOLD": 0.20,
            "CASHFLOW": 0.10,
            "DIVIDEND_LOW_VOL": 0.10,
        }
        bad = {**good, "NASDAQ100": 0.80}

        self.assertTrue(check_constraints(good, 0.20)["all_satisfied"])
        self.assertFalse(check_constraints(bad, 0.30)["all_satisfied"])

    def test_score_function(self):
        self.assertAlmostEqual(score_portfolio(0.2, 0.1, 2.0), 0.5 * 0.2 - 0.3 * 0.1 + 0.2 * 2.0)

    def test_quick_candidates_exist(self):
        candidates = generate_weight_candidates("quick", ["NASDAQ100", "GOLD"])

        self.assertTrue(candidates)
        self.assertTrue(all(abs(sum(candidate.values()) - 1) < 1e-9 for candidate in candidates))

    def test_three_modes_output_consistency(self):
        report = run_portfolio_constraint_optimizer(
            self.portfolio_report,
            self.dca_report,
            preset="quick",
            workers=1,
        )

        self.assertIn("max_return_mode", report["modes"])
        self.assertIn("min_risk_mode", report["modes"])
        self.assertIn("balanced_mode", report["modes"])
        self.assertIn("best_portfolio", report["recommendations"])
        self.assertIn("binding_constraints", report)
        self.assertGreater(report["tested_count"], 0)


if __name__ == "__main__":
    unittest.main()
