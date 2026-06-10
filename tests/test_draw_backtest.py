import json
import tempfile
import unittest
from pathlib import Path

from draw_backtest import build_plot_title, plot_report_file


class DrawBacktestTest(unittest.TestCase):
    def setUp(self):
        self.fund_report = {
            "fund_code": "demo",
            "fund_name": "演示基金",
            "start_date": "2026-01-01",
            "end_date": "2026-01-03",
            "initial_cash": 2000,
            "final_cash": 1700,
            "total_invested": 300,
            "trigger_count_total": 1,
            "trigger_count_by_level": {"10": 1, "15": 0, "20": 0},
            "max_drawdown_seen": -0.12,
            "series": [
                {"date": "2026-01-01", "nav": 1.0, "peak_nav": 1.0, "drawdown": 0, "cash_after": 2000},
                {"date": "2026-01-02", "nav": 0.88, "peak_nav": 1.0, "drawdown": -0.12, "cash_after": 1700},
                {"date": "2026-01-03", "nav": 0.9, "peak_nav": 1.0, "drawdown": -0.1, "cash_after": 1700},
            ],
            "events": [
                {
                    "date": "2026-01-02",
                    "nav": 0.88,
                    "peak_nav": 1.0,
                    "drawdown": -0.12,
                    "level": "10",
                    "amount": 300,
                    "cash_after": 1700,
                }
            ],
        }

    def test_backtest_report_generates_plot(self):
        report = {
            "backtest": {"initial_cash": 2000, "monthly_cash_addition": 0},
            "fund_reports": [self.fund_report],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "backtest_report.json"
            output_dir = Path(temp_dir) / "plots"
            report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

            plots = plot_report_file(report_path, output_dir)

            self.assertEqual(len(plots), 1)
            self.assertEqual(plots[0]["scenario_id"], "backtest")
            self.assertIn("demo 演示基金 | backtest | Initial Cash 2000 | Monthly Add 0", plots[0]["title"])
            self.assertTrue(Path(plots[0]["path"]).exists())
            self.assertGreater(Path(plots[0]["path"]).stat().st_size, 0)

    def test_scenarios_report_generates_selected_scenario_plot(self):
        report = {
            "scenarios": [
                {
                    "scenario_id": "S001",
                    "initial_cash": 2000,
                    "monthly_cash_addition": 0,
                    "funds": [self.fund_report],
                },
                {
                    "scenario_id": "S002",
                    "initial_cash": 3000,
                    "monthly_cash_addition": 200,
                    "funds": [self.fund_report],
                },
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "scenarios_report.json"
            output_dir = Path(temp_dir) / "plots"
            report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

            plots = plot_report_file(report_path, output_dir, scenario_id="S002")

            self.assertEqual(len(plots), 1)
            self.assertEqual(plots[0]["scenario_id"], "S002")
            self.assertIn("demo 演示基金 | S002 | Initial Cash 3000 | Monthly Add 200", plots[0]["title"])
            self.assertTrue((output_dir / "S002").is_dir())
            self.assertTrue(Path(plots[0]["path"]).name.endswith("_S002.png"))
            self.assertTrue(Path(plots[0]["path"]).exists())

    def test_build_plot_title_contains_required_context(self):
        scenario = {"scenario_id": "S003", "initial_cash": 5000, "monthly_cash_addition": 500}

        title = build_plot_title(self.fund_report, scenario)

        self.assertEqual(title, "demo 演示基金 | S003 | Initial Cash 5000 | Monthly Add 500")


if __name__ == "__main__":
    unittest.main()
