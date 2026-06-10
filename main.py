import argparse
from datetime import date
from pathlib import Path

from backtest import (
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
from data_provider import NavDataProvider
from draw_backtest import plot_report_file
from email_notifier import send_daily_email
from notifier import format_daily_logs, format_report, format_transactions
from storage import Storage
from strategy import DrawdownStrategy
from strategy_lab import run_strategy_lab, summarize_strategy_lab_report
from weekly_dca_analysis import run_weekly_dca_analysis, summarize_weekly_dca_analysis


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
    print("回测完成，报告已写入 backtest_report.json")
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
    print("资产级回测完成，报告已写入 asset_backtest_report.json")
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

    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    histories, warnings = collect_portfolio_histories(portfolio_config, provider)
    report = PortfolioBacktester(config).run(histories)
    report["warnings"] = [*report.get("warnings", []), *warnings]
    storage.save_portfolio_backtest_report(report)
    print("组合回测完成，报告已写入 portfolio_backtest_report.json")
    print(summarize_portfolio_backtest_report(report))
    return 0


def collect_portfolio_histories(portfolio_config, provider):
    histories = {}
    warnings = []
    for asset in portfolio_config.get("assets", []):
        fund_code = asset.get("representative_fund", "")
        if not fund_code or "请先" in fund_code:
            warnings.append(f"{asset.get('asset_id')} 代表基金为配置占位，已跳过。")
            continue
        if fund_code in histories:
            continue
        nav_data = provider.get_full_history(fund_code)
        if nav_data["warnings"]:
            warnings.append({"asset_id": asset.get("asset_id"), "fund_code": fund_code, "warnings": nav_data["warnings"]})
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
    print("定投周几分析完成，报告已写入 weekly_dca_analysis.json")
    print(summarize_weekly_dca_analysis(report))
    return 0


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
    print("Strategy Lab 完成，报告已写入 strategy_lab_report.json")
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


def run_scenarios(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    fund_histories, warnings = collect_backtest_histories(config, provider)
    report = run_backtest_scenarios(config, fund_histories)
    report["warnings"] = warnings
    storage.save_scenarios_report(report)
    print("多参数回测完成，报告已写入 scenarios_report.json")
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
    scenarios_path = BASE_DIR / "scenarios_report.json"
    backtest_path = BASE_DIR / "backtest_report.json"
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
    portfolio_backtest_parser.set_defaults(func=run_portfolio_backtest)

    portfolio_report_parser = subparsers.add_parser("portfolio-report", help="查看最近一次组合回测摘要")
    portfolio_report_parser.set_defaults(func=show_portfolio_report)

    weekly_dca_parser = subparsers.add_parser("weekly-dca", help="分析周一到周五定投日差异")
    weekly_dca_parser.add_argument(
        "--source",
        choices=["backtest", "scenarios"],
        default="backtest",
        help="记录本次分析来源标签",
    )
    weekly_dca_parser.set_defaults(func=run_weekly_dca)

    strategy_lab_parser = subparsers.add_parser("strategy-lab", help="比较不同回撤补仓档位")
    strategy_lab_parser.set_defaults(func=run_strategy_lab_command)

    strategy_lab_report_parser = subparsers.add_parser("strategy-lab-report", help="查看 Strategy Lab 排名")
    strategy_lab_report_parser.set_defaults(func=show_strategy_lab_report)

    scenarios_parser = subparsers.add_parser("backtest-scenarios", help="运行多参数回测场景")
    scenarios_parser.set_defaults(func=run_scenarios)

    scenarios_return_parser = subparsers.add_parser("scenarios-return", help="查看多参数场景收益估算")
    scenarios_return_parser.set_defaults(func=show_scenarios_returns)

    plot_parser = subparsers.add_parser("backtest-plot", help="生成回测可视化图表")
    plot_parser.add_argument(
        "--source",
        choices=["auto", "backtest", "scenarios"],
        default="auto",
        help="选择读取 backtest_report.json 或 scenarios_report.json",
    )
    scenario_group = plot_parser.add_mutually_exclusive_group()
    scenario_group.add_argument("--scenario", help="只绘制单个场景，例如 S001")
    scenario_group.add_argument("--all", action="store_true", help="绘制全部场景")
    plot_parser.add_argument("--output-dir", default="backtest_plots", help="图表输出目录")
    plot_parser.set_defaults(func=run_backtest_plot)

    parser.set_defaults(func=run_monitor)
    return parser.parse_args()


def main():
    args = parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
