import unittest
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from drawdownguard.daily_workflow import (
    PROXY_ENV_KEYS,
    build_network_debug_report,
    format_daily_summary,
    proxy_environment,
    run_daily_workflow,
)
from drawdownguard.storage import Storage


class DailyWorkflowTest(unittest.TestCase):
    def test_daily_workflow_runs_steps_in_order(self):
        calls = []
        steps = [
            {"name": "policy-check", "func": _step(calls, "policy-check")},
            {"name": "run", "func": _step(calls, "run")},
            {"name": "portfolio-backtest", "func": _step(calls, "portfolio-backtest")},
            {"name": "contribution-report", "func": _step(calls, "contribution-report")},
            {"name": "rebalance-advice", "func": _step(calls, "rebalance-advice")},
            {"name": "committee-report", "func": _step(calls, "committee-report")},
        ]

        report = run_daily_workflow(steps, save_report=lambda item: None, today="2026-06-16")

        self.assertEqual(calls, [step["name"] for step in steps])
        self.assertEqual(report["status"], "success")

    def test_run_step_source_is_fresh_execution(self):
        report = run_daily_workflow(
            [
                {
                    "name": "run",
                    "func": lambda: {
                        "status": "success",
                        "message": "OK",
                        "result_source": "fresh_execution",
                    },
                },
                {"name": "committee-report", "func": lambda: {"status": "success", "message": "OK"}},
            ],
            save_report=lambda item: None,
        )

        self.assertEqual(report["run_step_source"], "fresh_execution")
        self.assertIn("run结果来源：fresh_execution", format_daily_summary(report))

    def test_quick_mode_skips_backtest_and_contribution(self):
        calls = []
        steps = [
            {"name": "policy-check", "func": _step(calls, "policy-check")},
            {"name": "run", "func": _step(calls, "run")},
            {
                "name": "portfolio-backtest",
                "func": _step(calls, "portfolio-backtest"),
                "skip": True,
                "skip_message": "daily quick/skip-backtest 模式已跳过组合回测。",
            },
            {
                "name": "contribution-report",
                "func": _step(calls, "contribution-report"),
                "skip": True,
                "skip_message": "daily quick 模式已跳过资产贡献分析。",
            },
            {"name": "rebalance-advice", "func": _step(calls, "rebalance-advice")},
            {"name": "committee-report", "func": _step(calls, "committee-report")},
        ]

        report = run_daily_workflow(steps, save_report=lambda item: None)

        self.assertNotIn("portfolio-backtest", calls)
        self.assertNotIn("contribution-report", calls)
        skipped = [step["name"] for step in report["steps"] if step["status"] == "skipped"]
        self.assertEqual(skipped, ["portfolio-backtest", "contribution-report"])
        self.assertEqual(report["status"], "success")
        self.assertIn("daily quick/skip-backtest 模式已跳过组合回测。", report["infos"])
        self.assertIn("daily quick 模式已跳过资产贡献分析。", report["infos"])

    def test_failed_step_does_not_crash_workflow(self):
        calls = []
        steps = [
            {"name": "policy-check", "func": _step(calls, "policy-check")},
            {"name": "run", "func": _raising_step(calls, "run")},
            {"name": "rebalance-advice", "func": _step(calls, "rebalance-advice")},
            {"name": "committee-report", "func": _step(calls, "committee-report")},
        ]

        report = run_daily_workflow(steps, save_report=lambda item: None)

        self.assertEqual(calls, ["policy-check", "run", "rebalance-advice", "committee-report"])
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["steps"][1]["status"], "failed")

    def test_daily_run_report_is_saved(self):
        with TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))
            report = run_daily_workflow(
                [{"name": "committee-report", "func": lambda: {"status": "success", "message": "OK"}}],
                save_report=storage.save_daily_run_report,
                today="2026-06-16",
            )

            saved = storage.load_daily_run_report()
            self.assertEqual(saved["date"], "2026-06-16")
            self.assertEqual(saved["status"], report["status"])
            self.assertTrue((Path(temp_dir) / "data" / "daily_run_report.json").exists())

    def test_committee_report_failure_marks_daily_failed(self):
        steps = [
            {"name": "policy-check", "func": lambda: {"status": "success", "message": "OK"}},
            {"name": "committee-report", "func": lambda: {"status": "failed", "message": "无法生成"}},
        ]

        report = run_daily_workflow(steps, save_report=lambda item: None)

        self.assertEqual(report["status"], "failed")
        self.assertIn("committee-report: 无法生成", report["errors"])

    def test_warnings_are_collected(self):
        steps = [
            {
                "name": "run",
                "func": lambda: {
                    "status": "warning",
                    "message": "真实净值拉取失败",
                    "warnings": ["AKShare warning"],
                },
            },
            {"name": "committee-report", "func": lambda: {"status": "success", "message": "OK"}},
        ]

        report = run_daily_workflow(steps, save_report=lambda item: None)

        self.assertEqual(report["status"], "warning")
        self.assertIn("AKShare warning", report["warnings"])
        self.assertIn("run: 真实净值拉取失败", report["warnings"])

    def test_info_only_does_not_make_daily_warning(self):
        report = run_daily_workflow(
            [
                {
                    "name": "portfolio-backtest",
                    "func": lambda: {
                        "status": "success",
                        "message": "OK",
                        "infos": ["NASDAQ100: 012752 定投在资产级回测中使用代表基金 270042 净值作为 fallback。"],
                    },
                },
                {"name": "committee-report", "func": lambda: {"status": "success", "message": "OK"}},
            ],
            save_report=lambda item: None,
        )

        self.assertEqual(report["status"], "success")
        self.assertIn("012752 定投", report["infos"][0])

    def test_error_makes_daily_failed(self):
        report = run_daily_workflow(
            [
                {"name": "policy-check", "func": lambda: {"status": "failed", "message": "配置错误", "errors": ["policy failed"]}},
                {"name": "committee-report", "func": lambda: {"status": "success", "message": "OK"}},
            ],
            save_report=lambda item: None,
        )

        self.assertEqual(report["status"], "failed")
        self.assertIn("policy failed", report["errors"])

    def test_012752_fallback_is_info(self):
        import main

        infos, warnings = main._split_portfolio_messages(
            [
                {
                    "asset_id": "NASDAQ100",
                    "fund_code": "012752",
                    "warnings": ["012752 定投在资产级回测中使用代表基金 270042 净值作为 fallback。"],
                }
            ]
        )

        self.assertEqual(len(infos), 1)
        self.assertEqual(warnings, [])

    def test_summary_contains_final_report_and_conclusion(self):
        report = run_daily_workflow(
            [{"name": "committee-report", "func": lambda: {"status": "success", "message": "OK"}}],
            save_report=lambda item: None,
            conclusion_builder=lambda: {
                "drawdown_triggered": False,
                "needs_immediate_rebalance": False,
                "future_dca_bias": "CORE",
                "quant_market_regime": "neutral",
                "core_asset_score": 92,
            },
        )

        summary = format_daily_summary(report)

        self.assertIn("DrawdownGuard Daily Workflow", summary)
        self.assertIn("data/committee_report.md", summary)
        self.assertIn("未来定投方向：CORE", summary)
        self.assertIn("市场环境：neutral", summary)
        self.assertIn("核心资产量化分数：92", summary)

    def test_daily_default_includes_quant_signal_step(self):
        import main

        steps = main._daily_steps(_daily_args(quick=False))

        self.assertEqual(
            [step["name"] for step in steps],
            [
                "policy-check",
                "run",
                "portfolio-backtest",
                "contribution-report",
                "quant-signal",
                "watchlist-analyze",
                "rebalance-advice",
                "committee-report",
            ],
        )

    def test_daily_quick_includes_quant_before_rebalance(self):
        import main

        steps = main._daily_steps(_daily_args(quick=True))
        names = [step["name"] for step in steps]

        self.assertIn("quant-signal", names)
        self.assertLess(names.index("quant-signal"), names.index("rebalance-advice"))
        self.assertLess(names.index("watchlist-analyze"), names.index("rebalance-advice"))
        self.assertTrue(steps[names.index("portfolio-backtest")]["skip"])
        self.assertTrue(steps[names.index("contribution-report")]["skip"])
        self.assertTrue(steps[names.index("watchlist-analyze")]["skip"])
        self.assertFalse(steps[names.index("quant-signal")].get("skip", False))

    def test_skip_quant_skips_step_and_writes_info(self):
        report = run_daily_workflow(
            [
                {
                    "name": "quant-signal",
                    "func": lambda: {"status": "success", "message": "should not run"},
                    "skip": True,
                    "skip_message": "daily --skip-quant 已跳过量化信号刷新，committee-report 将使用已有 quant_signal_report.json。",
                },
                {"name": "committee-report", "func": lambda: {"status": "success", "message": "OK"}},
            ],
            save_report=lambda item: None,
        )

        self.assertEqual(report["steps"][0]["status"], "skipped")
        self.assertIn("daily --skip-quant 已跳过量化信号刷新", report["infos"][0])
        self.assertEqual(report["status"], "success")

    def test_daily_conclusion_contains_quant_fields(self):
        import main

        quant_report = {
            "portfolio_quant_summary": {
                "market_regime": "neutral",
                "average_quant_score": 62,
                "core_asset_score": 92,
            }
        }

        with patch.object(main.Storage, "load_daily_logs", return_value=[]), patch.object(
            main.Storage,
            "load_rebalance_advice",
            return_value={"conclusion": {"needs_immediate_rebalance": False, "future_dca_bias": "CORE"}},
        ), patch.object(main.Storage, "load_quant_signal_report", return_value=quant_report):
            conclusion = main._build_daily_conclusion()

        self.assertEqual(conclusion["quant_market_regime"], "neutral")
        self.assertEqual(conclusion["average_quant_score"], 62)
        self.assertEqual(conclusion["core_asset_score"], 92)

    def test_quant_warning_does_not_make_daily_failed(self):
        report = run_daily_workflow(
            [
                {
                    "name": "quant-signal",
                    "func": lambda: {
                        "status": "warning",
                        "message": "量化信号完成，但存在数据 warning。",
                        "warnings": ["CASHFLOW: 净值数据不足120条"],
                    },
                },
                {"name": "committee-report", "func": lambda: {"status": "success", "message": "OK"}},
            ],
            save_report=lambda item: None,
        )

        self.assertEqual(report["status"], "warning")
        self.assertNotEqual(report["status"], "failed")

    def test_clean_proxy_removes_and_restores_proxy_environment(self):
        previous = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
        try:
            for key in PROXY_ENV_KEYS:
                os.environ[key] = "http://127.0.0.1:7890"

            with proxy_environment(clean_proxy=True):
                self.assertTrue(all(key not in os.environ for key in PROXY_ENV_KEYS))

            for key in PROXY_ENV_KEYS:
                self.assertEqual(os.environ.get(key), "http://127.0.0.1:7890")
        finally:
            _restore_env(previous)

    def test_daily_run_step_uses_clean_proxy_environment(self):
        previous = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
        try:
            os.environ["http_proxy"] = "http://127.0.0.1:7890"
            observed = {}

            def run_step():
                observed["http_proxy"] = os.environ.get("http_proxy")
                return {"status": "success", "message": "OK"}

            report = run_daily_workflow(
                [
                    {"name": "run", "func": run_step},
                    {"name": "committee-report", "func": lambda: {"status": "success", "message": "OK"}},
                ],
                save_report=lambda item: None,
                clean_proxy=True,
            )

            self.assertIsNone(observed["http_proxy"])
            self.assertTrue(report["clean_proxy"])
            self.assertEqual(report["network_proxy_mode"], "clean_proxy")
            self.assertEqual(os.environ.get("http_proxy"), "http://127.0.0.1:7890")
        finally:
            _restore_env(previous)

    def test_inherited_proxy_mode_keeps_environment_for_daily_run(self):
        previous = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
        try:
            os.environ["http_proxy"] = "http://127.0.0.1:7890"
            observed = {}

            def run_step():
                observed["http_proxy"] = os.environ.get("http_proxy")
                return {"status": "success", "message": "OK"}

            report = run_daily_workflow(
                [
                    {"name": "run", "func": run_step},
                    {"name": "committee-report", "func": lambda: {"status": "success", "message": "OK"}},
                ],
                save_report=lambda item: None,
                clean_proxy=False,
            )

            self.assertEqual(observed["http_proxy"], "http://127.0.0.1:7890")
            self.assertFalse(report["clean_proxy"])
            self.assertEqual(report["network_proxy_mode"], "inherited_env")
        finally:
            _restore_env(previous)

    def test_daily_run_step_does_not_read_old_warning(self):
        import main

        args = SimpleNamespace(config="config.yaml", nav_file="nav_data.json")
        execution = {
            "code": 0,
            "provider_class": "NavDataProvider",
            "results": [
                {
                    "fund_code": "270042",
                    "fund_name": "广发纳指",
                    "data_source": "real",
                    "warnings": [],
                    "suggested_amounts": {},
                }
            ],
        }

        with patch.object(main, "run_monitor_execution", return_value=execution):
            result = main._daily_run(args)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result_source"], "fresh_execution")
        self.assertEqual(result["warnings"] if "warnings" in result else [], [])

    def test_direct_run_success_means_daily_ignores_old_failed_warning(self):
        import main

        args = SimpleNamespace(config="config.yaml", nav_file="nav_data.json")
        old_warning = "270042: fund.eastmoney.com DNS 解析失败"
        execution = {
            "code": 0,
            "provider_class": "NavDataProvider",
            "results": [
                {
                    "fund_code": "270042",
                    "fund_name": "广发纳指",
                    "data_source": "real",
                    "warnings": [],
                    "suggested_amounts": {},
                }
            ],
        }

        with patch.object(main, "run_monitor_execution", return_value=execution), patch.object(
            main,
            "_daily_log_warnings",
            return_value=[old_warning],
        ):
            result = main._daily_run(args)

        self.assertEqual(result["status"], "success")
        self.assertNotIn(old_warning, result.get("warnings", []))

    def test_network_debug_reports_data_provider(self):
        debug = build_network_debug_report(provider_name="NavDataProvider")

        self.assertEqual(debug["data_provider"], "NavDataProvider")
        self.assertEqual(debug["run_call_path"], "direct_internal_function")


def _step(calls, name):
    def run():
        calls.append(name)
        return {"status": "success", "message": "OK"}

    return run


def _raising_step(calls, name):
    def run():
        calls.append(name)
        raise RuntimeError("boom")

    return run


def _restore_env(previous):
    for key in PROXY_ENV_KEYS:
        if previous.get(key) is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous[key]


def _daily_args(quick=False, skip_quant=False):
    return SimpleNamespace(
        config="config.yaml",
        nav_file="nav_data.json",
        start_date="2018-01-01",
        quick=quick,
        skip_backtest=False,
        skip_quant=skip_quant,
        include_watchlist=False,
    )
