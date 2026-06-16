import json
import tempfile
import unittest
from pathlib import Path

from drawdownguard.backtest import (
    AssetBacktester,
    PortfolioBacktester,
    StrategyBacktester,
    run_backtest_scenarios,
    summarize_asset_backtest_report,
    summarize_backtest_report,
    summarize_backtest_returns,
    summarize_portfolio_backtest_report,
    summarize_scenarios_report,
    summarize_scenarios_returns,
)
from drawdownguard.storage import Storage
from drawdownguard.strategy_lab import run_strategy_lab, summarize_strategy_lab_report
from drawdownguard.weekly_dca_analysis import run_weekly_dca_analysis, summarize_weekly_dca_analysis
from main import collect_portfolio_histories


class RecordingPortfolioProvider:
    def __init__(self):
        self.calls = []

    def get_full_history(self, fund_code, nav_mode="unit_nav"):
        self.calls.append((fund_code, nav_mode))
        nav = 2.0 if nav_mode == "accumulated_nav" else 1.0
        return {
            "history": [{"date": "2026-01-05", "nav": nav}],
            "warnings": [],
            "nav_mode": nav_mode,
        }


class BacktestTest(unittest.TestCase):
    def setUp(self):
        self.config = {
            "peak_window_trading_days": 250,
            "round_amount_to": 10,
            "bullet_account": {"name": "余额宝", "balance": 9999},
            "backtest": {
                "enabled": True,
                "start_date": "2026-01-01",
                "initial_cash": 2000,
                "monthly_cash_addition": 0,
                "include_regular_dca": False,
                "funds": ["demo"],
            },
            "replenishment_levels": [
                {"drawdown_percent": 10, "cash_ratio": 0.15},
                {"drawdown_percent": 15, "cash_ratio": 0.25},
                {"drawdown_percent": 20, "cash_ratio": 0.35},
            ],
        }
        self.fund = {"code": "demo", "name": "演示基金"}

    def test_portfolio_dca_uses_next_trading_day_when_monday_missing(self):
        config = {
            **self.config,
            "portfolio_backtest": {
                "enabled": True,
                "start_date": "2023-01-01",
                "bullet_cash_initial": 2000,
                "bullet_cash_monthly_addition": 0,
                "assets": [
                    {
                        "asset_id": "NASDAQ100",
                        "asset_name": "纳斯达克100",
                        "representative_fund": "270042",
                        "strategy": "dca_only",
                        "weekly_dca_amount": 10,
                    }
                ],
            },
        }
        histories = {
            "270042": [
                {"date": "2023-01-03", "nav": 1.0},
                {"date": "2023-01-09", "nav": 2.0},
            ]
        }

        report = PortfolioBacktester(config).run(histories)
        asset = report["assets"][0]

        self.assertEqual([event["date"] for event in asset["events"]], ["2023-01-03", "2023-01-09"])
        self.assertEqual(asset["dca_invested"], 20)
        self.assertAlmostEqual(asset["total_shares"], 10 / 1.0 + 10 / 2.0)
        self.assertAlmostEqual(asset["final_market_value"], 30)

    def test_portfolio_backtest_supports_custom_time_ranges(self):
        base_config = {
            **self.config,
            "portfolio_backtest": {
                "enabled": True,
                "start_date": "2018-01-01",
                "bullet_cash_initial": 2000,
                "bullet_cash_monthly_addition": 0,
                "assets": [
                    {
                        "asset_id": "CASHFLOW",
                        "asset_name": "自由现金流",
                        "representative_fund": "023918",
                        "strategy": "dca_only",
                        "weekly_dca_amount": 10,
                    }
                ],
            },
        }
        histories = {
            "023918": [
                {"date": "2020-01-06", "nav": 1.0},
                {"date": "2020-01-13", "nav": 1.1},
                {"date": "2022-01-03", "nav": 1.2},
                {"date": "2022-01-10", "nav": 1.3},
                {"date": "2022-01-17", "nav": 1.4},
            ]
        }

        cases = [
            ("2018-01-01", None, "2020-01-06", "2022-01-17", 50),
            ("2020-01-01", "2020-12-31", "2020-01-06", "2020-01-13", 20),
            ("2022-01-01", "2022-01-10", "2022-01-03", "2022-01-10", 20),
        ]

        for start_date, end_date, actual_start, actual_end, dca_invested in cases:
            with self.subTest(start_date=start_date, end_date=end_date):
                config = {
                    **base_config,
                    "portfolio_backtest": {
                        **base_config["portfolio_backtest"],
                        "start_date": start_date,
                    },
                }
                if end_date:
                    config["portfolio_backtest"]["end_date"] = end_date

                report = PortfolioBacktester(config).run(histories)
                asset = report["assets"][0]

                self.assertEqual(report["portfolio_summary"]["start_date"], actual_start)
                self.assertEqual(report["portfolio_summary"]["end_date"], actual_end)
                self.assertEqual(asset["start_date"], actual_start)
                self.assertEqual(asset["end_date"], actual_end)
                self.assertEqual(asset["dca_invested"], dca_invested)

    def test_weekly_dca_analysis_outputs_all_weekdays(self):
        config = {
            **self.config,
            "portfolio_backtest": {
                "enabled": True,
                "start_date": "2026-01-05",
                "bullet_cash_initial": 2000,
                "bullet_cash_monthly_addition": 0,
                "assets": [
                    {
                        "asset_id": "HSTECH",
                        "asset_name": "恒生科技",
                        "representative_fund": "012349",
                        "strategy": "dca_only",
                        "weekly_dca_amount": 10,
                    }
                ],
            },
        }
        histories = {
            "012349": [
                {"date": "2026-01-05", "nav": 1.0},
                {"date": "2026-01-06", "nav": 1.25},
                {"date": "2026-01-07", "nav": 1.5},
                {"date": "2026-01-08", "nav": 1.75},
                {"date": "2026-01-09", "nav": 2.0},
            ]
        }

        report = run_weekly_dca_analysis(config, histories, source="backtest")

        self.assertEqual(len(report["results"]), 5)
        self.assertEqual([item["weekday_label"] for item in report["results"]], ["周一", "周二", "周三", "周四", "周五"])
        monday = report["results"][0]
        self.assertEqual(monday["total_invested"], 10)
        self.assertEqual(monday["final_market_value"], 20)
        self.assertEqual(monday["total_profit"], 10)
        self.assertEqual(monday["total_return_rate"], 1)

    def test_weekly_dca_analysis_keeps_nasdaq_drawdown_triggers(self):
        config = {
            **self.config,
            "portfolio_backtest": {
                "enabled": True,
                "start_date": "2026-01-05",
                "bullet_cash_initial": 2000,
                "bullet_cash_monthly_addition": 0,
                "assets": [
                    {
                        "asset_id": "NASDAQ100",
                        "asset_name": "纳斯达克100",
                        "representative_fund": "270042",
                        "strategy": "drawdown_plus_dca",
                        "weekly_dca_amount": 10,
                        "drawdown_levels": [
                            {"level": 10, "cash_ratio": 0.15},
                            {"level": 15, "cash_ratio": 0.25},
                            {"level": 20, "cash_ratio": 0.35},
                        ],
                    },
                    {
                        "asset_id": "HSTECH",
                        "asset_name": "恒生科技",
                        "representative_fund": "012349",
                        "strategy": "dca_only",
                        "weekly_dca_amount": 10,
                    },
                ],
            },
        }
        histories = {
            "270042": [
                {"date": "2026-01-05", "nav": 1.0},
                {"date": "2026-01-06", "nav": 0.74},
                {"date": "2026-01-07", "nav": 0.75},
                {"date": "2026-01-08", "nav": 0.76},
                {"date": "2026-01-09", "nav": 0.77},
            ]
        }

        report = run_weekly_dca_analysis(config, histories)

        self.assertTrue(all(item["trigger_count_total"] == 3 for item in report["results"]))
        self.assertTrue(all(item["bullet_cash_final"] == 820 for item in report["results"]))

    def test_summarize_weekly_dca_analysis(self):
        report = {
            "results": [
                {
                    "weekday_label": "周一",
                    "total_invested": 10,
                    "final_market_value": 12,
                    "total_profit": 2,
                    "total_return_rate": 0.2,
                    "bullet_cash_final": 2000,
                    "trigger_count_total": 0,
                }
            ]
        }

        summary = summarize_weekly_dca_analysis(report)

        self.assertIn("定投周几回测分析", summary)
        self.assertIn("周一 | 投入 10.00 元", summary)
        self.assertIn("收益率最高：周一 20.00%", summary)

    def test_strategy_lab_outputs_default_strategies_and_rankings(self):
        config = {
            **self.config,
            "portfolio_backtest": {
                "enabled": True,
                "start_date": "2026-01-05",
                "bullet_cash_initial": 2000,
                "bullet_cash_monthly_addition": 0,
                "assets": [
                    {
                        "asset_id": "NASDAQ100",
                        "asset_name": "纳斯达克100",
                        "representative_fund": "270042",
                        "strategy": "drawdown_plus_dca",
                        "weekly_dca_amount": 10,
                        "drawdown_levels": [
                            {"level": 10, "cash_ratio": 0.15},
                            {"level": 15, "cash_ratio": 0.25},
                            {"level": 20, "cash_ratio": 0.35},
                        ],
                    }
                ],
            },
        }
        histories = {
            "270042": [
                {"date": "2026-01-05", "nav": 1.0},
                {"date": "2026-01-06", "nav": 0.74},
                {"date": "2026-01-07", "nav": 1.1},
            ],
            "012349": [
                {"date": "2026-01-05", "nav": 1.0},
                {"date": "2026-01-06", "nav": 0.5},
                {"date": "2026-01-07", "nav": 1.0},
            ],
        }

        report = run_strategy_lab(config, histories)

        self.assertEqual(
            [item["strategy_name"] for item in report["strategies"]],
            ["A_current", "B_conservative", "C_aggressive", "D_balanced"],
        )
        self.assertEqual([item["level"] for item in report["strategies"][0]["drawdown_levels"]], [10, 15, 20])
        self.assertEqual([item["level"] for item in report["strategies"][1]["drawdown_levels"]], [10, 20, 30])
        self.assertEqual(report["strategies"][0]["trigger_count_total"], 3)
        self.assertEqual(report["strategies"][1]["trigger_count_total"], 2)
        self.assertEqual(report["strategies"][0]["bullet_cash_final"], 820)
        self.assertIn("nasdaq100_return_rate", report["strategies"][0])
        self.assertIn("return_rate", report["rankings"])
        self.assertIn("bullet_cash_final", report["rankings"])
        self.assertIn("trigger_count", report["rankings"])
        self.assertEqual(report["rankings"]["recommended_strategy"], report["rankings"]["return_rate"][0])

    def test_summarize_strategy_lab_report(self):
        report = {
            "strategies": [
                {
                    "strategy_name": "A_current",
                    "drawdown_levels": [
                        {"level": 10, "cash_ratio": 0.15},
                        {"level": 15, "cash_ratio": 0.25},
                        {"level": 20, "cash_ratio": 0.35},
                    ],
                    "total_invested": 1000,
                    "total_return_rate": 0.1,
                    "total_profit": 100,
                    "final_market_value": 1100,
                    "trigger_count_total": 3,
                    "bullet_cash_final": 820,
                    "nasdaq100_return_rate": 0.2,
                }
            ],
            "rankings": {
                "return_rate": ["A_current"],
                "bullet_cash_final": ["A_current"],
                "trigger_count": ["A_current"],
                "recommended_strategy": "A_current",
            },
        }

        summary = summarize_strategy_lab_report(report)

        self.assertIn("Strategy Lab 回测摘要", summary)
        self.assertIn("收益率排名：A_current", summary)
        self.assertIn("子弹仓剩余排名：A_current", summary)
        self.assertIn("触发次数排名：A_current", summary)
        self.assertIn("推荐策略：A_current", summary)

    def test_portfolio_nasdaq_can_dca_and_drawdown_buy(self):
        config = {
            **self.config,
            "portfolio_backtest": {
                "enabled": True,
                "start_date": "2026-01-05",
                "bullet_cash_initial": 2000,
                "bullet_cash_monthly_addition": 0,
                "assets": [
                    {
                        "asset_id": "NASDAQ100",
                        "asset_name": "纳斯达克100",
                        "representative_fund": "270042",
                        "strategy": "drawdown_plus_dca",
                        "weekly_dca_amount": 50,
                        "drawdown_levels": [
                            {"level": 10, "cash_ratio": 0.15},
                            {"level": 15, "cash_ratio": 0.25},
                            {"level": 20, "cash_ratio": 0.35},
                        ],
                    }
                ],
            },
        }
        histories = {
            "270042": [
                {"date": "2026-01-05", "nav": 1.0},
                {"date": "2026-01-12", "nav": 0.74},
            ]
        }

        report = PortfolioBacktester(config).run(histories)
        asset = report["assets"][0]

        self.assertEqual(asset["dca_invested"], 100)
        self.assertEqual(asset["bullet_invested"], 1180)
        self.assertEqual(asset["trigger_count_total"], 3)
        self.assertEqual(asset["trigger_count_by_level"], {"10": 1, "15": 1, "20": 1})
        self.assertEqual(report["portfolio_summary"]["total_dca_invested"], 100)
        self.assertEqual(report["portfolio_summary"]["total_bullet_invested"], 1180)
        self.assertEqual(report["portfolio_summary"]["bullet_cash_final"], 820)
        self.assertEqual([event["type"] for event in asset["events"]], ["dca", "dca", "drawdown_buy", "drawdown_buy", "drawdown_buy"])

    def test_portfolio_hstech_dca_only_does_not_trigger_drawdown_buy(self):
        config = {
            **self.config,
            "portfolio_backtest": {
                "enabled": True,
                "start_date": "2026-01-05",
                "bullet_cash_initial": 2000,
                "bullet_cash_monthly_addition": 0,
                "assets": [
                    {
                        "asset_id": "HSTECH",
                        "asset_name": "恒生科技",
                        "representative_fund": "012349",
                        "strategy": "dca_only",
                        "weekly_dca_amount": 20,
                    }
                ],
            },
        }
        histories = {
            "012349": [
                {"date": "2026-01-05", "nav": 1.0},
                {"date": "2026-01-12", "nav": 0.7},
            ]
        }

        asset = PortfolioBacktester(config).run(histories)["assets"][0]

        self.assertEqual(asset["dca_invested"], 40)
        self.assertEqual(asset["bullet_invested"], 0)
        self.assertEqual(asset["trigger_count_total"], 0)
        self.assertTrue(all(event["type"] == "dca" for event in asset["events"]))

    def test_portfolio_placeholder_asset_is_skipped(self):
        config = {
            **self.config,
            "portfolio_backtest": {
                "enabled": True,
                "start_date": "2026-01-05",
                "bullet_cash_initial": 2000,
                "bullet_cash_monthly_addition": 0,
                "assets": [
                    {
                        "asset_id": "GOLD",
                        "asset_name": "黄金",
                        "representative_fund": "请先使用配置占位",
                        "strategy": "dca_only",
                        "weekly_dca_amount": 10,
                    }
                ],
            },
        }

        report = PortfolioBacktester(config).run({})
        asset = report["assets"][0]

        self.assertEqual(asset["status"], "skipped")
        self.assertIn("配置占位", asset["skip_reason"])
        self.assertEqual(report["portfolio_summary"]["skipped_assets"][0]["asset_id"], "GOLD")

    def test_portfolio_real_fund_asset_participates_as_dca_only(self):
        config = {
            **self.config,
            "portfolio_backtest": {
                "enabled": True,
                "start_date": "2026-01-05",
                "bullet_cash_initial": 2000,
                "bullet_cash_monthly_addition": 0,
                "assets": [
                    {
                        "asset_id": "CASHFLOW",
                        "asset_name": "自由现金流",
                        "representative_fund": "023918",
                        "strategy": "dca_only",
                        "weekly_dca_amount": 30,
                    }
                ],
            },
        }
        histories = {
            "023918": [
                {"date": "2026-01-05", "nav": 1.0},
                {"date": "2026-01-12", "nav": 1.2},
            ]
        }

        report = PortfolioBacktester(config).run(histories)
        asset = report["assets"][0]

        self.assertEqual(asset["status"], "active")
        self.assertEqual(asset["representative_fund"], "023918")
        self.assertEqual(asset["dca_invested"], 60)
        self.assertEqual(asset["bullet_invested"], 0)
        self.assertEqual(asset["trigger_count_total"], 0)
        self.assertEqual(report["portfolio_summary"]["skipped_assets"], [])

    def test_collect_portfolio_histories_uses_asset_nav_mode(self):
        portfolio_config = {
            "assets": [
                {
                    "asset_id": "DIVIDEND_LOW_VOL",
                    "asset_name": "红利低波",
                    "representative_fund": "008163",
                    "nav_mode": "accumulated_nav",
                },
                {
                    "asset_id": "GOLD",
                    "asset_name": "黄金",
                    "representative_fund": "000216",
                    "nav_mode": "unit_nav",
                },
            ]
        }
        provider = RecordingPortfolioProvider()

        histories, warnings = collect_portfolio_histories(portfolio_config, provider)

        self.assertEqual(provider.calls, [("008163", "accumulated_nav"), ("000216", "unit_nav")])
        self.assertEqual(histories["008163"][0]["nav"], 2.0)
        self.assertEqual(histories["000216"][0]["nav"], 1.0)
        self.assertEqual(warnings, [])

    def test_portfolio_report_includes_nav_mode(self):
        config = {
            **self.config,
            "portfolio_backtest": {
                "enabled": True,
                "start_date": "2026-01-05",
                "bullet_cash_initial": 2000,
                "bullet_cash_monthly_addition": 0,
                "assets": [
                    {
                        "asset_id": "DIVIDEND_LOW_VOL",
                        "asset_name": "红利低波",
                        "representative_fund": "008163",
                        "nav_mode": "accumulated_nav",
                        "strategy": "dca_only",
                        "weekly_dca_amount": 20,
                    }
                ],
            },
        }
        report = PortfolioBacktester(config).run({"008163": [{"date": "2026-01-05", "nav": 1.0}]})
        asset = report["assets"][0]
        summary = summarize_portfolio_backtest_report(report)

        self.assertEqual(asset["nav_mode"], "accumulated_nav")
        self.assertIn("净值口径 accumulated_nav", summary)

    def test_summarize_portfolio_backtest_report(self):
        report = {
            "portfolio_summary": {
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "total_dca_invested": 100,
                "total_bullet_invested": 50,
                "total_invested": 150,
                "final_market_value": 180,
                "total_profit": 30,
                "total_return_rate": 0.2,
                "bullet_cash_final": 1950,
                "trigger_count_total": 1,
                "skipped_assets": [
                    {
                        "asset_id": "GOLD",
                        "asset_name": "黄金",
                        "skip_reason": "代表基金为配置占位。",
                    }
                ],
            },
            "assets": [
                {
                    "asset_id": "NASDAQ100",
                    "asset_name": "纳斯达克100",
                    "status": "active",
                    "total_invested": 150,
                    "dca_invested": 100,
                    "bullet_invested": 50,
                    "final_market_value": 180,
                    "total_return_rate": 0.2,
                    "trigger_count_total": 1,
                }
            ],
        }

        summary = summarize_portfolio_backtest_report(report)

        self.assertIn("组合回测摘要", summary)
        self.assertIn("组合总投入：150.00 元", summary)
        self.assertIn("NASDAQ100 | 纳斯达克100", summary)
        self.assertIn("GOLD | 黄金", summary)

    def test_asset_backtest_triggers_once_for_grouped_funds(self):
        config = {
            **self.config,
            "asset_config": {
                "assets": [
                    {
                        "code": "NASDAQ100",
                        "name": "NASDAQ100",
                        "fund_codes": ["fund_a", "fund_b"],
                    }
                ]
            },
        }
        fund_a = {"code": "fund_a", "name": "基金A"}
        fund_b = {"code": "fund_b", "name": "基金B"}
        history_a = [
            {"date": "2026-01-01", "nav": 2.0},
            {"date": "2026-01-02", "nav": 1.48},
        ]
        history_b = [
            {"date": "2026-01-01", "nav": 4.0},
            {"date": "2026-01-02", "nav": 2.96},
        ]

        report = AssetBacktester(config).run([(fund_a, history_a), (fund_b, history_b)])
        asset_report = report["asset_reports"][0]

        self.assertEqual(asset_report["asset_code"], "NASDAQ100")
        self.assertEqual(asset_report["fund_codes"], ["fund_a", "fund_b"])
        self.assertEqual(asset_report["trigger_count_total"], 3)
        self.assertEqual(asset_report["trigger_count_by_level"], {"10": 1, "15": 1, "20": 1})
        self.assertEqual(asset_report["total_invested"], 1180)
        self.assertEqual(asset_report["final_cash"], 820)
        self.assertAlmostEqual(asset_report["events"][0]["nav"], 0.74)
        self.assertAlmostEqual(asset_report["total_shares"], 1180 / 0.74)
        self.assertAlmostEqual(asset_report["final_market_value"], 1180)

    def test_summarize_asset_backtest_report(self):
        report = {
            "asset_reports": [
                {
                    "asset_code": "NASDAQ100",
                    "asset_name": "NASDAQ100",
                    "trigger_count_total": 3,
                    "total_invested": 1180,
                    "final_cash": 820,
                    "total_return_rate": 0.1,
                }
            ]
        }

        summary = summarize_asset_backtest_report(report)

        self.assertIn("资产级回测摘要", summary)
        self.assertIn("资产级总触发次数：3", summary)
        self.assertIn("资产级累计现金消耗：1180 元", summary)
        self.assertIn("NASDAQ100 | NASDAQ100", summary)

    def test_single_fund_triggers_three_levels(self):
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-01-02", "nav": 0.74},
        ]

        report = StrategyBacktester(self.config).run([(self.fund, history)])
        fund_report = report["fund_reports"][0]

        self.assertEqual(fund_report["fund_code"], "demo")
        self.assertEqual(fund_report["trigger_count_total"], 3)
        self.assertEqual(fund_report["trigger_count_by_level"], {"10": 1, "15": 1, "20": 1})
        self.assertEqual([event["amount"] for event in fund_report["events"]], [300, 430, 450])
        self.assertEqual([event["cash_after"] for event in fund_report["events"]], [1700, 1270, 820])
        self.assertEqual(fund_report["total_invested"], 1180)
        self.assertEqual(fund_report["final_cash"], 820)
        self.assertEqual(fund_report["start_date"], "2026-01-01")
        self.assertEqual(fund_report["end_date"], "2026-01-02")
        self.assertAlmostEqual(fund_report["total_shares"], 1180 / 0.74)
        self.assertEqual(fund_report["final_nav"], 0.74)
        self.assertAlmostEqual(fund_report["final_market_value"], 1180)
        self.assertAlmostEqual(fund_report["total_profit"], 0)
        self.assertAlmostEqual(fund_report["total_return_rate"], 0)
        self.assertAlmostEqual(fund_report["events"][0]["shares"], 300 / 0.74)

    def test_return_estimate_for_single_drawdown_event_day(self):
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-01-02", "nav": 0.75},
            {"date": "2026-01-03", "nav": 1.0},
        ]

        fund_report = StrategyBacktester(self.config).run([(self.fund, history)])["fund_reports"][0]

        self.assertEqual(fund_report["total_invested"], 1180)
        self.assertAlmostEqual(fund_report["total_shares"], 1180 / 0.75)
        self.assertEqual(fund_report["final_nav"], 1.0)
        self.assertAlmostEqual(fund_report["final_market_value"], 1180 / 0.75)
        self.assertAlmostEqual(fund_report["total_profit"], 1180 / 0.75 - 1180)
        self.assertAlmostEqual(fund_report["total_return_rate"], (1180 / 0.75 - 1180) / 1180)

    def test_return_estimate_accumulates_shares_across_multiple_events(self):
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-01-02", "nav": 0.88},
            {"date": "2026-01-03", "nav": 1.1},
            {"date": "2026-01-04", "nav": 0.99},
            {"date": "2026-01-05", "nav": 1.2},
        ]

        fund_report = StrategyBacktester(self.config).run([(self.fund, history)])["fund_reports"][0]

        expected_shares = 300 / 0.88 + 260 / 0.99
        self.assertEqual(fund_report["total_invested"], 560)
        self.assertAlmostEqual(fund_report["total_shares"], expected_shares)
        self.assertEqual(fund_report["final_nav"], 1.2)
        self.assertAlmostEqual(fund_report["final_market_value"], expected_shares * 1.2)
        self.assertAlmostEqual(
            fund_report["total_return_rate"],
            (expected_shares * 1.2 - 560) / 560,
        )

    def test_return_estimate_has_zero_rate_without_replenishment_events(self):
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-01-02", "nav": 1.1},
        ]

        fund_report = StrategyBacktester(self.config).run([(self.fund, history)])["fund_reports"][0]

        self.assertEqual(fund_report["total_invested"], 0)
        self.assertEqual(fund_report["total_shares"], 0)
        self.assertEqual(fund_report["final_market_value"], 0)
        self.assertEqual(fund_report["total_profit"], 0)
        self.assertEqual(fund_report["total_return_rate"], 0)

    def test_new_high_resets_levels(self):
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-01-02", "nav": 0.88},
            {"date": "2026-01-03", "nav": 1.1},
            {"date": "2026-01-04", "nav": 0.98},
        ]

        fund_report = StrategyBacktester(self.config).run([(self.fund, history)])["fund_reports"][0]

        self.assertEqual(fund_report["trigger_count_by_level"]["10"], 2)
        self.assertEqual(fund_report["trigger_count_total"], 2)
        self.assertEqual([event["level"] for event in fund_report["events"]], ["10", "10"])

    def test_cash_never_goes_negative_when_insufficient(self):
        config = {
            **self.config,
            "backtest": {**self.config["backtest"], "initial_cash": 5},
        }
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-01-02", "nav": 0.74},
        ]

        fund_report = StrategyBacktester(config).run([(self.fund, history)])["fund_reports"][0]

        self.assertEqual(fund_report["final_cash"], 0)
        self.assertTrue(all(event["cash_after"] >= 0 for event in fund_report["events"]))
        self.assertEqual(sum(event["amount"] for event in fund_report["events"]), 5)

    def test_start_date_filters_backtest_period_but_keeps_prior_peak(self):
        config = {
            **self.config,
            "backtest": {**self.config["backtest"], "start_date": "2026-01-03"},
        }
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-01-02", "nav": 0.95},
            {"date": "2026-01-03", "nav": 0.88},
        ]

        fund_report = StrategyBacktester(config).run([(self.fund, history)])["fund_reports"][0]

        self.assertEqual(fund_report["start_date"], "2026-01-03")
        self.assertEqual(fund_report["trigger_count_by_level"]["10"], 1)
        self.assertEqual(fund_report["events"][0]["peak_nav"], 1.0)

    def test_storage_saves_and_loads_backtest_report(self):
        report = {
            "backtest": {"start_date": "2026-01-01"},
            "fund_reports": [{"fund_code": "demo", "trigger_count_total": 1}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))

            storage.save_backtest_report(report)

            saved = json.loads((Path(temp_dir) / "data" / "backtest_report.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, report)
            self.assertEqual(storage.load_backtest_report(), report)

    def test_summarize_backtest_report(self):
        report = {
            "fund_reports": [
                {
                    "fund_code": "demo",
                    "fund_name": "演示基金",
                    "trigger_count_total": 3,
                    "total_invested": 1180,
                    "final_cash": 820,
                    "max_drawdown_seen": -0.26,
                }
            ]
        }

        summary = summarize_backtest_report(report)

        self.assertIn("最近一次回测摘要", summary)
        self.assertIn("总触发次数：3", summary)
        self.assertIn("demo | 演示基金", summary)

    def test_backtest_scenarios_multiple_initial_cash_and_monthly_cash(self):
        history = [
            {"date": "2026-01-01", "nav": 1.0},
            {"date": "2026-01-02", "nav": 0.74},
        ]

        report = run_backtest_scenarios(
            self.config,
            [(self.fund, history)],
            initial_cash_values=[2000, 3000],
            monthly_cash_values=[0, 200],
        )

        self.assertEqual(len(report["scenarios"]), 4)
        self.assertEqual(report["scenarios"][0]["scenario_id"], "S001")
        self.assertEqual(report["scenarios"][0]["initial_cash"], 2000)
        self.assertEqual(report["scenarios"][0]["monthly_cash_addition"], 0)
        self.assertEqual(report["scenarios"][1]["monthly_cash_addition"], 200)
        self.assertEqual(report["scenarios"][2]["initial_cash"], 3000)
        first_fund = report["scenarios"][0]["funds"][0]
        self.assertEqual(first_fund["trigger_count_total"], 3)
        self.assertEqual(first_fund["trigger_count_by_level"], {"10": 1, "15": 1, "20": 1})
        self.assertEqual(first_fund["total_invested"], 1180)
        self.assertAlmostEqual(first_fund["total_shares"], 1180 / 0.74)
        self.assertEqual(first_fund["final_nav"], 0.74)
        self.assertAlmostEqual(first_fund["final_market_value"], 1180)
        self.assertAlmostEqual(first_fund["total_profit"], 0)
        self.assertAlmostEqual(first_fund["total_return_rate"], 0)
        self.assertEqual(len(report["summary"]["scenarios"]), 4)
        self.assertEqual(report["summary"]["scenarios"][0]["trigger_count_total"], 3)
        self.assertEqual(report["summary"]["scenarios"][0]["total_invested"], 1180)
        self.assertEqual(report["summary"]["scenarios"][0]["final_cash_total"], 820)
        self.assertAlmostEqual(report["summary"]["scenarios"][0]["final_market_value_total"], 1180)
        self.assertAlmostEqual(report["summary"]["scenarios"][0]["total_profit"], 0)
        self.assertAlmostEqual(report["summary"]["scenarios"][0]["total_return_rate"], 0)
        self.assertEqual(report["summary"]["fund_comparisons"][0]["fund_code"], "demo")
        self.assertEqual(len(report["summary"]["fund_comparisons"][0]["scenarios"]), 4)

    def test_summarize_scenarios_report(self):
        report = {
            "scenarios": [{"scenario_id": "S001"}],
            "summary": {
                "scenarios": [
                    {
                        "scenario_id": "S001",
                        "initial_cash": 2000,
                        "monthly_cash_addition": 0,
                        "trigger_count_total": 3,
                        "total_invested": 1180,
                        "final_cash_total": 820,
                    }
                ]
            },
        }

        summary = summarize_scenarios_report(report)

        self.assertIn("多参数回测场景摘要", summary)
        self.assertIn("场景数量：1", summary)
        self.assertIn("S001 | 初始 2000 元 | 月追加 0 元", summary)

    def test_summarize_backtest_returns(self):
        report = {
            "fund_reports": [
                {
                    "fund_code": "demo",
                    "fund_name": "演示基金",
                    "total_invested": 100,
                    "final_market_value": 120,
                    "total_profit": 20,
                    "total_return_rate": 0.2,
                }
            ]
        }

        summary = summarize_backtest_returns(report)

        self.assertIn("最近一次回测收益估算", summary)
        self.assertIn("估算市值 120.00 元", summary)
        self.assertIn("总收益率 20.00%", summary)
        self.assertIn("不代表真实账户收益", summary)

    def test_summarize_scenarios_returns_handles_zero_investment(self):
        report = {
            "scenarios": [
                {
                    "scenario_id": "S001",
                    "initial_cash": 2000,
                    "monthly_cash_addition": 0,
                    "funds": [
                        {
                            "fund_code": "demo",
                            "fund_name": "演示基金",
                            "total_invested": 0,
                            "final_market_value": 0,
                            "total_profit": 0,
                            "total_return_rate": 0,
                        }
                    ],
                }
            ]
        }

        summary = summarize_scenarios_returns(report)

        self.assertIn("多参数场景收益估算", summary)
        self.assertIn("总收益率 0.00%", summary)
        self.assertIn("不代表真实账户收益", summary)

    def test_storage_saves_scenarios_report(self):
        report = {
            "scenarios": [
                {
                    "scenario_id": "S001",
                    "initial_cash": 2000,
                    "monthly_cash_addition": 0,
                    "funds": [],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))

            storage.save_scenarios_report(report)

            saved = json.loads((Path(temp_dir) / "data" / "scenarios_report.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, report)

    def test_storage_saves_portfolio_backtest_report(self):
        report = {
            "portfolio_summary": {"total_invested": 100},
            "assets": [{"asset_id": "NASDAQ100"}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))

            storage.save_portfolio_backtest_report(report)

            saved = json.loads((Path(temp_dir) / "data" / "portfolio_backtest_report.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, report)
            self.assertEqual(storage.load_portfolio_backtest_report(), report)

    def test_storage_saves_weekly_dca_analysis(self):
        report = {
            "results": [{"weekday_label": "周一", "total_return_rate": 0.1}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))

            storage.save_weekly_dca_analysis(report)

            saved = json.loads((Path(temp_dir) / "data" / "weekly_dca_analysis.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, report)
            self.assertEqual(storage.load_weekly_dca_analysis(), report)

    def test_storage_saves_strategy_lab_report(self):
        report = {
            "strategies": [{"strategy_name": "A", "total_return_rate": 0.1}],
            "rankings": {"return_rate": ["A"]},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))

            storage.save_strategy_lab_report(report)

            saved = json.loads((Path(temp_dir) / "data" / "strategy_lab_report.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, report)
            self.assertEqual(storage.load_strategy_lab_report(), report)


if __name__ == "__main__":
    unittest.main()
