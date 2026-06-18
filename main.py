import argparse
import json
from contextlib import redirect_stdout
from datetime import date
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import webbrowser

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
from drawdownguard.committee_report import build_committee_report
from drawdownguard.config_manager import ConfigManager
from drawdownguard.daily_workflow import (
    build_network_debug_report,
    format_daily_summary,
    proxy_environment,
    run_daily_workflow,
)
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
from drawdownguard.interactive_control import run_interactive_control
from drawdownguard.nav_cache import NavCache
from drawdownguard.news_intelligence import (
    add_news_source,
    analyze_news,
    ensure_news_sources,
    fetch_news_from_sources,
    import_news,
    set_news_source_enabled,
    summarize_news_report,
    summarize_news_sources,
)
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
from drawdownguard.quant_signal import run_quant_signal, summarize_quant_signal_report
from drawdownguard.real_config import (
    run_policy_checks,
    summarize_dca_report,
    summarize_holdings_report,
    summarize_policy_check,
    summarize_profile,
)
from drawdownguard.rebalance_advisor import build_rebalance_advice, summarize_rebalance_advice
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
from drawdownguard.watchlist import (
    add_watchlist_fund,
    analyze_all_watchlist,
    analyze_watchlist_fund,
    compact_watchlist_analysis,
    promote_watchlist_fund,
    remove_watchlist_fund,
    summarize_watchlist,
    summarize_watchlist_analysis,
)


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
        "cache_used": nav_data.get("cache_used", False),
        "cache_stale": nav_data.get("cache_stale", False),
        "cache_last_updated": nav_data.get("cache_last_updated"),
        "cache_status": nav_data.get("cache_status"),
        "skipped": True,
        "status": "净值数据缺失，已跳过",
        "suggested_amounts": {},
        "pending_levels": {},
    }


def run_monitor_execution(args, emit=True):
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
            _attach_nav_metadata(result, nav_data)
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
    if emit:
        print(report)
    email_status = send_daily_email(config, results)
    if emit and email_status.get("warning"):
        print(f"警告：{email_status['warning']}")
    return {
        "code": 0,
        "results": results,
        "report": report,
        "email_status": email_status,
        "provider_class": provider.__class__.__name__,
    }


def run_monitor(args):
    return run_monitor_execution(args, emit=True)["code"]


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
                "cache_used": result.get("cache_used", False),
                "cache_stale": result.get("cache_stale", False),
                "cache_last_updated": result.get("cache_last_updated"),
            }
        )
    return entries


def _attach_nav_metadata(result, nav_data):
    result["cache_used"] = nav_data.get("cache_used", False)
    result["cache_stale"] = nav_data.get("cache_stale", False)
    result["cache_last_updated"] = nav_data.get("cache_last_updated")
    result["cache_status"] = nav_data.get("cache_status")


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


def show_profile_report(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    print(summarize_profile(config))
    return 0


def show_holdings_report(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    print(summarize_holdings_report(config))
    return 0


def show_dca_report(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    print(summarize_dca_report(config))
    return 0


def run_policy_check_command(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    report = run_policy_checks(config)
    print(summarize_policy_check(report))
    return 0 if report.get("passed") else 1


def run_rebalance_advice_command(args):
    report = _build_and_save_rebalance_advice(args.config)
    print("再平衡建议已写入 data/rebalance_advice.json")
    print(summarize_rebalance_advice(report, detail=False))
    return 0


def show_rebalance_detail(args):
    report = _build_and_save_rebalance_advice(args.config)
    print("再平衡建议已写入 data/rebalance_advice.json")
    print(summarize_rebalance_advice(report, detail=True))
    return 0


def _build_and_save_rebalance_advice(config_file):
    storage = Storage(BASE_DIR)
    config = storage.load_config(config_file)
    report = build_rebalance_advice(
        config,
        portfolio_strategy_report=storage.load_portfolio_strategy_report(),
        portfolio_optimize_report=storage.load_portfolio_optimize_report(),
        contribution_report=storage.load_contribution_report(),
    )
    storage.save_rebalance_advice(report)
    return report


def run_committee_report_command(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    policy_report = run_policy_checks(config)
    report = build_committee_report(
        config,
        policy_check_report=policy_report,
        daily_logs=storage.load_daily_logs(),
        portfolio_backtest_report=storage.load_portfolio_backtest_report(),
        contribution_report=storage.load_contribution_report(),
        rebalance_advice=storage.load_rebalance_advice(),
        daily_run_report=storage.load_daily_run_report(),
        quant_signal_report=storage.load_quant_signal_report(),
        watchlist_report=storage.load_watchlist_analysis_report(),
        watchlist_funds=storage.load_watchlist_funds(),
        news_report=storage.load_news_analysis_report(),
        plain=args.plain,
    )
    storage.save_committee_report(report)
    print("投委会报告已写入 data/committee_report.md 和 data/committee_report.json")
    print(report["markdown"])
    return 0


def show_cache_status(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    cache = NavCache(BASE_DIR, config)
    report = cache.status_report()
    print(_format_cache_status(report))
    return 0


def clear_cache_command(args):
    if not args.yes:
        print("这是清空本地净值缓存操作。请追加 --yes 确认执行：python3 main.py cache-clear --yes")
        return 1
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    cache = NavCache(BASE_DIR, config)
    cache.clear()
    print("已清空 data/nav_cache.json")
    return 0


def _policy_check_after_change(config_filename="config.yaml"):
    storage = Storage(BASE_DIR)
    config = storage.load_config(config_filename)
    report = run_policy_checks(config)
    print(summarize_policy_check(report))
    return report


def _finish_config_change(result, config_filename="config.yaml"):
    manager = ConfigManager(BASE_DIR)
    if result.get("dry_run"):
        print("DRY RUN：不会写入任何配置。")
        print(json.dumps({key: result.get(key) for key in ("operation", "target", "before", "after")}, ensure_ascii=False, indent=2))
        return 0
    policy_report = _policy_check_after_change(config_filename)
    manager.log_change(
        result["operation"],
        result["target"],
        result.get("before"),
        result.get("after"),
        result.get("backup_path"),
        {"passed": policy_report.get("passed"), "issues": policy_report.get("issues", [])},
    )
    print(f"配置已更新，备份目录：{result.get('backup_path')}")
    if not policy_report.get("passed"):
        print("policy-check 未通过。可执行 python3 main.py config-rollback --latest 回滚。")
        return 1
    print("下一步建议：python3 main.py daily --quick")
    return 0


def cash_update_command(args):
    result = ConfigManager(BASE_DIR).update_cash(args.amount, dry_run=args.dry_run)
    return _finish_config_change(result, args.config)


def holding_update_command(args):
    result = ConfigManager(BASE_DIR).update_holding(args.fund_code, args.amount, dry_run=args.dry_run)
    return _finish_config_change(result, args.config)


def holding_add_command(args):
    result = ConfigManager(BASE_DIR).add_holding(
        args.fund_code,
        args.name,
        args.asset_id,
        args.role,
        args.amount,
        nav_mode=args.nav_mode,
        dry_run=args.dry_run,
    )
    return _finish_config_change(result, args.config)


def holding_remove_command(args):
    result = ConfigManager(BASE_DIR).remove_holding(args.fund_code, dry_run=args.dry_run)
    return _finish_config_change(result, args.config)


def dca_add_command(args):
    result = ConfigManager(BASE_DIR).add_dca(
        args.fund_code,
        args.amount,
        args.frequency,
        weekday=args.weekday,
        dry_run=args.dry_run,
    )
    return _finish_config_change(result, args.config)


def dca_update_command(args):
    result = ConfigManager(BASE_DIR).update_dca(args.fund_code, args.amount, dry_run=args.dry_run)
    return _finish_config_change(result, args.config)


def dca_pause_command(args):
    result = ConfigManager(BASE_DIR).set_dca_status(args.fund_code, "paused", dry_run=args.dry_run)
    return _finish_config_change(result, args.config)


def dca_resume_command(args):
    result = ConfigManager(BASE_DIR).set_dca_status(args.fund_code, "active", dry_run=args.dry_run)
    return _finish_config_change(result, args.config)


def config_backup_command(args):
    path = ConfigManager(BASE_DIR).backup()
    print(f"配置备份已创建：{path}")
    return 0


def config_backup_list_command(args):
    backups = ConfigManager(BASE_DIR).list_backups()
    if not backups:
        print("暂无配置备份。")
        return 0
    for path in backups[-20:]:
        print(path)
    return 0


def config_rollback_command(args):
    if not args.latest:
        print("当前仅支持 --latest 回滚。")
        return 1
    manager = ConfigManager(BASE_DIR)
    try:
        path = manager.rollback_latest()
    except ValueError as exc:
        print(str(exc))
        return 1
    policy_report = _policy_check_after_change(args.config)
    manager.log_change(
        "config-rollback",
        "latest",
        None,
        {"backup_path": str(path)},
        str(path),
        {"passed": policy_report.get("passed"), "issues": policy_report.get("issues", [])},
    )
    print(f"已回滚到：{path}")
    return 0 if policy_report.get("passed") else 1


def config_change_log_command(args):
    logs = ConfigManager(BASE_DIR).recent_logs(limit=20)
    if not logs:
        print("暂无配置修改记录。")
        return 0
    for item in logs:
        print(f"{item.get('timestamp')} | {item.get('operation')} | {item.get('target')} | passed={item.get('policy_check_result', {}).get('passed')}")
    return 0


def interactive_command(args):
    actions = {
        "profile": show_profile_report,
        "holdings": show_holdings_report,
        "committee": run_committee_report_command,
        "daily": run_daily_command,
        "cash_update": cash_update_command,
        "holding_update": holding_update_command,
        "watchlist_add": watchlist_add_command,
        "watchlist_remove": watchlist_remove_command,
        "dca_add": dca_add_command,
        "dca_update": dca_update_command,
        "dca_pause": dca_pause_command,
        "dca_resume": dca_resume_command,
        "policy": run_policy_check_command,
        "backup": config_backup_command,
        "rollback": config_rollback_command,
    }
    return run_interactive_control(actions, args)


def _format_cache_status(report):
    lines = ["本地净值缓存状态"]
    lines.append(f"缓存文件存在：{report.get('exists')}")
    lines.append(f"缓存路径：{report.get('path')}")
    lines.append(f"缓存启用：{report.get('enabled')}")
    lines.append(f"缓存基金数量：{report.get('fund_count', 0)}")
    for warning in report.get("warnings", []):
        lines.append(f"提示：{warning}")
    for item in report.get("items", []):
        lines.append(
            f"- {item.get('fund_code')} | {item.get('fund_name')} | {item.get('nav_mode')} | "
            f"last_updated {item.get('last_updated')} | history {item.get('history_count')} | "
            f"latest {item.get('latest_nav_date')} | run {item.get('cache_status_for_run')} | "
            f"backtest {item.get('cache_status_for_backtest')} | "
            f"满足250条 {item.get('meets_min_history_for_run')}"
        )
    return "\n".join(lines)


def run_daily_command(args):
    storage = Storage(BASE_DIR)
    steps = _daily_steps(args)
    if args.debug_network:
        with proxy_environment(args.clean_proxy):
            _print_network_debug()
    report = run_daily_workflow(
        steps,
        save_report=storage.save_daily_run_report,
        final_report="data/committee_report.md",
        conclusion_builder=_build_daily_conclusion,
        clean_proxy=args.clean_proxy,
    )
    print(format_daily_summary(report))
    if args.open_report:
        _try_open_report(BASE_DIR / "data" / "committee_report.md")
    return 0 if report["status"] != "failed" else 1


def _daily_steps(args):
    return [
        {"name": "policy-check", "func": lambda: _daily_policy_check(args)},
        {"name": "run", "func": lambda: _daily_run(args)},
        {
            "name": "portfolio-backtest",
            "func": lambda: _daily_portfolio_backtest(args),
            "skip": args.quick or args.skip_backtest,
            "skip_message": "daily quick/skip-backtest 模式已跳过组合回测。",
        },
        {
            "name": "contribution-report",
            "func": _daily_contribution_report,
            "skip": args.quick,
            "skip_message": "daily quick 模式已跳过资产贡献分析。",
        },
        {
            "name": "quant-signal",
            "func": lambda: _daily_quant_signal(args),
            "skip": args.skip_quant,
            "skip_message": "daily --skip-quant 已跳过量化信号刷新，committee-report 将使用已有 quant_signal_report.json。",
        },
        {
            "name": "watchlist-analyze",
            "func": lambda: _daily_watchlist_analyze(args),
            "skip": not args.include_watchlist,
            "skip_message": "daily 默认不分析观察池；如需刷新请使用 --include-watchlist。",
        },
        {
            "name": "news-fetch",
            "func": lambda: _daily_news_fetch(args),
            "skip": not args.include_news,
            "skip_message": "daily 默认不抓取新闻；如需刷新请使用 --include-news。",
        },
        {
            "name": "news-analyze",
            "func": lambda: _daily_news_analyze(args),
            "skip": not args.include_news,
            "skip_message": "daily 默认不分析新闻；如需刷新请使用 --include-news。",
        },
        {"name": "rebalance-advice", "func": lambda: _daily_rebalance_advice(args)},
        {"name": "committee-report", "func": lambda: _daily_committee_report(args)},
    ]


def _daily_policy_check(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    report = run_policy_checks(config)
    if report.get("passed"):
        return {"status": "success", "message": "配置检查通过。"}
    return {
        "status": "failed",
        "message": "配置检查存在问题。",
        "errors": [item.get("message", "") for item in report.get("issues", [])],
    }


def _daily_run(args):
    execution = run_monitor_execution(args, emit=False)
    infos, warnings = _run_result_messages(execution.get("results", []))
    cache_meta = _run_cache_meta(execution.get("results", []))
    if cache_meta["cache_used"] and not cache_meta["cache_stale"]:
        infos.append("使用缓存净值")
    if execution.get("code", 1) != 0:
        return {
            "status": "failed",
            "message": "每日补仓检查失败。",
            "warnings": warnings,
            "result_source": "fresh_execution",
            **cache_meta,
        }
    if warnings or cache_meta["cache_stale"]:
        return {
            "status": "warning",
            "message": "每日补仓检查完成，但存在数据 warning。",
            "warnings": warnings,
            "infos": infos,
            "result_source": "fresh_execution",
            "provider_class": execution.get("provider_class"),
            **cache_meta,
        }
    return {
        "status": "success",
        "message": "每日补仓检查完成。",
        "infos": infos,
        "result_source": "fresh_execution",
        "provider_class": execution.get("provider_class"),
        **cache_meta,
    }


def _daily_portfolio_backtest(args):
    step_args = SimpleNamespace(
        config=args.config,
        nav_file=args.nav_file,
        start_date=args.start_date or "2018-01-01",
        end_date=None,
    )
    code, output = _capture_command_output(run_portfolio_backtest, step_args)
    storage = Storage(BASE_DIR)
    report = storage.load_portfolio_backtest_report()
    infos, warnings = _split_portfolio_messages(report.get("warnings", []))
    if code != 0:
        return {"status": "failed", "message": "组合回测失败。", "warnings": warnings, "infos": infos}
    if warnings or "净值数据缺失" in output:
        return {"status": "warning", "message": "组合回测完成，但存在数据 warning。", "warnings": warnings or ["组合回测存在数据 warning。"], "infos": infos}
    return {"status": "success", "message": "组合回测完成。", "infos": infos}


def _daily_contribution_report():
    storage = Storage(BASE_DIR)
    portfolio_report = storage.load_portfolio_backtest_report()
    if not portfolio_report:
        return {
            "status": "warning",
            "message": "缺少 portfolio_backtest_report.json，已跳过资产贡献分析。",
            "warnings": ["请先运行 portfolio-backtest 或 daily --start-date 2018-01-01。"],
        }
    report = run_contribution_analysis(portfolio_report)
    storage.save_contribution_report(report)
    return {"status": "success", "message": "资产贡献分析完成。"}


def _daily_quant_signal(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    report = run_quant_signal(config, provider)
    storage.save_quant_signal_report(report)
    available = [asset for asset in report.get("assets", []) if asset.get("status") == "available"]
    if not available:
        return {
            "status": "warning",
            "message": "量化信号无法生成。",
            "warnings": ["全部量化资产净值数据缺失，已保留空报告。"],
        }
    infos, warnings = _split_quant_messages(report.get("warnings", []))
    if warnings:
        return {
            "status": "warning",
            "message": "量化信号完成，但存在数据 warning。",
            "infos": infos,
            "warnings": warnings,
        }
    return {"status": "success", "message": "量化信号完成。", "infos": infos}


def _daily_watchlist_analyze(args):
    storage = Storage(BASE_DIR)
    watchlist = storage.load_watchlist_funds()
    if not watchlist.get("funds"):
        report = {"generated_at": date.today().isoformat(), "funds": [], "warnings": []}
        storage.save_watchlist_analysis_report(report)
        return {"status": "success", "message": "观察池为空。", "infos": ["观察池为空，已跳过分析。"]}
    config = storage.load_config(args.config)
    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    report = analyze_all_watchlist(config, provider, watchlist)
    storage.save_watchlist_analysis_report(report)
    infos, warnings = _split_quant_messages(report.get("warnings", []))
    if warnings:
        return {"status": "warning", "message": "观察池分析完成，但存在数据 warning。", "infos": infos, "warnings": warnings}
    return {"status": "success", "message": "观察池分析完成。", "infos": infos}


def _daily_news_fetch(args):
    storage = Storage(BASE_DIR)
    sources, source_infos = ensure_news_sources(storage)
    report = fetch_news_from_sources(sources, storage.load_news_cache())
    storage.save_news_cache(report)
    fetch_status = report.get("fetch_status", {})
    infos = list(source_infos) + list(fetch_status.get("infos", []))
    warnings = fetch_status.get("warnings", [])
    if warnings:
        return {"status": "warning", "message": "新闻抓取完成，但部分来源失败。", "infos": infos, "warnings": warnings}
    return {
        "status": "success",
        "message": "新闻抓取完成。",
        "infos": infos or [f"新闻抓取完成，新增 {fetch_status.get('new_count', 0)} 条。"],
    }


def _daily_news_analyze(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    report = analyze_news(storage.load_news_cache(), config, storage.load_watchlist_funds(), days=1)
    storage.save_news_analysis_report(report)
    summary = report.get("portfolio_news_summary", {})
    if not report.get("items"):
        return {
            "status": "success",
            "message": "新闻分析完成，暂无相关重要新闻。",
            "infos": ["暂无相关重要新闻。"],
            "news_relevant_count": 0,
            "news_risk_alert_level": summary.get("risk_alert_level"),
            "news_overall_tone": summary.get("overall_news_tone"),
        }
    warnings = []
    if summary.get("risk_alert_level") == "high":
        warnings.append("存在高影响负面新闻，已纳入投委会观察。")
    return {
        "status": "warning" if warnings else "success",
        "message": "新闻分析完成。",
        "warnings": warnings,
        "news_relevant_count": summary.get("relevant_news_count", 0),
        "news_risk_alert_level": summary.get("risk_alert_level"),
        "news_overall_tone": summary.get("overall_news_tone"),
    }


def _daily_rebalance_advice(args):
    _build_and_save_rebalance_advice(args.config)
    return {"status": "success", "message": "再平衡建议完成。"}


def _daily_committee_report(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    report = build_committee_report(
        config,
        policy_check_report=run_policy_checks(config),
        daily_logs=storage.load_daily_logs(),
        portfolio_backtest_report=storage.load_portfolio_backtest_report(),
        contribution_report=storage.load_contribution_report(),
        rebalance_advice=storage.load_rebalance_advice(),
        daily_run_report=storage.load_daily_run_report(),
        quant_signal_report=storage.load_quant_signal_report(),
        watchlist_report=storage.load_watchlist_analysis_report(),
        watchlist_funds=storage.load_watchlist_funds(),
        news_report=storage.load_news_analysis_report(),
    )
    storage.save_committee_report(report)
    if not (BASE_DIR / "data" / "committee_report.md").exists():
        return {"status": "failed", "message": "投委会 Markdown 报告未生成。", "errors": ["投委会 Markdown 报告未生成。"]}
    return {"status": "success", "message": "投委会报告完成。"}


def _capture_command_output(func, args):
    buffer = StringIO()
    with redirect_stdout(buffer):
        code = func(args)
    return code, buffer.getvalue()


def _latest_daily_logs(logs):
    dated = [item for item in logs if item.get("date")]
    if not dated:
        return []
    latest_date = max(item["date"] for item in dated)
    return [item for item in dated if item.get("date") == latest_date]


def _daily_log_warnings(logs):
    warnings = []
    for item in logs:
        for warning in item.get("warnings", []) or []:
            warnings.append(f"{item.get('fund_code')}: {warning}")
    return warnings


def _run_result_warnings(results):
    warnings = []
    for result in results:
        for warning in result.get("warnings", []) or []:
            warnings.append(f"{result.get('fund_code')}: {warning}")
    return warnings


def _run_result_messages(results):
    infos = []
    warnings = []
    for result in results:
        fund_code = result.get("fund_code")
        cache_used = result.get("cache_used")
        cache_stale = result.get("cache_stale")
        for warning in result.get("warnings", []) or []:
            message = f"{fund_code}: {warning}"
            if cache_used and not cache_stale and ("已切换到缓存数据" in warning or "真实净值获取失败" in warning or "单位净值获取失败" in warning):
                infos.append(message)
            else:
                warnings.append(message)
    return infos, warnings


def _run_cache_meta(results):
    cache_results = [result for result in results if result.get("cache_used")]
    last_updated = next((result.get("cache_last_updated") for result in cache_results if result.get("cache_last_updated")), None)
    return {
        "cache_used": bool(cache_results),
        "cache_stale": any(result.get("cache_stale") for result in cache_results),
        "cache_last_updated": last_updated,
    }


def _flatten_warnings(items):
    warnings = []
    for item in items:
        if isinstance(item, str):
            warnings.append(item)
            continue
        for warning in item.get("warnings", []) or []:
            warnings.append(f"{item.get('asset_id') or item.get('fund_code')}: {warning}")
    return warnings


def _split_portfolio_messages(items):
    infos = []
    warnings = []
    for item in _flatten_warnings(items):
        if _is_info_message(item):
            infos.append(item)
        else:
            warnings.append(item)
    return infos, warnings


def _split_quant_messages(items):
    infos = []
    warnings = []
    for item in items:
        text = str(item)
        if (
            "已切换到缓存数据" in text
            or "真实净值获取失败" in text
            or "累计净值获取失败" in text
            or "单位净值获取失败" in text
        ) and "数据不足" not in text:
            infos.append(text)
        else:
            warnings.append(text)
    return infos, warnings


def _is_info_message(message):
    return "012752 定投在资产级回测中使用代表基金 270042 净值作为 fallback" in message


def _build_daily_conclusion():
    storage = Storage(BASE_DIR)
    logs = _latest_daily_logs(storage.load_daily_logs())
    rebalance = storage.load_rebalance_advice()
    quant = storage.load_quant_signal_report()
    news = storage.load_news_analysis_report()
    triggered = any(bool(item.get("suggestions")) for item in logs)
    conclusion = rebalance.get("conclusion", {})
    quant_summary = quant.get("portfolio_quant_summary", {})
    news_summary = news.get("portfolio_news_summary", {})
    return {
        "drawdown_triggered": triggered,
        "needs_immediate_rebalance": conclusion.get("needs_immediate_rebalance"),
        "future_dca_bias": conclusion.get("future_dca_bias"),
        "quant_market_regime": quant_summary.get("market_regime"),
        "average_quant_score": quant_summary.get("average_quant_score"),
        "core_asset_score": quant_summary.get("core_asset_score"),
        "news_relevant_count": news_summary.get("relevant_news_count"),
        "news_risk_alert_level": news_summary.get("risk_alert_level"),
        "news_overall_tone": news_summary.get("overall_news_tone"),
    }


def _print_network_debug():
    debug = build_network_debug_report(provider_name="NavDataProvider")
    print("Daily network debug")
    print(f"http_proxy: {debug.get('http_proxy')}")
    print(f"https_proxy: {debug.get('https_proxy')}")
    print(f"no_proxy: {debug.get('no_proxy')}")
    print(f"socket.getaddrinfo(fund.eastmoney.com, 443): {debug.get('fund_eastmoney_getaddrinfo')}")
    print(f"requests proxies: {debug.get('requests_environ_proxies')}")
    print(f"DataProvider: {debug.get('data_provider')}")
    print(f"run_call_path: {debug.get('run_call_path')}")


def _try_open_report(path):
    if not path.exists():
        print(f"报告不存在：{path}")
        return
    opened = False
    try:
        opened = webbrowser.open(path.resolve().as_uri())
    except Exception:
        opened = False
    if opened:
        print(f"已尝试打开报告：{path}")
    else:
        print(f"当前环境无法自动打开报告，请手动查看：{path}")


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


def run_quant_signal_command(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    report = run_quant_signal(config, provider)
    storage.save_quant_signal_report(report)
    print("量化信号报告已写入 data/quant_signal_report.json")
    print(summarize_quant_signal_report(report))
    return 0


def show_quant_signal_detail(args):
    storage = Storage(BASE_DIR)
    report = storage.load_quant_signal_report()
    if not report:
        print("暂无量化信号报告，请先运行 python3 main.py quant-signal。")
        return 0
    print(summarize_quant_signal_report(report, detail=True))
    return 0


def watchlist_add_command(args):
    storage = Storage(BASE_DIR)
    before = storage.load_watchlist_funds()
    try:
        updated, item = add_watchlist_fund(
            before,
            args.fund_code,
            args.name,
            role=args.role,
            reason=args.reason or "",
            nav_mode=args.nav_mode,
            notes=args.notes or "",
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    if item.get("already_exists"):
        print(f"观察池中已存在基金：{args.fund_code}，未重复添加。")
        return 0
    if args.dry_run:
        print("DRY RUN：不会写入任何配置。")
        print(json.dumps(item, ensure_ascii=False, indent=2))
        return 0
    manager = ConfigManager(BASE_DIR)
    backup_path = manager.backup()
    storage.save_watchlist_funds(updated)
    policy_report = _policy_check_after_change(args.config)
    manager.log_change(
        "watchlist-add",
        args.fund_code,
        before,
        updated,
        str(backup_path),
        {"passed": policy_report.get("passed"), "issues": policy_report.get("issues", [])},
    )
    print("观察基金已添加到 data/watchlist_funds.json")
    print(f"配置已备份：{backup_path}")
    print(f"{item['fund_code']} {item['fund_name']} | role {item['candidate_role']} | allow_dca {item['allow_dca']} | allow_drawdown_buy {item['allow_drawdown_buy']}")
    return 0 if policy_report.get("passed") else 1


def watchlist_report_command(args):
    storage = Storage(BASE_DIR)
    print(summarize_watchlist(storage.load_watchlist_funds()))
    return 0


def watchlist_analyze_command(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    watchlist = storage.load_watchlist_funds()
    provider = NavDataProvider(BASE_DIR / args.nav_file, config)
    try:
        report = analyze_watchlist_fund(
            config,
            provider,
            watchlist,
            args.fund_code,
            weekly_dca=args.weekly_dca,
            start_date=args.start_date,
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    storage.save_watchlist_fund_analysis(args.fund_code, report)
    aggregate = storage.load_watchlist_analysis_report()
    funds = [item for item in aggregate.get("funds", []) if item.get("fund", {}).get("fund_code") != args.fund_code]
    funds.append(report)
    storage.save_watchlist_analysis_report(
        {
            "generated_at": date.today().isoformat(),
            "funds": funds,
            "summary_funds": [compact_watchlist_analysis(item) for item in funds],
            "warnings": aggregate.get("warnings", []),
        }
    )
    print(f"观察基金分析已写入 data/watchlist_analysis_{args.fund_code}.json")
    print(summarize_watchlist_analysis(report))
    return 0


def watchlist_remove_command(args):
    storage = Storage(BASE_DIR)
    before = storage.load_watchlist_funds()
    try:
        updated = remove_watchlist_fund(before, args.fund_code)
    except ValueError as exc:
        print(str(exc))
        return 1
    if args.dry_run:
        print("DRY RUN：不会写入任何配置。")
        print(json.dumps({"before": before, "after": updated}, ensure_ascii=False, indent=2))
        return 0
    manager = ConfigManager(BASE_DIR)
    backup_path = manager.backup()
    storage.save_watchlist_funds(updated)
    policy_report = _policy_check_after_change(args.config)
    manager.log_change(
        "watchlist-remove",
        args.fund_code,
        before,
        updated,
        str(backup_path),
        {"passed": policy_report.get("passed"), "issues": policy_report.get("issues", [])},
    )
    print(f"已从观察池移除：{args.fund_code}")
    print(f"配置已备份：{backup_path}")
    return 0 if policy_report.get("passed") else 1


def watchlist_promote_command(args):
    storage = Storage(BASE_DIR)
    try:
        report = promote_watchlist_fund(storage.load_watchlist_funds(), args.fund_code)
    except ValueError as exc:
        print(str(exc))
        return 1
    print("观察基金转入真实持仓建议")
    print(report["message"])
    print("holding snippet:")
    print(json.dumps(report["holding_snippet"], ensure_ascii=False, indent=2))
    print("policy reminder:")
    print(json.dumps(report["policy_reminder"], ensure_ascii=False, indent=2))
    print("如你已实际买入该基金，可执行：")
    print(report["holding_add_command"])
    print("如你想设置定投，可执行：")
    print(report["dca_add_command"])
    print("promote 不会自动买入，也不会自动修改真实持仓。")
    return 0


def news_sources_command(args):
    storage = Storage(BASE_DIR)
    sources, infos = ensure_news_sources(storage)
    print(summarize_news_sources(sources))
    for info in infos:
        print(f"Info: {info}")
    return 0


def news_source_add_command(args):
    storage = Storage(BASE_DIR)
    sources, _ = ensure_news_sources(storage)
    try:
        updated = add_news_source(sources, args.name, args.type, args.url, category=args.category, enabled=not args.disabled)
    except ValueError as exc:
        print(str(exc))
        return 1
    storage.save_news_sources(updated)
    print(f"新闻源已添加：{args.name}")
    return 0


def news_source_enable_command(args):
    return _set_news_source_enabled(args.name, True)


def news_source_disable_command(args):
    return _set_news_source_enabled(args.name, False)


def _set_news_source_enabled(name, enabled):
    storage = Storage(BASE_DIR)
    sources, _ = ensure_news_sources(storage)
    try:
        updated = set_news_source_enabled(sources, name, enabled)
    except ValueError as exc:
        print(str(exc))
        return 1
    storage.save_news_sources(updated)
    print(f"新闻源已{'启用' if enabled else '禁用'}：{name}")
    return 0


def news_fetch_command(args):
    storage = Storage(BASE_DIR)
    sources, infos = ensure_news_sources(storage)
    report = fetch_news_from_sources(sources, storage.load_news_cache())
    storage.save_news_cache(report)
    status = report.get("fetch_status", {})
    print("新闻抓取完成")
    print(f"抓取数量：{status.get('fetched_count', 0)}")
    print(f"新增数量：{status.get('new_count', 0)}")
    print(f"成功来源：{', '.join(status.get('success_sources', [])) or '无'}")
    print(f"失败来源：{', '.join(status.get('failed_sources', [])) or '无'}")
    for info in infos + status.get("infos", []):
        print(f"Info: {info}")
    for warning in status.get("warnings", []):
        print(f"Warning: {warning}")
    return 0


def news_import_command(args):
    storage = Storage(BASE_DIR)
    cache, item = import_news(storage.load_news_cache(), args.title, content=args.content or "", source=args.source or "manual")
    storage.save_news_cache(cache)
    print("新闻已导入 news_cache.json")
    print(f"{item['news_id']} | {item['title']}")
    return 0


def news_analyze_command(args):
    storage = Storage(BASE_DIR)
    config = storage.load_config(args.config)
    report = analyze_news(storage.load_news_cache(), config, storage.load_watchlist_funds(), days=args.days)
    storage.save_news_analysis_report(report)
    print("新闻分析已写入 data/news_analysis_report.json")
    print(summarize_news_report(report))
    return 0


def news_report_command(args):
    storage = Storage(BASE_DIR)
    report = storage.load_news_analysis_report()
    if not report:
        print("暂无新闻分析报告，请先运行 python3 main.py news-analyze。")
        return 0
    print(summarize_news_report(report))
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
        for schedule in asset.get("dca_schedules", []):
            schedule_code = schedule.get("fund_code")
            if schedule_code and schedule_code != fund_code:
                warnings.append(
                    {
                        "asset_id": asset.get("asset_id"),
                        "fund_code": schedule_code,
                        "warnings": [
                            f"{schedule_code} 定投在资产级回测中使用代表基金 {fund_code} 净值作为 fallback。"
                        ],
                    }
                )
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

    profile_parser = subparsers.add_parser("profile-report", help="查看真实账户画像和策略配置")
    profile_parser.set_defaults(func=show_profile_report)

    holdings_parser = subparsers.add_parser("holdings-report", help="查看真实持仓明细和资产汇总")
    holdings_parser.set_defaults(func=show_holdings_report)

    policy_check_parser = subparsers.add_parser("policy-check", help="检查真实配置是否符合补仓和账户隔离规则")
    policy_check_parser.set_defaults(func=run_policy_check_command)

    rebalance_advice_parser = subparsers.add_parser("rebalance-advice", help="生成真实持仓再平衡建议")
    rebalance_advice_parser.set_defaults(func=run_rebalance_advice_command)

    rebalance_detail_parser = subparsers.add_parser("rebalance-detail", help="查看详细再平衡建议")
    rebalance_detail_parser.set_defaults(func=show_rebalance_detail)

    committee_report_parser = subparsers.add_parser("committee-report", help="生成个人投委会报告")
    committee_report_parser.add_argument("--plain", action="store_true", help="输出旧版简洁文本，不使用表格摘要和 emoji")
    committee_report_parser.set_defaults(func=run_committee_report_command)

    cache_status_parser = subparsers.add_parser("cache-status", help="查看本地净值缓存状态")
    cache_status_parser.set_defaults(func=show_cache_status)

    cache_clear_parser = subparsers.add_parser("cache-clear", help="清空本地净值缓存")
    cache_clear_parser.add_argument("--yes", action="store_true", help="确认清空 data/nav_cache.json")
    cache_clear_parser.set_defaults(func=clear_cache_command)

    interactive_parser = subparsers.add_parser("interactive", help="启动 DrawdownGuard 交互式控制中心")
    interactive_parser.set_defaults(func=interactive_command)

    cash_update_parser = subparsers.add_parser("cash-update", help="更新子弹仓金额")
    cash_update_parser.add_argument("--amount", type=float, required=True, help="新的子弹仓金额")
    cash_update_parser.add_argument("--dry-run", action="store_true", help="只预览修改，不写入文件")
    cash_update_parser.set_defaults(func=cash_update_command)

    holding_update_parser = subparsers.add_parser("holding-update", help="更新基金持仓金额")
    holding_update_parser.add_argument("fund_code", help="基金代码")
    holding_update_parser.add_argument("--amount", type=float, required=True, help="新的持仓金额")
    holding_update_parser.add_argument("--dry-run", action="store_true", help="只预览修改，不写入文件")
    holding_update_parser.set_defaults(func=holding_update_command)

    holding_add_parser = subparsers.add_parser("holding-add", help="新增真实持仓基金")
    holding_add_parser.add_argument("fund_code", help="基金代码")
    holding_add_parser.add_argument("--name", required=True, help="基金名称")
    holding_add_parser.add_argument("--asset-id", required=True, help="资产ID")
    holding_add_parser.add_argument("--role", required=True, help="资产角色")
    holding_add_parser.add_argument("--amount", type=float, required=True, help="持仓金额")
    holding_add_parser.add_argument("--nav-mode", default="unit_nav", choices=["unit_nav", "accumulated_nav"], help="净值口径")
    holding_add_parser.add_argument("--dry-run", action="store_true", help="只预览修改，不写入文件")
    holding_add_parser.set_defaults(func=holding_add_command)

    holding_remove_parser = subparsers.add_parser("holding-remove", help="删除真实持仓基金")
    holding_remove_parser.add_argument("fund_code", help="基金代码")
    holding_remove_parser.add_argument("--dry-run", action="store_true", help="只预览修改，不写入文件")
    holding_remove_parser.set_defaults(func=holding_remove_command)

    dca_report_parser = subparsers.add_parser("dca-report", help="查看 active / paused 定投计划")
    dca_report_parser.set_defaults(func=show_dca_report)

    dca_add_parser = subparsers.add_parser("dca-add", help="新增定投计划")
    dca_add_parser.add_argument("fund_code", help="基金代码")
    dca_add_parser.add_argument("--amount", type=float, required=True, help="定投金额")
    dca_add_parser.add_argument("--frequency", choices=["weekly", "monthly"], required=True, help="定投频率")
    dca_add_parser.add_argument("--weekday", choices=["mon", "tue", "wed", "thu", "fri"], help="每周定投日")
    dca_add_parser.add_argument("--dry-run", action="store_true", help="只预览修改，不写入文件")
    dca_add_parser.set_defaults(func=dca_add_command)

    dca_update_parser = subparsers.add_parser("dca-update", help="修改定投金额")
    dca_update_parser.add_argument("fund_code", help="基金代码")
    dca_update_parser.add_argument("--amount", type=float, required=True, help="新的定投金额")
    dca_update_parser.add_argument("--dry-run", action="store_true", help="只预览修改，不写入文件")
    dca_update_parser.set_defaults(func=dca_update_command)

    dca_pause_parser = subparsers.add_parser("dca-pause", help="暂停定投计划")
    dca_pause_parser.add_argument("fund_code", help="基金代码")
    dca_pause_parser.add_argument("--dry-run", action="store_true", help="只预览修改，不写入文件")
    dca_pause_parser.set_defaults(func=dca_pause_command)

    dca_resume_parser = subparsers.add_parser("dca-resume", help="恢复定投计划")
    dca_resume_parser.add_argument("fund_code", help="基金代码")
    dca_resume_parser.add_argument("--dry-run", action="store_true", help="只预览修改，不写入文件")
    dca_resume_parser.set_defaults(func=dca_resume_command)

    config_backup_parser = subparsers.add_parser("config-backup", help="备份当前真实配置")
    config_backup_parser.set_defaults(func=config_backup_command)

    config_backup_list_parser = subparsers.add_parser("config-backup-list", help="查看最近配置备份")
    config_backup_list_parser.set_defaults(func=config_backup_list_command)

    config_rollback_parser = subparsers.add_parser("config-rollback", help="回滚配置备份")
    config_rollback_parser.add_argument("--latest", action="store_true", help="回滚到最新备份")
    config_rollback_parser.set_defaults(func=config_rollback_command)

    config_change_log_parser = subparsers.add_parser("config-change-log", help="查看最近配置修改记录")
    config_change_log_parser.set_defaults(func=config_change_log_command)

    daily_parser = subparsers.add_parser("daily", help="运行一键每日工作流")
    daily_parser.add_argument("--start-date", default="2018-01-01", help="组合回测开始日期，默认 2018-01-01")
    daily_parser.add_argument("--skip-backtest", action="store_true", help="跳过组合回测，使用已有回测报告")
    daily_parser.add_argument("--quick", action="store_true", help="快速模式：跳过组合回测和资产贡献分析")
    daily_parser.add_argument("--skip-quant", action="store_true", help="跳过量化信号刷新，使用已有 quant_signal_report.json")
    daily_parser.add_argument("--include-watchlist", action="store_true", help="daily 中同步分析观察池基金")
    daily_parser.add_argument("--include-news", action="store_true", help="daily 中同步抓取并分析每日财经新闻")
    daily_parser.add_argument("--open-report", action="store_true", help="尝试打开 data/committee_report.md")
    daily_parser.add_argument("--clean-proxy", action="store_true", help="daily 执行期间临时移除代理环境变量")
    daily_parser.add_argument("--debug-network", action="store_true", help="输出 daily 网络环境和 DNS 诊断信息")
    daily_parser.set_defaults(func=run_daily_command)

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

    quant_signal_parser = subparsers.add_parser("quant-signal", help="生成资产量化信号报告")
    quant_signal_parser.set_defaults(func=run_quant_signal_command)

    quant_signal_detail_parser = subparsers.add_parser("quant-signal-detail", help="查看资产量化信号详细指标")
    quant_signal_detail_parser.set_defaults(func=show_quant_signal_detail)

    watchlist_add_parser = subparsers.add_parser("watchlist-add", help="添加基金到观察池")
    watchlist_add_parser.add_argument("fund_code", help="基金代码")
    watchlist_add_parser.add_argument("--name", required=True, help="基金名称")
    watchlist_add_parser.add_argument("--role", default="unknown", choices=["core", "satellite", "hedge", "factor", "theme", "bond", "active", "unknown"], help="候选角色")
    watchlist_add_parser.add_argument("--reason", default="", help="关注原因")
    watchlist_add_parser.add_argument("--nav-mode", default="unit_nav", choices=["unit_nav", "accumulated_nav"], help="净值口径")
    watchlist_add_parser.add_argument("--notes", default="", help="观察备注")
    watchlist_add_parser.add_argument("--dry-run", action="store_true", help="只预览修改，不写入文件")
    watchlist_add_parser.set_defaults(func=watchlist_add_command)

    watchlist_report_parser = subparsers.add_parser("watchlist-report", help="查看基金观察池")
    watchlist_report_parser.set_defaults(func=watchlist_report_command)

    watchlist_analyze_parser = subparsers.add_parser("watchlist-analyze", help="分析观察池候选基金")
    watchlist_analyze_parser.add_argument("fund_code", help="基金代码")
    watchlist_analyze_parser.add_argument("--weekly-dca", type=float, default=20, help="候选基金每周定投模拟金额，默认20元")
    watchlist_analyze_parser.add_argument("--start-date", help="定投模拟开始日期，格式 YYYY-MM-DD")
    watchlist_analyze_parser.set_defaults(func=watchlist_analyze_command)

    watchlist_remove_parser = subparsers.add_parser("watchlist-remove", help="从观察池移除基金")
    watchlist_remove_parser.add_argument("fund_code", help="基金代码")
    watchlist_remove_parser.add_argument("--dry-run", action="store_true", help="只预览修改，不写入文件")
    watchlist_remove_parser.set_defaults(func=watchlist_remove_command)

    watchlist_promote_parser = subparsers.add_parser("watchlist-promote", help="生成候选基金转入真实持仓的配置建议")
    watchlist_promote_parser.add_argument("fund_code", help="基金代码")
    watchlist_promote_parser.set_defaults(func=watchlist_promote_command)

    news_fetch_parser = subparsers.add_parser("news-fetch", help="抓取已启用新闻源的财经新闻")
    news_fetch_parser.set_defaults(func=news_fetch_command)

    news_analyze_parser = subparsers.add_parser("news-analyze", help="分析最近新闻并生成组合相关新闻报告")
    news_analyze_parser.add_argument("--days", type=int, default=1, help="分析最近 N 天新闻，默认 1 天")
    news_analyze_parser.set_defaults(func=news_analyze_command)

    news_report_parser = subparsers.add_parser("news-report", help="查看最近一次新闻分析摘要")
    news_report_parser.set_defaults(func=news_report_command)

    news_sources_parser = subparsers.add_parser("news-sources", help="查看新闻源配置")
    news_sources_parser.set_defaults(func=news_sources_command)

    news_source_add_parser = subparsers.add_parser("news-source-add", help="添加新闻源")
    news_source_add_parser.add_argument("--name", required=True, help="新闻源名称")
    news_source_add_parser.add_argument("--type", required=True, choices=["rss", "web"], help="新闻源类型")
    news_source_add_parser.add_argument("--url", required=True, help="新闻源 URL")
    news_source_add_parser.add_argument("--category", default="market", help="新闻源类别")
    news_source_add_parser.add_argument("--disabled", action="store_true", help="添加后保持禁用")
    news_source_add_parser.set_defaults(func=news_source_add_command)

    news_source_enable_parser = subparsers.add_parser("news-source-enable", help="启用新闻源")
    news_source_enable_parser.add_argument("name", help="新闻源名称")
    news_source_enable_parser.set_defaults(func=news_source_enable_command)

    news_source_disable_parser = subparsers.add_parser("news-source-disable", help="禁用新闻源")
    news_source_disable_parser.add_argument("name", help="新闻源名称")
    news_source_disable_parser.set_defaults(func=news_source_disable_command)

    news_import_parser = subparsers.add_parser("news-import", help="手动导入一条新闻到缓存")
    news_import_parser.add_argument("--title", required=True, help="新闻标题")
    news_import_parser.add_argument("--content", default="", help="新闻正文")
    news_import_parser.add_argument("--source", default="manual", help="新闻来源")
    news_import_parser.set_defaults(func=news_import_command)

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
