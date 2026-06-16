import unittest

from drawdownguard.asset_dca_audit import find_portfolio_asset, run_asset_dca_audit, summarize_asset_dca_audit


class FakeDataFrame:
    def __init__(self, records):
        self.records = records

    def to_dict(self, orient):
        return self.records


class FakeAkShare:
    def fund_open_fund_info_em(self, symbol, indicator):
        if indicator == "累计净值走势":
            return FakeDataFrame(
                [
                    {"净值日期": "2026-01-05", "累计净值": 1.0},
                    {"净值日期": "2026-03-30", "累计净值": 1.8},
                ]
            )
        if indicator == "累计收益率走势":
            return FakeDataFrame(
                [
                    {"净值日期": "2026-01-05", "累计收益率": 0},
                    {"净值日期": "2026-03-30", "累计收益率": 80},
                ]
            )
        return FakeDataFrame([])


class FakeProvider:
    def __init__(self, history):
        self.history = history
        self.akshare_client = FakeAkShare()

    def get_full_history(self, fund_code):
        return {"history": self.history, "source": "local", "warnings": []}


class AssetDcaAuditTest(unittest.TestCase):
    def setUp(self):
        self.config = {
            "funds": [{"code": "008163", "name": "南方红利低波50ETF联接A"}],
            "portfolio_backtest": {
                "start_date": "2026-01-05",
                "assets": [
                    {
                        "asset_id": "DIVIDEND_LOW_VOL",
                        "asset_name": "红利低波",
                        "representative_fund": "008163",
                        "strategy": "dca_only",
                        "weekly_dca_amount": 100,
                    }
                ],
            },
        }
        self.history = [
            {"date": "2026-01-05", "nav": 1.0},
            {"date": "2026-01-12", "nav": 2.0},
            {"date": "2026-01-19", "nav": 1.0},
            {"date": "2026-01-26", "nav": 2.0},
            {"date": "2026-02-02", "nav": 1.0},
            {"date": "2026-02-09", "nav": 2.0},
            {"date": "2026-02-16", "nav": 1.0},
            {"date": "2026-02-23", "nav": 2.0},
            {"date": "2026-03-02", "nav": 1.0},
            {"date": "2026-03-09", "nav": 2.0},
            {"date": "2026-03-16", "nav": 1.0},
            {"date": "2026-03-23", "nav": 2.0},
            {"date": "2026-03-30", "nav": 1.0},
        ]

    def test_asset_id_and_fund_code_lookup(self):
        portfolio_config = self.config["portfolio_backtest"]

        self.assertEqual(find_portfolio_asset(portfolio_config, "DIVIDEND_LOW_VOL")["representative_fund"], "008163")
        self.assertEqual(find_portfolio_asset(portfolio_config, "008163")["asset_id"], "DIVIDEND_LOW_VOL")

    def test_average_cost_and_dca_return(self):
        report = run_asset_dca_audit(self.config, FakeProvider(self.history), "DIVIDEND_LOW_VOL")
        dca = report["dca_audit"]

        self.assertEqual(dca["buy_count"], 13)
        self.assertEqual(dca["total_invested"], 1300)
        expected_shares = 7 * 100 / 1.0 + 6 * 100 / 2.0
        self.assertAlmostEqual(dca["total_shares"], expected_shares)
        self.assertAlmostEqual(dca["average_cost"], 1300 / expected_shares)
        self.assertAlmostEqual(dca["final_market_value"], expected_shares * 1.0)
        self.assertAlmostEqual(dca["total_return_rate"], (expected_shares - 1300) / 1300)

    def test_buy_record_samples_first_and_last_10(self):
        report = run_asset_dca_audit(self.config, FakeProvider(self.history), "008163")
        samples = report["buy_record_samples"]

        self.assertEqual(len(samples["first_10"]), 10)
        self.assertEqual(len(samples["last_10"]), 10)
        self.assertEqual(samples["first_10"][0]["date"], "2026-01-05")
        self.assertEqual(samples["last_10"][-1]["date"], "2026-03-30")
        self.assertIn("cumulative_invested", samples["first_10"][0])
        self.assertIn("average_cost_after_buy", samples["first_10"][0])

    def test_warning_logic_for_nav_profile_and_high_buys(self):
        report = run_asset_dca_audit(self.config, FakeProvider(self.history), "DIVIDEND_LOW_VOL")

        self.assertTrue(any("单位净值回测可能低估收益" in warning for warning in report["warnings"]))
        self.assertTrue(any("支付宝显示" in warning for warning in report["warnings"]))
        self.assertGreater(report["high_buy_diagnosis"]["buys_above_final_nav_percent"], 0.4)

    def test_insufficient_data_does_not_crash(self):
        report = run_asset_dca_audit(self.config, FakeProvider([]), "DIVIDEND_LOW_VOL")

        self.assertEqual(report["dca_audit"]["buy_count"], 0)
        self.assertEqual(report["buy_record_samples"]["first_10"], [])
        self.assertTrue(report["warnings"])

    def test_falls_back_to_portfolio_report_series_when_provider_has_no_history(self):
        portfolio_report = {
            "portfolio_summary": {
                "requested_start_date": "2026-01-05",
                "requested_end_date": None,
                "end_date": "2026-01-19",
            },
            "assets": [
                {
                    "asset_id": "DIVIDEND_LOW_VOL",
                    "representative_fund": "008163",
                    "total_invested": 300,
                    "final_market_value": 300,
                    "total_profit": 0,
                    "total_return_rate": 0,
                    "events": [],
                    "series": [
                        {"date": "2026-01-05", "nav": 1.0},
                        {"date": "2026-01-12", "nav": 1.0},
                        {"date": "2026-01-19", "nav": 1.0},
                    ],
                }
            ],
        }

        report = run_asset_dca_audit(
            self.config,
            FakeProvider([]),
            "DIVIDEND_LOW_VOL",
            portfolio_report=portfolio_report,
        )

        self.assertEqual(report["total_nav_records"], 3)
        self.assertEqual(report["dca_audit"]["buy_count"], 3)
        self.assertTrue(any("portfolio_backtest_report.json" in warning for warning in report["warnings"]))

    def test_summarize_asset_dca_audit(self):
        report = run_asset_dca_audit(self.config, FakeProvider(self.history), "DIVIDEND_LOW_VOL")

        summary = summarize_asset_dca_audit(report)

        self.assertIn("资产定投审计报告", summary)
        self.assertIn("净值口径检查", summary)
        self.assertIn("定投记录抽样：前 10 笔", summary)
        self.assertIn("成立来业绩走势代表一次性持有收益", summary)


if __name__ == "__main__":
    unittest.main()
