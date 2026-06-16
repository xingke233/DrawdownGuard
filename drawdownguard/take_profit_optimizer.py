import json
import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path

from .risk_compare import max_drawdown, volatility
from .take_profit import TakeProfitBacktester

_WORKER_CONFIG = None
_WORKER_HISTORY = None
_WORKER_BASELINE_MAX_DRAWDOWN = 0


def default_worker_count():
    return max(1, (os.cpu_count() or 2) - 1)


def generate_take_profit_combinations(preset="quick"):
    if preset == "quick":
        return _generate_quick_combinations()
    if preset == "full":
        return _generate_full_combinations()
    raise ValueError(f"未知止盈优化 preset：{preset}")


def _generate_quick_combinations():
    combinations = []
    level_profiles = [
        [10, 20, 30],
        [14, 26, 40],
        [20, 35, 50],
    ]
    sell_profiles = [
        [5, 10, 15],
        [15, 20, 25],
        [20, 25, 30],
    ]
    step_sells = [1, 3, 5]

    for levels in level_profiles:
        for sell_percents in sell_profiles:
            for step_sell in step_sells:
                combinations.append(_build_combination(levels, sell_percents, step_sell))
    return combinations


def _generate_full_combinations():
    combinations = []
    first_levels = range(10, 21, 2)
    second_levels = range(20, 36, 3)
    third_levels = range(30, 51, 5)
    first_sell_percents = range(5, 21, 5)
    second_sell_percents = range(10, 26, 5)
    third_sell_percents = range(15, 31, 5)
    step_sells = range(1, 6)

    for first_level in first_levels:
        for second_level in second_levels:
            for third_level in third_levels:
                if not first_level < second_level < third_level:
                    continue
                levels = [first_level, second_level, third_level]
                for first_sell in first_sell_percents:
                    for second_sell in second_sell_percents:
                        for third_sell in third_sell_percents:
                            sell_percents = [first_sell, second_sell, third_sell]
                            for step_sell in step_sells:
                                combinations.append(_build_combination(levels, sell_percents, step_sell))
    return combinations


def _build_combination(levels, sell_percents, step_sell):
    return {
        "levels": list(levels),
        "sell_percents": list(sell_percents),
        "step_sell_percent": step_sell,
        "rules": [
            {
                "level": levels[0],
                "base_sell_percent": sell_percents[0],
                "step_sell_percent": step_sell,
            },
            {
                "level": levels[1],
                "base_sell_percent": sell_percents[1],
                "step_sell_percent": step_sell,
            },
            {
                "level": levels[2],
                "base_sell_percent": sell_percents[2],
                "step_sell_percent": 0,
            },
        ],
    }


def run_take_profit_optimizer(
    config,
    history,
    combinations=None,
    workers=None,
    preset="quick",
    planned_count=None,
    progress_callback=None,
    partial_report_path=None,
):
    started_at = time.perf_counter()
    workers = workers or default_worker_count()
    combinations = combinations or generate_take_profit_combinations(preset)
    planned_count = planned_count or len(combinations)
    baseline_report = TakeProfitBacktester(config).run_without_take_profit(history)
    baseline_max_drawdown = max_drawdown(baseline_report.get("series", []))
    baseline = {
        "total_return_rate": baseline_report.get("total_return_rate", 0),
        "max_drawdown": baseline_max_drawdown,
        "volatility": volatility(baseline_report.get("series", [])),
    }
    results = []
    total = len(combinations)
    if total == 0:
        return _build_optimizer_report(baseline, results, preset, workers, planned_count, started_at)

    try:
        if workers <= 1:
            for index, combination in enumerate(combinations, start=1):
                results.append(_run_optimizer_case(config, history, baseline_max_drawdown, index, combination))
                _notify_optimizer_progress(
                    progress_callback,
                    partial_report_path,
                    baseline,
                    results,
                    preset,
                    workers,
                    planned_count,
                    started_at,
                    total,
                )
        else:
            with ProcessPoolExecutor(
                max_workers=workers,
                initializer=_init_optimizer_worker,
                initargs=(config, history, baseline_max_drawdown),
                mp_context=multiprocessing.get_context("fork"),
            ) as executor:
                futures = [
                    executor.submit(_run_optimizer_worker, (index, combination))
                    for index, combination in enumerate(combinations, start=1)
                ]
                for future in as_completed(futures):
                    results.append(future.result())
                    _notify_optimizer_progress(
                        progress_callback,
                        partial_report_path,
                        baseline,
                        results,
                        preset,
                        workers,
                        planned_count,
                        started_at,
                        total,
                    )
    except KeyboardInterrupt:
        _save_partial_report(partial_report_path, baseline, results, preset, workers, planned_count, started_at)
        raise

    results.sort(key=lambda item: item["scenario_id"])
    return _build_optimizer_report(baseline, results, preset, workers, planned_count, started_at)


def _init_optimizer_worker(config, history, baseline_max_drawdown):
    global _WORKER_CONFIG, _WORKER_HISTORY, _WORKER_BASELINE_MAX_DRAWDOWN
    _WORKER_CONFIG = config
    _WORKER_HISTORY = history
    _WORKER_BASELINE_MAX_DRAWDOWN = baseline_max_drawdown


def _run_optimizer_worker(task):
    index, combination = task
    return _run_optimizer_case(
        _WORKER_CONFIG,
        _WORKER_HISTORY,
        _WORKER_BASELINE_MAX_DRAWDOWN,
        index,
        combination,
    )


def _run_optimizer_case(config, history, baseline_max_drawdown, index, combination):
    scenario_config = deepcopy(config)
    scenario_config.setdefault("take_profit_backtest", {})["rules"] = combination["rules"]
    report = TakeProfitBacktester(scenario_config).run_compact(history)
    result = {
        "scenario_id": f"TP{index:05d}",
        "levels": combination["levels"],
        "sell_percents": combination["sell_percents"],
        "step_sell_percent": combination["step_sell_percent"],
        "total_return_rate": report.get("total_return_rate", 0),
        "max_drawdown": max_drawdown(report.get("series", [])),
        "volatility": volatility(report.get("series", [])),
        "bullet_cash_final": report.get("final_cash", 0),
        "sell_count": report.get("trigger_count_sell", 0),
        "sell_count_by_level": report.get("sell_count_by_level", {}),
        "total_sell_amount": report.get("total_sell_amount", 0),
        "final_market_value": report.get("final_market_value", 0),
        "total_asset_value": report.get("total_asset_value", 0),
    }
    result["max_drawdown_improvement"] = result["max_drawdown"] - baseline_max_drawdown
    result["risk_return_score"] = (
        result["total_return_rate"] + result["max_drawdown_improvement"] - result["volatility"]
    )
    return result


def _notify_optimizer_progress(
    progress_callback,
    partial_report_path,
    baseline,
    results,
    preset,
    workers,
    planned_count,
    started_at,
    total,
):
    completed = len(results)
    elapsed = time.perf_counter() - started_at
    eta = (elapsed / completed * (total - completed)) if completed else None
    if progress_callback:
        progress_callback(completed, total, elapsed, eta)
    if partial_report_path and (completed == total or completed % max(1, min(100, total // 10 or 1)) == 0):
        _save_partial_report(partial_report_path, baseline, results, preset, workers, planned_count, started_at)


def _build_optimizer_report(baseline, results, preset, workers, planned_count, started_at, partial=False):
    rankings = build_optimizer_rankings(results)
    return {
        "preset": preset,
        "workers": workers,
        "planned_count": planned_count,
        "partial": partial,
        "duration_seconds": round(time.perf_counter() - started_at, 3),
        "baseline": baseline,
        "tested_count": len(results),
        "results": results,
        "rankings": rankings,
        "recommended": rankings["risk_return"][0] if rankings["risk_return"] else None,
    }


def _save_partial_report(partial_report_path, baseline, results, preset, workers, planned_count, started_at):
    if not partial_report_path:
        return
    report = _build_optimizer_report(
        baseline,
        sorted(results, key=lambda item: item["scenario_id"]),
        preset,
        workers,
        planned_count,
        started_at,
        partial=True,
    )
    path = Path(partial_report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")


def build_optimizer_rankings(results, limit=10):
    by_risk = sorted(
        results,
        key=lambda item: (item["max_drawdown_improvement"], item["total_return_rate"]),
        reverse=True,
    )
    by_return = sorted(
        results,
        key=lambda item: (item["total_return_rate"], item["max_drawdown_improvement"]),
        reverse=True,
    )
    by_score = sorted(results, key=lambda item: item["risk_return_score"], reverse=True)
    return {
        "max_drawdown_improvement": [_compact_result(item) for item in by_risk[:limit]],
        "total_return_rate": [_compact_result(item) for item in by_return[:limit]],
        "risk_return": [_compact_result(item) for item in by_score[:limit]],
    }


def summarize_take_profit_optimizer_report(report):
    lines = ["阶梯止盈档位优化摘要"]
    results = report.get("results", [])
    if not results:
        lines.append("暂无优化结果。")
        return "\n".join(lines)

    lines.append(f"测试组合数量：{report.get('tested_count', len(results))}")
    if report.get("planned_count") is not None:
        lines.append(
            f"preset：{report.get('preset', 'quick')} | "
            f"workers：{report.get('workers', 1)} | "
            f"完整组合数：{report.get('planned_count')} | "
            f"耗时：{report.get('duration_seconds', 0):.2f}s"
        )
    baseline = report.get("baseline", {})
    lines.append(
        f"原始策略基线：收益率 {baseline.get('total_return_rate', 0) * 100:.2f}% | "
        f"最大回撤 {baseline.get('max_drawdown', 0) * 100:.2f}% | "
        f"波动率 {baseline.get('volatility', 0) * 100:.2f}%"
    )
    recommended = report.get("recommended")
    if recommended:
        lines.append(
            "推荐组合："
            f"{recommended['scenario_id']} | "
            f"档位 {_format_list(recommended['levels'])} | "
            f"卖出比例 {_format_list(recommended['sell_percents'])} | "
            f"增量 {recommended['step_sell_percent']}% | "
            f"收益率 {recommended['total_return_rate'] * 100:.2f}% | "
            f"最大回撤 {recommended['max_drawdown'] * 100:.2f}% | "
            f"回撤改善 {recommended['max_drawdown_improvement'] * 100:.2f}%"
        )

    lines.append("最大回撤改善排名 Top 3：")
    for item in report.get("rankings", {}).get("max_drawdown_improvement", [])[:3]:
        lines.append(_summary_line(item))

    lines.append("收益率排名 Top 3：")
    for item in report.get("rankings", {}).get("total_return_rate", [])[:3]:
        lines.append(_summary_line(item))
    lines.append("说明：优化结果为历史净值策略模拟，不代表真实账户收益。")
    return "\n".join(lines)


def _compact_result(item):
    return {
        "scenario_id": item["scenario_id"],
        "levels": item["levels"],
        "sell_percents": item["sell_percents"],
        "step_sell_percent": item["step_sell_percent"],
        "total_return_rate": item["total_return_rate"],
        "max_drawdown": item["max_drawdown"],
        "max_drawdown_improvement": item["max_drawdown_improvement"],
        "volatility": item["volatility"],
        "bullet_cash_final": item["bullet_cash_final"],
        "sell_count": item["sell_count"],
        "risk_return_score": item["risk_return_score"],
    }


def _summary_line(item):
    return (
        f"- {item['scenario_id']} | 档位 {_format_list(item['levels'])} | "
        f"卖出比例 {_format_list(item['sell_percents'])} | 增量 {item['step_sell_percent']}% | "
        f"收益率 {item['total_return_rate'] * 100:.2f}% | "
        f"最大回撤 {item['max_drawdown'] * 100:.2f}% | "
        f"改善 {item['max_drawdown_improvement'] * 100:.2f}%"
    )


def _format_list(values):
    return "/".join(str(value) for value in values)
