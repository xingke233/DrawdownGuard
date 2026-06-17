import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from drawdownguard.committee_report import build_committee_report
from drawdownguard.quant_signal import (
    build_asset_signal,
    calculate_quant_metrics,
    max_drawdown,
    moving_average,
    run_quant_signal,
    signal_status,
    trend_score,
    volatility,
)
from drawdownguard.storage import Storage


class QuantSignalTest(unittest.TestCase):
    def test_moving_averages_are_calculated(self):
        history = _history([float(index) for index in range(1, 131)])

        self.assertEqual(moving_average(history, 20), sum(range(111, 131)) / 20)
        self.assertEqual(moving_average(history, 60), sum(range(71, 131)) / 60)
        self.assertEqual(moving_average(history, 120), sum(range(11, 131)) / 120)

    def test_drawdown_from_250d_high_is_calculated(self):
        history = _history([1, 2, 3, 2.4])

        metrics = calculate_quant_metrics(history)

        self.assertEqual(metrics["high_250d"], 3)
        self.assertAlmostEqual(metrics["drawdown_from_250d_high"], -0.2)

    def test_volatility_is_calculated(self):
        history = _history([100, 110, 99, 108.9])

        self.assertAlmostEqual(volatility(history, 3), 0.094280904, places=6)

    def test_trend_score_prefers_ordered_uptrend(self):
        history = _history([float(index) for index in range(1, 181)])
        metrics = calculate_quant_metrics(history)

        self.assertEqual(trend_score(metrics), 90)

    def test_quant_score_range_and_status(self):
        history = _history([float(index) for index in range(1, 181)])

        report = build_asset_signal("NASDAQ100", "纳斯达克100", "270042", "unit_nav", history)

        self.assertGreaterEqual(report["quant_score"], 0)
        self.assertLessEqual(report["quant_score"], 100)
        self.assertIn(report["signal_status"], {"strong_uptrend", "healthy", "neutral", "weak", "high_risk"})
        self.assertEqual(signal_status(80), "strong_uptrend")
        self.assertEqual(signal_status(60), "healthy")
        self.assertEqual(signal_status(40), "neutral")
        self.assertEqual(signal_status(20), "weak")
        self.assertEqual(signal_status(19.99), "high_risk")

    def test_insufficient_data_does_not_crash(self):
        report = build_asset_signal("CASHFLOW", "自由现金流", "023918", "unit_nav", _history([1, 1.1]))

        self.assertEqual(report["status"], "available")
        self.assertIn("净值数据不足120条", " ".join(report["warnings"]))

    def test_dividend_low_vol_uses_accumulated_nav(self):
        provider = FakeProvider(_history([1 + index * 0.01 for index in range(260)]))

        report = run_quant_signal(_config(), provider)

        self.assertIn(("008163", "accumulated_nav"), provider.calls)
        asset = _asset(report, "DIVIDEND_LOW_VOL")
        self.assertEqual(asset["nav_mode"], "accumulated_nav")

    def test_quant_signal_report_json_is_saved(self):
        provider = FakeProvider(_history([1 + index * 0.01 for index in range(260)]))
        report = run_quant_signal(_config(), provider)

        with TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))
            storage.save_quant_signal_report(report)
            saved = json.loads((Path(temp_dir) / "data" / "quant_signal_report.json").read_text(encoding="utf-8"))
            loaded = storage.load_quant_signal_report()

        self.assertIn("portfolio_quant_summary", saved)
        self.assertEqual(loaded, saved)

    def test_committee_report_reads_quant_signal(self):
        provider = FakeProvider(_history([1 + index * 0.01 for index in range(260)]))
        quant_report = run_quant_signal(_config(), provider)

        committee = build_committee_report(_config(), quant_signal_report=quant_report)

        self.assertIn("量化信号", committee["markdown"])
        self.assertIn("市场环境", committee["markdown"])
        self.assertEqual(committee["sections"]["quant_signal"]["status"], "available")

    def test_max_drawdown(self):
        self.assertAlmostEqual(max_drawdown(_history([1, 1.5, 1.2, 1.8])), -0.2)


class FakeProvider:
    def __init__(self, history):
        self.history = history
        self.calls = []

    def get_full_history(self, fund_code, nav_mode="unit_nav"):
        self.calls.append((fund_code, nav_mode))
        return {
            "history": self.history,
            "source": "local",
            "warnings": [],
            "nav_mode": nav_mode,
        }


def _history(values):
    return [
        {"date": f"2026-{index + 1:04d}", "nav": value}
        for index, value in enumerate(values)
    ]


def _asset(report, asset_id):
    return next(asset for asset in report["assets"] if asset.get("asset_id") == asset_id)


def _config():
    return {
        "funds": [],
        "bullet_account": {"name": "余额宝", "balance": 1883},
        "holdings": [
            {"asset_id": "NASDAQ100", "asset_name": "纳斯达克100", "amount": 2181, "weight": 0.2035},
            {"asset_id": "HSTECH", "asset_name": "恒生科技", "amount": 290, "weight": 0.0271},
            {"asset_id": "CASHFLOW", "asset_name": "自由现金流", "amount": 574, "weight": 0.0536},
            {"asset_id": "DIVIDEND_LOW_VOL", "asset_name": "红利低波", "amount": 419, "weight": 0.0390, "nav_mode": "accumulated_nav"},
            {"asset_id": "GOLD", "asset_name": "黄金", "amount": 763, "weight": 0.0712},
            {"asset_id": "BONDS", "asset_name": "债券", "amount": 3963, "weight": 0.3696},
        ],
        "portfolio_backtest": {
            "assets": [
                {"asset_id": "NASDAQ100", "asset_name": "纳斯达克100", "representative_fund": "270042", "nav_mode": "unit_nav"},
                {"asset_id": "HSTECH", "asset_name": "恒生科技", "representative_fund": "012349", "nav_mode": "unit_nav"},
                {"asset_id": "CASHFLOW", "asset_name": "自由现金流", "representative_fund": "023918", "nav_mode": "unit_nav"},
                {"asset_id": "DIVIDEND_LOW_VOL", "asset_name": "红利低波", "representative_fund": "008163", "nav_mode": "accumulated_nav"},
                {"asset_id": "GOLD", "asset_name": "黄金", "representative_fund": "000216", "nav_mode": "unit_nav"},
            ]
        },
    }
