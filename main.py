import argparse
from datetime import date
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
from drawdownguard.asset_dca_audit import run_asset_dca_audit, summarize_asset_dca_audit
from drawdownguard.data_provider import NavDataProvider
from drawdownguard.contribution import run_contribution_analysis, summarize_contribution_report
from drawdownguard.dca_strategy_lab import (
    default_dca_workers,
    run_dca_strategy_lab,
    summarize_dca_strategy_report,
)
from drawdownguard.draw_backtest import plot_report_file
from drawdownguard.email_notifier import send_daily_email
from drawdownguard.fund_check import run_fund_check, summarize_fund_check_report
from drawdownguard.notifier import format_daily_logs, format_report, format_transactions
from drawdownguard.portfolio_constraint_optimizer import (
    default_optimizer_workers,
    run_portfolio_constraint_optimizer,
    summarize_portfolio_optimize_report,
)
from drawdownguard.portfolio_continuous_optimizer import (
    run_portfolio_continuous_optimizer,
    summarize_portfolio_continuous_report,
)
from drawdownguard.portfolio_strategy import (
    run_portfolio_strategy_synth,
    summarize_portfolio_strategy_report,
)
from drawdownguard.risk_compare import run_risk_compare, summarize_risk_compare_report
from drawdownguard.storage import Storage
from drawdownguard.strategy import DrawdownStrategy
from drawdownguard.strategy_lab import run_strategy_lab, summarize_strategy_lab_report
from drawdownguard.take_profit import TakeProfitBacktester, summarize_take_profit_report
from drawdownguard.take_profit_optimizer import (
    default_worker_count,
    generate_take_profit_combinations,
    run_take_profit_optimizer,
    summarize_take_profit_optimizer_report,
)
from drawdownguard.weekly_dca_analysis import run_weekly_dca_analysis, summarize_weekly_dca_analysis


BASE_DIR = Path(__file__).resolve().parent


def build_app(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    records = storage.load_records()
    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    strategy = DrawdownStrategy(config)
    return storage, config, records, provider, strategy


def create_skipped_result(fund, nav_data):
    return {
        "fund_code": fund["code"],
        "fund_name": fund["name"],
        "data_source": nav_data.get("source", "unknown"),
        "warnings": nav_data.get("warnings", []),
        "skipped": True,
        "status": "净值数据缺失，已跳过",
        "suggested_amounts": {},
        "pending_levels": {},
    }


def run_monitor(args):
    storage, config, records, provider, strategy = build_app(args)
    results = []

    for fund in config["funds"]:
        nav_data = provider.get_history(fund["code"])
        if not nav_data["history"]:
            result = create_skipped_result(fund, nav_data)
            results.append(result)
            continue
        try:
            result = strategy.evaluate_fund(fund, nav_data["history"], records)
            result["data_source"] = nav_data["source"]
            result["warnings"] = nav_data["warnings"]
        except Exception as exc:
            result = create_skipped_result(
                fund,
                {
                    "source": nav_data["source"],
                    "warnings": [*nav_data["warnings"], f"策略计算失败：{exc}"],
                },
            )
        results.append(result)

    storage.save_records(records)
    storage.upsert_daily_logs(build_daily_log_entries(results))
    report = format_report(results, config)
    print(report)
    email_status = send_daily_email(config, results)
    if email_status.get("warning"):
        print(f"警告：{email_status['warning']}")
    return 0


def build_daily_log_entries(results):
    entries = []
    for result in results:
        entries.append(
            {
                "date": result.get("current_date") or date.today().isoformat(),
                "fund_code": result["fund_code"],
                "fund_name": result["fund_name"],
                "nav": result.get("current_nav"),
                "peak_nav": result.get("peak_nav"),
                "drawdown": result.get("drawdown"),
                "status": result["status"],
                "suggestions": dict(result.get("suggested_amounts", {})),
                "data_source": result.get("data_source", "unknown"),
                "warnings": list(result.get("warnings", [])),
            }
        )
    return entries


def confirm_transaction(args):
    storage, config, records, provider, strategy = build_app(args)
    fund = storage.find_fund(config, args.fund)
    if not fund:
        print(f"未找到基金：{args.fund}")
        return 1

    nav_data = provider.get_history(fund["code"])
    if not nav_data["history"]:
        print(f"{fund['name']} 净值数据缺失，已跳过。")
        return 1
    result = strategy.evaluate_fund(fund, nav_data["history"], records)
    level_key = str(args.level)

    if level_key not in strategy.levels:
        print(f"不支持的补仓档位：{args.level}%。可用档位：{', '.join(strategy.levels)}")
        return 1
    if not result["triggered_levels"].get(level_key):
        print(f"{fund['name']} 当前未触发 {args.level}% 档位。")
        return 1

    amount = args.amount if args.amount is not None else result["suggested_amounts"].get(level_key, 0)
    if amount <= 0:
        print("补仓金额必须大于 0。")
        return 1

    bullet = config["bullet_account"]
    if amount > bullet["balance"]:
        print(f"子弹仓余额不足：当前 {bullet['balance']} 元，需要 {amount} 元。")
        return 1

    bullet["balance"] -= amount
    records.setdefault(fund["code"], {}).setdefault("executed_levels", {})[level_key] = True
    records[fund["code"]]["pending_levels"][level_key] = False

    transactions = storage.load_transactions()
    transactions.append(
        {
            "date": args.date,
            "fund_code": fund["code"],
            "fund": fund["name"],
            "level": f"{args.level}%",
            "amount": amount,
            "nav": result["current_nav"],
            "drawdown": result["drawdown"],
        }
    )

    storage.save_config(config, args.config)
    storage.save_records(records)
    storage.save_transactions(transactions)
    print(f"已确认补仓：{fund['name']} {args.level}% 档，金额 {amount} 元。")
    return 0


def set_cash(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    if args.amount < 0:
        print("子弹仓余额不能为负数。")
        return 1
    config["bullet_account"]["balance"] = args.amount
    storage.save_config(config, args.config)
    print(f"已更新子弹仓余额：{args.amount} 元。")
    return 0


def show_transactions(args):
    storage = Storage(BASE_DIR)
    transactions = storage.load_transactions()
    print(format_transactions(transactions))
    return 0


def show_daily_logs(args):
    storage = Storage(BASE_DIR)
    logs = storage.load_daily_logs()
    print(format_daily_logs(logs, limit=10))
    return 0


def run_backtest(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    backtest_config = config.get("backtest", {})
    if not backtest_config.get("enabled", True):
        print("回测未启用，请在 config.yaml 中设置 backtest.enabled = true。")
        return 1

    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    fund_histories, warnings = collect_backtest_histories(config, provider)

    report = StrategyBacktester(config).run(fund_histories)
    report["warnings"] = warnings
    storage.save_backtest_report(report)
    print("回测完成，报告已写入 data/backtest_report.json")
    print(summarize_backtest_report(report))
    return 0


def collect_backtest_histories(config, provider):
    fund_histories = []
    warnings = []
    backtest_funds = set(config.get("backtest", {}).get("funds", []))

    for fund in config["funds"]:
        if backtest_funds and fund["code"] not in backtest_funds:
            continue
        nav_data = provider.get_full_history(fund["code"])
        if nav_data["warnings"]:
            warnings.append({"fund_code": fund["code"], "warnings": nav_data["warnings"]})
        if nav_data["history"]:
            fund_histories.append((fund, nav_data["history"]))

    return fund_histories, warnings


def show_backtest_report(args):
    storage = Storage(BASE_DIR)
    report = storage.load_backtest_report()
    if not report:
        print("暂无回测报告，请先运行 python3 main.py backtest。")
        return 0
    print(summarize_backtest_report(report))
    return 0


def show_backtest_returns(args):
    storage = Storage(BASE_DIR)
    report = storage.load_backtest_report()
    if not report:
        print("暂无回测报告，请先运行 python3 main.py backtest。")
        return 0
    print(summarize_backtest_returns(report))
    return 0


def run_asset_backtest(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    if not config.get("asset_config", {}).get("assets"):
        print("未配置 asset_config.assets，无法运行资产级回测。")
        return 1

    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    fund_histories, warnings = collect_backtest_histories(config, provider)
    report = AssetBacktester(config).run(fund_histories)
    report["warnings"] = warnings
    storage.save_asset_backtest_report(report)
    print("资产级回测完成，报告已写入 data/asset_backtest_report.json")
    print(summarize_asset_backtest_report(report))
    return 0


def show_asset_backtest_report(args):
    storage = Storage(BASE_DIR)
    report = storage.load_asset_backtest_report()
    if not report:
        print("暂无资产级回测报告，请先运行 python3 main.py asset-backtest。")
        return 0
    print(summarize_asset_backtest_report(report))
    return 0


def run_portfolio_backtest(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    portfolio_config = config.get("portfolio_backtest", {})
    if not portfolio_config.get("enabled", True):
        print("组合回测未启用，请在 config.yaml 中设置 portfolio_backtest.enabled = true。")
        return 1
    if args.start_date:
        portfolio_config["start_date"] = args.start_date
    if args.end_date:
        portfolio_config["end_date"] = args.end_date

    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    histories, warnings = collect_portfolio_histories(portfolio_config, provider)
    report = PortfolioBacktester(config).run(histories)
    report["warnings"] = [*report.get("warnings", []), *warnings]
    storage.save_portfolio_backtest_report(report)
    print("组合回测完成，报告已写入 data/portfolio_backtest_report.json")
    print(summarize_portfolio_backtest_report(report))
    return 0


def run_fund_check_command(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    portfolio_config = config.get("portfolio_backtest", {})
    if not portfolio_config.get("assets"):
        print("未配置 portfolio_backtest.assets，无法检查基金数据。")
        return 1

    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    portfolio_report = storage.load_portfolio_backtest_report()
    report = run_fund_check(config, provider, portfolio_report=portfolio_report)
    storage.save_fund_check_report(report)
    print("基金数据检查完成，报告已写入 data/fund_check_report.json")
    print(summarize_fund_check_report(report))
    return 0


def run_asset_dca_audit_command(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    portfolio_report = storage.load_portfolio_backtest_report()
    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    try:
        report = run_asset_dca_audit(config, provider, args.asset, portfolio_report=portfolio_report)
    except ValueError as exc:
        print(str(exc))
        return 1

    storage.save_asset_dca_audit_report(report["asset_id"], report)
    print(f"资产定投审计完成，报告已写入 data/asset_dca_audit_{report['asset_id']}.json")
    print(summarize_asset_dca_audit(report))
    return 0


def collect_portfolio_histories(portfolio_config, provider):
    histories = {}
    warnings = []
    for asset in portfolio_config.get("assets", []):
        fund_code = asset.get("representative_fund", "")
        nav_mode = asset.get("nav_mode", "unit_nav")
        if not fund_code or "请先" in fund_code:
            warnings.append(f"{asset.get('asset_id')} 代表基金为配置占位，已跳过。")
            continue
        if fund_code in histories:
            continue
        try:
            nav_data = provider.get_full_history(fund_code, nav_mode=nav_mode)
        except TypeError:
            nav_data = provider.get_full_history(fund_code)
        if nav_data.get("nav_mode") and nav_data.get("nav_mode") != nav_mode:
            asset["nav_mode"] = nav_data["nav_mode"]
        if nav_data["warnings"]:
            warnings.append(
                {
                    "asset_id": asset.get("asset_id"),
                    "fund_code": fund_code,
                    "nav_mode": nav_data.get("nav_mode", nav_mode),
                    "warnings": nav_data["warnings"],
                }
            )
        if nav_data["history"]:
            histories[fund_code] = nav_data["history"]
    return histories, warnings


def show_portfolio_report(args):
    storage = Storage(BASE_DIR)
    report = storage.load_portfolio_backtest_report()
    if not report:
        print("暂无组合回测报告，请先运行 python3 main.py portfolio-backtest。")
        return 0
    print(summarize_portfolio_backtest_report(report))
    return 0


def run_contribution_report_command(args):
    report = _build_and_save_contribution_report()
    if report is None:
        return 1
    print("资产贡献分析完成，报告已写入 data/contribution_report.json")
    print(summarize_contribution_report(report))
    return 0


def show_contribution_detail(args):
    report = _build_and_save_contribution_report()
    if report is None:
        return 1
    print(summarize_contribution_report(report, detail=True))
    return 0


def _build_and_save_contribution_report():
    storage = Storage(BASE_DIR)
    portfolio_report = storage.load_portfolio_backtest_report()
    if not portfolio_report:
        print("未找到 data/portfolio_backtest_report.json。请先运行：")
        print("python3 main.py portfolio-backtest --start-date 2018-01-01")
        return None
    report = run_contribution_analysis(portfolio_report)
    storage.save_contribution_report(report)
    return report


def run_weekly_dca(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    portfolio_config = config.get("portfolio_backtest", {})
    if not portfolio_config.get("enabled", True):
        print("组合回测未启用，请在 config.yaml 中设置 portfolio_backtest.enabled = true。")
        return 1

    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    histories, warnings = collect_portfolio_histories(portfolio_config, provider)
    report = run_weekly_dca_analysis(config, histories, source=args.source)
    report["warnings"] = [*report.get("warnings", []), *warnings]
    storage.save_weekly_dca_analysis(report)
    print("定投周几分析完成，报告已写入 data/weekly_dca_analysis.json")
    print(summarize_weekly_dca_analysis(report))
    return 0


def run_dca_strategy_lab_command(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    portfolio_config = config.get("portfolio_backtest", {})
    if not portfolio_config.get("enabled", True):
        print("组合回测未启用，请在 config.yaml 中设置 portfolio_backtest.enabled = true。")
        return 1
    if args.start_date:
        portfolio_config["start_date"] = args.start_date
    if args.end_date:
        portfolio_config["end_date"] = args.end_date

    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    histories, warnings = collect_portfolio_histories(portfolio_config, provider)
    portfolio_report = storage.load_portfolio_backtest_report()
    fallback_warnings = _fill_histories_from_portfolio_report(histories, portfolio_config, portfolio_report)
    warnings.extend(fallback_warnings)
    workers = args.workers or default_dca_workers()
    if workers <= 0:
        print("--workers 必须大于 0")
        return 1

    print(f"preset：{args.preset}")
    print(f"workers：{workers}")

    def show_progress(completed, total, elapsed, eta):
        if completed != total and completed % max(1, min(50, total // 20 or 1)) != 0:
            return
        print(
            f"进度：{completed}/{total} | 已耗时：{_format_seconds(elapsed)} | "
            f"预计剩余：{_format_seconds(eta) if eta is not None else 'N/A'}",
            flush=True,
        )

    try:
        report = run_dca_strategy_lab(
            config,
            histories,
            preset=args.preset,
            workers=workers,
            start_date=portfolio_config.get("start_date"),
            end_date=portfolio_config.get("end_date"),
            checkpoint_path=BASE_DIR / "data" / "dca_strategy_checkpoint.json",
            progress_callback=show_progress,
        )
    except KeyboardInterrupt:
        print("\n已中断，checkpoint 已尽量保存到 data/dca_strategy_checkpoint.json")
        return 130
    report["warnings"] = warnings
    storage.save_dca_strategy_report(report)
    print("DCA Strategy Lab 完成，报告已写入 data/dca_strategy_report.json")
    print(summarize_dca_strategy_report(report))
    return 0


def _fill_histories_from_portfolio_report(histories, portfolio_config, portfolio_report):
    if not portfolio_report:
        return []
    warnings = []
    report_assets = {
        asset.get("representative_fund"): asset
        for asset in portfolio_report.get("assets", [])
        if asset.get("representative_fund")
    }
    for asset in portfolio_config.get("assets", []):
        fund_code = asset.get("representative_fund")
        if not fund_code or fund_code in histories:
            continue
        report_asset = report_assets.get(fund_code)
        if not report_asset or not report_asset.get("series"):
            continue
        histories[fund_code] = [
            {"date": item["date"], "nav": item["nav"]}
            for item in report_asset.get("series", [])
            if item.get("date") and item.get("nav") is not None
        ]
        warnings.append(
            {
                "asset_id": asset.get("asset_id"),
                "fund_code": fund_code,
                "warnings": ["实时/本地净值缺失，DCA Strategy Lab 已使用 portfolio_backtest_report.json 中的 series。"],
            }
        )
    return warnings


def show_dca_strategy_report(args):
    storage = Storage(BASE_DIR)
    report = storage.load_dca_strategy_report()
    if not report:
        print("暂无 DCA 策略报告，请先运行 python3 main.py dca-strategy-lab --preset quick。")
        return 0
    print(summarize_dca_strategy_report(report))
    return 0


def run_portfolio_strategy_synth_command(args):
    storage = Storage(BASE_DIR)
    portfolio_report = storage.load_portfolio_backtest_report()
    if not portfolio_report:
        print("未找到 data/portfolio_backtest_report.json，请先运行 python3 main.py portfolio-backtest --start-date 2018-01-01")
        return 1
    dca_report = storage.load_dca_strategy_report()
    if not dca_report:
        print("未找到 data/dca_strategy_report.json，请先运行 python3 main.py dca-strategy-lab --preset quick")
        return 1
    audit_reports = _load_asset_audit_reports(storage, portfolio_report)
    report = run_portfolio_strategy_synth(portfolio_report, dca_report, audit_reports)
    storage.save_portfolio_strategy_report(report)
    print("组合策略合成完成，报告已写入 data/portfolio_strategy_report.json")
    print(summarize_portfolio_strategy_report(report))
    return 0


def show_portfolio_strategy_report(args):
    storage = Storage(BASE_DIR)
    report = storage.load_portfolio_strategy_report()
    if not report:
        print("暂无组合策略合成报告，请先运行 python3 main.py portfolio-strategy-synth。")
        return 0
    print(summarize_portfolio_strategy_report(report))
    return 0


def run_portfolio_optimize_command(args):
    storage = Storage(BASE_DIR)
    portfolio_report = storage.load_portfolio_backtest_report()
    if not portfolio_report:
        print("未找到 data/portfolio_backtest_report.json，请先运行 python3 main.py portfolio-backtest --start-date 2018-01-01")
        return 1
    dca_report = storage.load_dca_strategy_report()
    if not dca_report:
        print("未找到 data/dca_strategy_report.json，请先运行 python3 main.py dca-strategy-lab --preset quick")
        return 1
    workers = args.workers or default_optimizer_workers()
    if workers <= 0:
        print("--workers 必须大于 0")
        return 1
    report = run_portfolio_constraint_optimizer(
        portfolio_report,
        dca_report,
        preset=args.preset,
        workers=workers,
    )
    storage.save_portfolio_optimize_report(report)
    print("组合约束优化完成，报告已写入 data/portfolio_optimize_report.json")
    print(summarize_portfolio_optimize_report(report))
    return 0


def show_portfolio_optimize_report(args):
    storage = Storage(BASE_DIR)
    report = storage.load_portfolio_optimize_report()
    if not report:
        print("暂无组合约束优化报告，请先运行 python3 main.py portfolio-optimize --preset quick。")
        return 0
    print(summarize_portfolio_optimize_report(report))
    return 0


def run_portfolio_optimize_continuous_command(args):
    storage = Storage(BASE_DIR)
    portfolio_report = storage.load_portfolio_backtest_report()
    if not portfolio_report:
        print("未找到 data/portfolio_backtest_report.json，请先运行 python3 main.py portfolio-backtest --start-date 2018-01-01")
        return 1
    dca_report = storage.load_dca_strategy_report()
    if not dca_report:
        print("未找到 data/dca_strategy_report.json，请先运行 python3 main.py dca-strategy-lab --preset quick")
        return 1
    discrete_report = storage.load_portfolio_optimize_report()
    if not discrete_report:
        print("未找到 data/portfolio_optimize_report.json，请先运行 python3 main.py portfolio-optimize --preset quick")
        return 1
    report = run_portfolio_continuous_optimizer(
        portfolio_report,
        dca_report,
        discrete_report=discrete_report,
        preset=args.preset,
        seed=args.seed,
    )
    storage.save_portfolio_optimize_continuous_report(report)
    print("连续组合优化完成，报告已写入 data/portfolio_optimize_continuous_report.json")
    print(summarize_portfolio_continuous_report(report))
    return 0


def show_portfolio_optimize_continuous_report(args):
    storage = Storage(BASE_DIR)
    report = storage.load_portfolio_optimize_continuous_report()
    if not report:
        print("暂无连续组合优化报告，请先运行 python3 main.py portfolio-optimize-continuous --preset quick。")
        return 0
    print(summarize_portfolio_continuous_report(report))
    return 0


def _load_asset_audit_reports(storage, portfolio_report):
    reports = {}
    for asset in portfolio_report.get("assets", []):
        asset_id = asset.get("asset_id")
        if not asset_id:
            continue
        report = storage.load_asset_dca_audit_report(asset_id)
        if report:
            reports[asset_id] = report
    return reports


def run_strategy_lab_command(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    portfolio_config = config.get("portfolio_backtest", {})
    if not portfolio_config.get("enabled", True):
        print("组合回测未启用，请在 config.yaml 中设置 portfolio_backtest.enabled = true。")
        return 1

    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    histories, warnings = collect_portfolio_histories(portfolio_config, provider)
    report = run_strategy_lab(config, histories)
    report["warnings"] = [*report.get("warnings", []), *warnings]
    storage.save_strategy_lab_report(report)
    print("Strategy Lab 完成，报告已写入 data/strategy_lab_report.json")
    print(summarize_strategy_lab_report(report))
    return 0


def show_strategy_lab_report(args):
    storage = Storage(BASE_DIR)
    report = storage.load_strategy_lab_report()
    if not report:
        print("暂无 Strategy Lab 报告，请先运行 python3 main.py strategy-lab。")
        return 0
    print(summarize_strategy_lab_report(report))
    return 0


def run_take_profit_backtest(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    portfolio_config = config.get("portfolio_backtest", {})
    if args.start_date or args.end_date:
        take_profit_config = config.setdefault("take_profit_backtest", {})
        if args.start_date:
            take_profit_config["start_date"] = args.start_date
        if args.end_date:
            take_profit_config["end_date"] = args.end_date

    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    nasdaq_asset = _find_portfolio_asset(portfolio_config, "NASDAQ100")
    fund_code = nasdaq_asset.get("representative_fund", "270042")
    nav_data = provider.get_full_history(fund_code)
    report = TakeProfitBacktester(config).run(nav_data["history"])
    report["warnings"] = nav_data.get("warnings", [])
    storage.save_take_profit_report(report)
    print("保守阶梯止盈回测完成，报告已写入 data/take_profit_report.json")
    print(summarize_take_profit_report(report))
    return 0


def show_take_profit_report(args):
    storage = Storage(BASE_DIR)
    report = storage.load_take_profit_report()
    if not report:
        print("暂无止盈回测报告，请先运行 python3 main.py take-profit-backtest。")
        return 0
    print(summarize_take_profit_report(report))
    return 0


def run_risk_compare_command(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    if args.start_date or args.end_date:
        take_profit_config = config.setdefault("take_profit_backtest", {})
        if args.start_date:
            take_profit_config["start_date"] = args.start_date
        if args.end_date:
            take_profit_config["end_date"] = args.end_date

    portfolio_config = config.get("portfolio_backtest", {})
    nasdaq_asset = _find_portfolio_asset(portfolio_config, "NASDAQ100")
    fund_code = nasdaq_asset.get("representative_fund", "270042")
    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    nav_data = provider.get_full_history(fund_code)
    report = run_risk_compare(config, nav_data["history"])
    report["warnings"] = nav_data.get("warnings", [])
    storage.save_risk_compare_report(report)
    print("止盈策略风险对比完成，报告已写入 data/risk_compare_report.json")
    print(summarize_risk_compare_report(report))
    return 0


def show_risk_compare_report(args):
    storage = Storage(BASE_DIR)
    report = storage.load_risk_compare_report()
    if not report:
        print("暂无风险对比报告，请先运行 python3 main.py risk-compare。")
        return 0
    print(summarize_risk_compare_report(report))
    return 0


def run_take_profit_optimizer_command(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    if args.start_date or args.end_date:
        take_profit_config = config.setdefault("take_profit_backtest", {})
        if args.start_date:
            take_profit_config["start_date"] = args.start_date
        if args.end_date:
            take_profit_config["end_date"] = args.end_date

    portfolio_config = config.get("portfolio_backtest", {})
    nasdaq_asset = _find_portfolio_asset(portfolio_config, "NASDAQ100")
    fund_code = nasdaq_asset.get("representative_fund", "270042")
    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    nav_data = provider.get_full_history(fund_code)
    all_combinations = generate_take_profit_combinations(args.preset)
    if args.max_combinations is not None and args.max_combinations <= 0:
        print("--max-combinations 必须大于 0")
        return 1
    combinations = all_combinations[: args.max_combinations] if args.max_combinations else all_combinations
    workers = args.workers or default_worker_count()
    if workers <= 0:
        print("--workers 必须大于 0")
        return 1

    print(f"preset：{args.preset}")
    print(f"总组合数：{len(all_combinations)}")
    print(f"本次测试组合数：{len(combinations)}")
    print(f"workers：{workers}")

    progress_interval = max(1, min(100, len(combinations) // 20 or 1))

    def show_progress(completed, total, elapsed, eta):
        if completed != total and completed % progress_interval != 0:
            return
        eta_text = _format_seconds(eta) if eta is not None else "N/A"
        print(
            f"进度：{completed}/{total} | 已耗时：{_format_seconds(elapsed)} | "
            f"预计剩余：{eta_text}",
            flush=True,
        )

    try:
        report = run_take_profit_optimizer(
            config,
            nav_data["history"],
            combinations=combinations,
            workers=workers,
            preset=args.preset,
            planned_count=len(all_combinations),
            progress_callback=show_progress,
            partial_report_path=BASE_DIR / "data" / "take_profit_optimizer_partial.json",
        )
    except KeyboardInterrupt:
        print("\n已中断，partial report 已尽量保存到 data/take_profit_optimizer_partial.json")
        return 130
    report["warnings"] = nav_data.get("warnings", [])
    storage.save_take_profit_optimizer_report(report)
    print("阶梯止盈档位优化完成，报告已写入 data/take_profit_optimizer_report.json")
    print(summarize_take_profit_optimizer_report(report))
    return 0


def show_take_profit_optimizer_report(args):
    storage = Storage(BASE_DIR)
    report = storage.load_take_profit_optimizer_report()
    if not report:
        print("暂无止盈优化报告，请先运行 python3 main.py take-profit-optimizer。")
        return 0
    print(summarize_take_profit_optimizer_report(report))
    return 0


def _format_seconds(seconds):
    seconds = max(0, int(seconds or 0))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{sec:02d}s"
    if minutes:
        return f"{minutes}m{sec:02d}s"
    return f"{sec}s"


def _find_portfolio_asset(portfolio_config, asset_id):
    return next(
        (asset for asset in portfolio_config.get("assets", []) if asset.get("asset_id") == asset_id),
        {},
    )


def run_scenarios(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    fund_histories, warnings = collect_backtest_histories(config, provider)
    report = run_backtest_scenarios(config, fund_histories)
    report["warnings"] = warnings
    storage.save_scenarios_report(report)
    print("多参数回测完成，报告已写入 data/scenarios_report.json")
    print(summarize_scenarios_report(report))
    return 0


def show_scenarios_returns(args):
    storage = Storage(BASE_DIR)
    report = storage.load_scenarios_report()
    if not report:
        print("暂无场景回测报告，请先运行 python3 main.py backtest-scenarios。")
        return 0
    print(summarize_scenarios_returns(report))
    return 0


def run_backtest_plot(args):
    report_path = _resolve_plot_report_path(args.source)
    if not report_path.exists():
        print(f"未找到回测报告：{report_path.name}。请先运行 backtest 或 backtest-scenarios。")
        return 1

    try:
        scenario_id = None if args.all else args.scenario
        plots = plot_report_file(report_path, BASE_DIR / args.output_dir, scenario_id=scenario_id)
    except ValueError as exc:
        print(str(exc))
        return 1
    except ImportError:
        print("缺少 matplotlib。请先运行：python3 -m pip install matplotlib")
        return 1

    if not plots:
        print("没有可绘制的数据。请重新运行 backtest 或 backtest-scenarios 生成包含 series 的报告。")
        return 1

    print(f"已生成 {len(plots)} 张图表，输出目录：{args.output_dir}")
    for plot in plots:
        print(plot["path"])
    return 0


def _resolve_plot_report_path(source):
    scenarios_path = BASE_DIR / "data" / "scenarios_report.json"
    backtest_path = BASE_DIR / "data" / "backtest_report.json"
    if source == "scenarios":
        return scenarios_path
    if source == "backtest":
        return backtest_path
    return scenarios_path if scenarios_path.exists() else backtest_path


def parse_args():
    parser = argparse.ArgumentParser(description="基金补仓管家 CLI")
    parser.add_argument("--config", default="config.yaml", help="配置文件名")
    parser.add_argument("--nav-file", default="nav_data.json", help="本地净值数据文件名")
    subparsers = parser.add_subparsers(dest="command")

    monitor_parser = subparsers.add_parser("run", help="运行每日补仓检查")
    monitor_parser.set_defaults(func=run_monitor)

    confirm_parser = subparsers.add_parser("confirm", help="确认某档补仓已执行")
    confirm_parser.add_argument("fund", help="基金代码或名称")
    confirm_parser.add_argument("level", type=int, choices=[10, 15, 20], help="补仓档位")
    confirm_parser.add_argument("--amount", type=int, help="实际执行金额，默认使用系统建议金额")
    confirm_parser.add_argument("--date", default=date.today().isoformat(), help="执行日期")
    confirm_parser.set_defaults(func=confirm_transaction)

    cash_parser = subparsers.add_parser("set-cash", help="设置子弹仓余额")
    cash_parser.add_argument("amount", type=int, help="新的子弹仓余额")
    cash_parser.set_defaults(func=set_cash)

    tx_parser = subparsers.add_parser("transactions", help="查看执行日志")
    tx_parser.set_defaults(func=show_transactions)

    logs_parser = subparsers.add_parser("logs", help="查看最近10条每日检查日志")
    logs_parser.set_defaults(func=show_daily_logs)

    backtest_parser = subparsers.add_parser("backtest", help="运行历史回测")
    backtest_parser.set_defaults(func=run_backtest)

    backtest_report_parser = subparsers.add_parser("backtest-report", help="查看最近一次回测摘要")
    backtest_report_parser.set_defaults(func=show_backtest_report)

    backtest_return_parser = subparsers.add_parser("backtest-return", help="查看最近一次回测收益估算")
    backtest_return_parser.set_defaults(func=show_backtest_returns)

    asset_backtest_parser = subparsers.add_parser("asset-backtest", help="运行资产级历史回测")
    asset_backtest_parser.set_defaults(func=run_asset_backtest)

    asset_backtest_report_parser = subparsers.add_parser("asset-backtest-report", help="查看最近一次资产级回测摘要")
    asset_backtest_report_parser.set_defaults(func=show_asset_backtest_report)

    portfolio_backtest_parser = subparsers.add_parser("portfolio-backtest", help="运行组合级定投加补仓回测")
    portfolio_backtest_parser.add_argument("--start-date", help="自定义组合回测开始日期，格式 YYYY-MM-DD")
    portfolio_backtest_parser.add_argument("--end-date", help="自定义组合回测结束日期，格式 YYYY-MM-DD")
    portfolio_backtest_parser.set_defaults(func=run_portfolio_backtest)

    fund_check_parser = subparsers.add_parser("fund-check", help="检查组合配置中代表基金的净值覆盖")
    fund_check_parser.set_defaults(func=run_fund_check_command)

    asset_dca_audit_parser = subparsers.add_parser("asset-dca-audit", help="审计单个资产的定投买入和净值口径")
    asset_dca_audit_parser.add_argument("asset", help="资产 ID 或代表基金代码，例如 DIVIDEND_LOW_VOL 或 008163")
    asset_dca_audit_parser.set_defaults(func=run_asset_dca_audit_command)

    portfolio_report_parser = subparsers.add_parser("portfolio-report", help="查看最近一次组合回测摘要")
    portfolio_report_parser.set_defaults(func=show_portfolio_report)

    contribution_report_parser = subparsers.add_parser("contribution-report", help="生成资产贡献分析摘要")
    contribution_report_parser.set_defaults(func=run_contribution_report_command)

    contribution_detail_parser = subparsers.add_parser("contribution-detail", help="查看资产贡献分析明细")
    contribution_detail_parser.set_defaults(func=show_contribution_detail)

    weekly_dca_parser = subparsers.add_parser("weekly-dca", help="分析周一到周五定投日差异")
    weekly_dca_parser.add_argument(
        "--source",
        choices=["backtest", "scenarios"],
        default="backtest",
        help="记录本次分析来源标签",
    )
    weekly_dca_parser.set_defaults(func=run_weekly_dca)

    dca_strategy_parser = subparsers.add_parser("dca-strategy-lab", help="比较不同动态定投策略组合")
    dca_strategy_parser.add_argument("--start-date", help="自定义 DCA 策略回测开始日期，格式 YYYY-MM-DD")
    dca_strategy_parser.add_argument("--end-date", help="自定义 DCA 策略回测结束日期，格式 YYYY-MM-DD")
    dca_strategy_parser.add_argument("--workers", type=int, help="并行进程数，默认 CPU 核心数 - 1")
    dca_strategy_parser.add_argument(
        "--preset",
        choices=["quick", "full"],
        default="quick",
        help="quick 测试少量代表组合，full 测试完整组合",
    )
    dca_strategy_parser.set_defaults(func=run_dca_strategy_lab_command)

    dca_strategy_report_parser = subparsers.add_parser("dca-strategy-report", help="查看 DCA 策略实验摘要")
    dca_strategy_report_parser.set_defaults(func=show_dca_strategy_report)

    portfolio_strategy_parser = subparsers.add_parser("portfolio-strategy-synth", help="合成组合级策略与风险预算")
    portfolio_strategy_parser.set_defaults(func=run_portfolio_strategy_synth_command)

    portfolio_strategy_report_parser = subparsers.add_parser("portfolio-strategy-report", help="查看组合策略合成摘要")
    portfolio_strategy_report_parser.set_defaults(func=show_portfolio_strategy_report)

    portfolio_optimize_parser = subparsers.add_parser("portfolio-optimize", help="运行组合约束优化")
    portfolio_optimize_parser.add_argument("--preset", choices=["quick", "full"], default="quick", help="quick 快速候选，full 使用 5 percent 步长全量候选")
    portfolio_optimize_parser.add_argument("--workers", type=int, help="并行进程数，默认 CPU 核心数 - 1")
    portfolio_optimize_parser.set_defaults(func=run_portfolio_optimize_command)

    portfolio_optimize_report_parser = subparsers.add_parser("portfolio-optimize-report", help="查看组合约束优化摘要")
    portfolio_optimize_report_parser.set_defaults(func=show_portfolio_optimize_report)

    portfolio_optimize_continuous_parser = subparsers.add_parser(
        "portfolio-optimize-continuous", help="运行连续组合权重优化"
    )
    portfolio_optimize_continuous_parser.add_argument(
        "--preset", choices=["quick", "full"], default="quick", help="quick 快速优化，full 增加迭代次数"
    )
    portfolio_optimize_continuous_parser.add_argument("--seed", type=int, default=42, help="固定随机种子，保证结果可复现")
    portfolio_optimize_continuous_parser.set_defaults(func=run_portfolio_optimize_continuous_command)

    portfolio_optimize_continuous_report_parser = subparsers.add_parser(
        "portfolio-optimize-continuous-report", help="查看连续组合优化摘要"
    )
    portfolio_optimize_continuous_report_parser.set_defaults(func=show_portfolio_optimize_continuous_report)

    strategy_lab_parser = subparsers.add_parser("strategy-lab", help="比较不同回撤补仓档位")
    strategy_lab_parser.set_defaults(func=run_strategy_lab_command)

    strategy_lab_report_parser = subparsers.add_parser("strategy-lab-report", help="查看 Strategy Lab 排名")
    strategy_lab_report_parser.set_defaults(func=show_strategy_lab_report)

    take_profit_parser = subparsers.add_parser("take-profit-backtest", help="运行 NASDAQ100 保守阶梯止盈回测")
    take_profit_parser.add_argument("--start-date", help="自定义止盈回测开始日期，格式 YYYY-MM-DD")
    take_profit_parser.add_argument("--end-date", help="自定义止盈回测结束日期，格式 YYYY-MM-DD")
    take_profit_parser.set_defaults(func=run_take_profit_backtest)

    take_profit_report_parser = subparsers.add_parser("take-profit-report", help="查看最近一次止盈回测摘要")
    take_profit_report_parser.set_defaults(func=show_take_profit_report)

    risk_compare_parser = subparsers.add_parser("risk-compare", help="对比原始策略和阶梯止盈策略风险")
    risk_compare_parser.add_argument("--start-date", help="自定义风险对比开始日期，格式 YYYY-MM-DD")
    risk_compare_parser.add_argument("--end-date", help="自定义风险对比结束日期，格式 YYYY-MM-DD")
    risk_compare_parser.set_defaults(func=run_risk_compare_command)

    risk_compare_report_parser = subparsers.add_parser("risk-compare-report", help="查看最近一次风险对比摘要")
    risk_compare_report_parser.set_defaults(func=show_risk_compare_report)

    take_profit_optimizer_parser = subparsers.add_parser("take-profit-optimizer", help="优化 NASDAQ100 阶梯止盈档位")
    take_profit_optimizer_parser.add_argument("--start-date", help="自定义止盈优化开始日期，格式 YYYY-MM-DD")
    take_profit_optimizer_parser.add_argument("--end-date", help="自定义止盈优化结束日期，格式 YYYY-MM-DD")
    take_profit_optimizer_parser.add_argument("--workers", type=int, help="并行进程数，默认 CPU 核心数 - 1")
    take_profit_optimizer_parser.add_argument("--max-combinations", type=int, help="限制本次最多测试的组合数量")
    take_profit_optimizer_parser.add_argument(
        "--preset",
        choices=["quick", "full"],
        default="quick",
        help="quick 测试少量代表组合，full 测试完整组合",
    )
    take_profit_optimizer_parser.set_defaults(func=run_take_profit_optimizer_command)

    take_profit_optimizer_report_parser = subparsers.add_parser(
        "take-profit-optimizer-report", help="查看最近一次止盈优化摘要"
    )
    take_profit_optimizer_report_parser.set_defaults(func=show_take_profit_optimizer_report)

    scenarios_parser = subparsers.add_parser("backtest-scenarios", help="运行多参数回测场景")
    scenarios_parser.set_defaults(func=run_scenarios)

    scenarios_return_parser = subparsers.add_parser("scenarios-return", help="查看多参数场景收益估算")
    scenarios_return_parser.set_defaults(func=show_scenarios_returns)

    plot_parser = subparsers.add_parser("backtest-plot", help="生成回测可视化图表")
    plot_parser.add_argument(
        "--source",
        choices=["auto", "backtest", "scenarios"],
        default="auto",
        help="选择读取 data/backtest_report.json 或 data/scenarios_report.json",
    )
    scenario_group = plot_parser.add_mutually_exclusive_group()
    scenario_group.add_argument("--scenario", help="只绘制单个场景，例如 S001")
    scenario_group.add_argument("--all", action="store_true", help="绘制全部场景")
    plot_parser.add_argument("--output-dir", default="reports/backtest_plots", help="图表输出目录")
    plot_parser.set_defaults(func=run_backtest_plot)

    parser.set_defaults(func=run_monitor)
    return parser.parse_args()


def main():
    args = parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
