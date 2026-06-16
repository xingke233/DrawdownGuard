import unittest

from drawdownguard.portfolio_continuous_optimizer import (
    differential_evolution_optimize,
    project_weights,
    run_portfolio_continuous_optimizer,
)
from drawdownguard.portfolio_constraint_optimizer import ASSET_LIMITS


class PortfolioContinuousOptimizerTest(unittest.TestCase):
    def setUp(self):
        self.portfolio_report = {
            "assets": [
                {"asset_id": "NASDAQ100", "total_return_rate": 0.5, "series": [{"nav": 1.0}, {"nav": 1.3}]},
                {"asset_id": "HSTECH", "total_return_rate": -0.1, "series": [{"nav": 1.0}, {"nav": 0.8}]},
                {"asset_id": "CASHFLOW", "total_return_rate": 0.08, "series": [{"nav": 1.0}, {"nav": 1.02}]},
                {"asset_id": "DIVIDEND_LOW_VOL", "total_return_rate": 0.12, "series": [{"nav": 1.0}, {"nav": 1.05}]},
                {"asset_id": "GOLD", "total_return_rate": 0.3, "series": [{"nav": 1.0}, {"nav": 1.2}]},
            ]
        }
        self.dca_report = {
            "assets": [
                {"asset_id": "NASDAQ100", "best_strategy": {"total_return_rate": 0.6, "max_drawdown": -0.20, "volatility": 0.04}},
                {"asset_id": "HSTECH", "best_strategy": {"total_return_rate": -0.05, "max_drawdown": -0.30, "volatility": 0.05}},
                {"asset_id": "CASHFLOW", "best_strategy": {"total_return_rate": 0.08, "max_drawdown": -0.05, "volatility": 0.01}},
                {"asset_id": "DIVIDEND_LOW_VOL", "best_strategy": {"total_return_rate": 0.12, "max_drawdown": -0.08, "volatility": 0.015}},
                {"asset_id": "GOLD", "best_strategy": {"total_return_rate": 0.3, "max_drawdown": -0.10, "volatility": 0.02}},
            ]
        }
        self.discrete_report = {
            "recommendations": {
                "best_portfolio": {
                    "candidate_id": "discrete",
                    "return": 0.3,
                }
            }
        }

    def test_project_weights_sum_to_one_and_respect_bounds(self):
        weights = project_weights({"NASDAQ100": 10, "GOLD": 10, "HSTECH": 1}, ["NASDAQ100", "GOLD", "HSTECH"])

        self.assertAlmostEqual(sum(weights.values()), 1)
        for asset_id, weight in weights.items():
            self.assertLessEqual(weight, ASSET_LIMITS[asset_id] + 1e-9)

    def test_optimizer_satisfies_constraints(self):
        report = run_portfolio_continuous_optimizer(
            self.portfolio_report,
            self.dca_report,
            self.discrete_report,
            preset="quick",
            seed=7,
        )

        self.assertAlmostEqual(sum(report["asset_weights"].values()), 1)
        self.assertTrue(report["constraints"]["all_satisfied"])
        self.assertLessEqual(report["risk_metrics"]["max_drawdown"], 0.25)

    def test_optimization_converges_to_result(self):
        assets = {
            "NASDAQ100": {"return": 0.6, "drawdown": 0.2, "volatility": 0.04},
            "GOLD": {"return": 0.3, "drawdown": 0.1, "volatility": 0.02},
            "CASHFLOW": {"return": 0.08, "drawdown": 0.05, "volatility": 0.01},
        }

        result = differential_evolution_optimize(
            assets,
            ["NASDAQ100", "GOLD", "CASHFLOW"],
            iterations=5,
            population_size=10,
            seed=1,
        )

        self.assertIn("asset_weights", result)
        self.assertIn("optimization_score", result)

    def test_output_is_stable_with_fixed_seed(self):
        first = run_portfolio_continuous_optimizer(self.portfolio_report, self.dca_report, self.discrete_report, seed=42)
        second = run_portfolio_continuous_optimizer(self.portfolio_report, self.dca_report, self.discrete_report, seed=42)

        self.assertEqual(first["asset_weights"], second["asset_weights"])
        self.assertEqual(first["risk_metrics"], second["risk_metrics"])


if __name__ == "__main__":
    unittest.main()
