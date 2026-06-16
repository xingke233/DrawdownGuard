import json
import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, pstdev


FREQUENCIES = ["weekly", "biweekly", "monthly"]
AMOUNT_MODES = ["fixed", "increasing", "decreasing", "volatility_scaled"]
DRAWDOWN_RULES = ["none", "mild", "aggressive"]
HIGH_LEVEL_RULES = ["none", "reduce", "strong_reduce"]

_WORKER_HISTORIES = None


def default_dca_workers():
    return max(1, (os.cpu_count() or 2) - 1)


def generate_dca_strategy_combinations(preset="quick"):
    if preset == "quick":
        return [
            _combo("weekly", "fixed", "none", "none"),
            _combo("weekly", "volatility_scaled", "none", "none"),
            _combo("weekly", "fixed", "mild", "reduce"),
            _combo("biweekly", "fixed", "none", "none"),
            _combo("monthly", "decreasing", "none", "strong_reduce"),
            _combo("weekly", "fixed", "aggressive", "none"),
        ]
    if preset == "full":
        return [
            _combo(frequency, amount_mode, drawdown_rule, high_level_rule)
            for frequency in FREQUENCIES
            for amount_mode in AMOUNT_MODES
            for drawdown_rule in DRAWDOWN_RULES
            for high_level_rule in HIGH_LEVEL_RULES
        ]
    raise ValueError(f"未知 DCA preset：{preset}")


def run_dca_strategy_lab(
    config,
    histories,
    preset="quick",
    workers=None,
    start_date=None,
    end_date=None,
    checkpoint_path=None,
    progress_callback=None,
):
    started_at = time.perf_counter()
    workers = workers or default_dca_workers()
    portfolio_config = config.get("portfolio_backtest", {})
    start_date = start_date or portfolio_config.get("start_date", "1900-01-01")
    end_date = end_date or portfolio_config.get("end_date")
    combinations = generate_dca_strategy_combinations(preset)
    assets = [
        asset for asset in portfolio_config.get("assets", [])
        if asset.get("representative_fund") in histories
    ]
    tasks = []
    for asset in assets:
        for combination in combinations:
            scenario_id = _scenario_id(asset["asset_id"], combination)
            tasks.append((scenario_id, asset, combination, start_date, end_date))

    completed = _load_checkpoint(checkpoint_path)
    results = completed.get("results", [])
    completed_ids = {item["scenario_id"] for item in results}
    pending_tasks = [task for task in tasks if task[0] not in completed_ids]
    total = len(tasks)

    try:
        if workers <= 1:
            for task in pending_tasks:
                results.append(_run_dca_worker_with_histories(histories, task))
                _notify_progress(progress_callback, checkpoint_path, results, preset, workers, total, started_at)
        else:
            with ProcessPoolExecutor(
                max_workers=workers,
                initializer=_init_worker,
                initargs=(histories,),
                mp_context=multiprocessing.get_context("fork"),
            ) as executor:
                futures = [executor.submit(_run_dca_worker, task) for task in pending_tasks]
                for future in as_completed(futures):
                    results.append(future.result())
                    _notify_progress(progress_callback, checkpoint_path, results, preset, workers, total, started_at)
    except KeyboardInterrupt:
        _save_checkpoint(checkpoint_path, results, preset, workers, total, started_at)
        raise

    return _build_report(config, results, preset, workers, total, started_at, start_date, end_date)


def simulate_dca_strategy(asset, history, combination, start_date=None, end_date=None):
    start_date = start_date or (history[0]["date"] if history else "1900-01-01")
    filtered = [
        item for item in history
        if item["date"] >= start_date and (not end_date or item["date"] <= end_date)
    ]
    if not filtered:
        return _empty_result(asset, combination)

    base_amount = float(asset.get("weekly_dca_amount", 0))
    next_buy_date = date.fromisoformat(filtered[0]["date"])
    if start_date <= filtered[0]["date"]:
        next_buy_date = _next_weekday(date.fromisoformat(start_date), 0)
        if (date.fromisoformat(filtered[0]["date"]) - date.fromisoformat(start_date)).days > 7:
            next_buy_date = date.fromisoformat(filtered[0]["date"])

    shares = 0
    invested = 0
    events = []
    value_series = []
    navs = []
    start_month = filtered[0]["date"][:7]
    last_monthly_buy = None

    for row in filtered:
        current_date = date.fromisoformat(row["date"])
        nav = float(row["nav"])
        navs.append(nav)
        if _is_buy_day(combination["frequency"], current_date, next_buy_date, row["date"][:7], last_monthly_buy):
            amount = calculate_dca_amount(base_amount, combination, navs, row["date"], start_month)
            amount = _apply_drawdown_rule(amount, combination["drawdown_rule"], navs)
            amount = _apply_high_level_rule(amount, combination["high_level_rule"], navs)
            if amount > 0 and nav > 0:
                buy_shares = amount / nav
                shares += buy_shares
                invested += amount
                events.append({"date": row["date"], "nav": nav, "amount": amount, "shares": buy_shares})
            next_buy_date = _advance_buy_date(combination["frequency"], current_date, next_buy_date)
            if combination["frequency"] == "monthly":
                last_monthly_buy = row["date"][:7]

        value_series.append({"date": row["date"], "total_asset_value": shares * nav})

    final_nav = float(filtered[-1]["nav"])
    final_value = shares * final_nav
    total_profit = final_value - invested
    total_return_rate = total_profit / invested if invested > 0 else 0
    max_dd = calculate_max_drawdown(value_series)
    vol = calculate_volatility(value_series)
    return {
        "frequency": combination["frequency"],
        "amount_mode": combination["amount_mode"],
        "drawdown_rule": combination["drawdown_rule"],
        "high_level_rule": combination["high_level_rule"],
        "total_return_rate": total_return_rate,
        "max_drawdown": max_dd,
        "volatility": vol,
        "sharpe_like_ratio": total_return_rate / vol if vol else None,
        "total_invested": invested,
        "final_value": final_value,
        "buy_count": len(events),
        "events": events,
    }


def calculate_dca_amount(base_amount, combination, navs, current_date, start_month):
    amount_mode = combination["amount_mode"]
    if amount_mode == "fixed":
        return base_amount
    month_delta = _month_delta(start_month, current_date[:7])
    if amount_mode == "increasing":
        return base_amount * (1.02 ** month_delta)
    if amount_mode == "decreasing":
        return base_amount * (0.98 ** month_delta)
    if amount_mode == "volatility_scaled":
        returns = _nav_returns(navs[-21:])
        vol = pstdev(returns) if len(returns) > 1 else 0
        if vol == 0:
            return base_amount
        scale = min(1.5, max(0.5, 0.015 / vol))
        return base_amount * scale
    return base_amount


def calculate_max_drawdown(series):
    values = [item.get("total_asset_value", 0) for item in series if item.get("total_asset_value", 0) > 0]
    if not values:
        return 0
    peak = values[0]
    result = 0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            result = min(result, value / peak - 1)
    return result


def calculate_volatility(series):
    values = [item.get("total_asset_value", 0) for item in series if item.get("total_asset_value", 0) > 0]
    returns = [
        values[index] / values[index - 1] - 1
        for index in range(1, len(values))
        if values[index - 1] > 0
    ]
    return pstdev(returns) if len(returns) > 1 else 0


def summarize_dca_strategy_report(report):
    lines = ["Dynamic DCA Strategy Lab 摘要"]
    if not report:
        lines.append("暂无 DCA 策略报告。")
        return "\n".join(lines)
    lines.append(
        f"preset：{report.get('preset')} | workers：{report.get('workers')} | "
        f"测试组合：{report.get('tested_count')} | 回测区间：{report.get('start_date')} 至 {report.get('end_date')}"
    )
    for asset in report.get("assets", []):
        best = asset.get("best_strategy", {})
        lines.append(
            f"- {asset['asset_id']} {asset['asset_name']} | 最优 {best.get('frequency')}/"
            f"{best.get('amount_mode')}/{best.get('drawdown_rule')}/{best.get('high_level_rule')} | "
            f"收益率 {_fmt_pct(best.get('total_return_rate'))} | "
            f"最大回撤 {_fmt_pct(best.get('max_drawdown'))} | 夏普 {_fmt_num(best.get('sharpe_like_ratio'))}"
        )
    conclusion = report.get("conclusion", {})
    lines.append(f"统一 DCA 是否最优：{conclusion.get('unified_dca_optimal')}")
    lines.append(f"需要特殊策略资产：{', '.join(conclusion.get('assets_requiring_special_strategy', [])) or '无'}")
    lines.append(f"红利低波 volatility_scaled：{conclusion.get('dividend_low_vol_volatility_scaled')}")
    lines.append(f"黄金 decreasing：{conclusion.get('gold_decreasing')}")
    lines.append(f"纳指 aggressive：{conclusion.get('nasdaq_aggressive')}")
    return "\n".join(lines)


def _build_report(config, results, preset, workers, total, started_at, start_date, end_date):
    assets = []
    by_asset = {}
    for item in sorted(results, key=lambda row: (row["asset_id"], row["scenario_id"])):
        by_asset.setdefault(item["asset_id"], []).append(item)
    asset_config = {asset["asset_id"]: asset for asset in config.get("portfolio_backtest", {}).get("assets", [])}
    for asset_id, asset_results in by_asset.items():
        asset = asset_config.get(asset_id, {"asset_id": asset_id, "asset_name": asset_id})
        ranked_return = sorted(asset_results, key=lambda item: item["total_return_rate"], reverse=True)
        ranked_risk = sorted(asset_results, key=lambda item: item["max_drawdown"], reverse=True)
        ranked_sharpe = sorted(
            asset_results,
            key=lambda item: item["sharpe_like_ratio"] if item["sharpe_like_ratio"] is not None else -999,
            reverse=True,
        )
        assets.append(
            {
                "asset_id": asset_id,
                "asset_name": asset.get("asset_name"),
                "representative_fund": asset.get("representative_fund"),
                "nav_mode": asset.get("nav_mode", "unit_nav"),
                "best_strategy": _compact_strategy(ranked_sharpe[0]) if ranked_sharpe else None,
                "rankings": {
                    "highest_return": [_compact_strategy(item) for item in ranked_return[:5]],
                    "lowest_risk": [_compact_strategy(item) for item in ranked_risk[:5]],
                    "highest_sharpe": [_compact_strategy(item) for item in ranked_sharpe[:5]],
                },
                "results": asset_results,
            }
        )
    return {
        "preset": preset,
        "workers": workers,
        "planned_count": total,
        "tested_count": len(results),
        "duration_seconds": round(time.perf_counter() - started_at, 3),
        "start_date": start_date,
        "end_date": end_date,
        "assets": assets,
        "conclusion": _build_conclusion(assets),
    }


def _build_conclusion(assets):
    best_modes = {asset["asset_id"]: asset.get("best_strategy", {}) for asset in assets}
    unique_strategies = {
        (
            item.get("frequency"),
            item.get("amount_mode"),
            item.get("drawdown_rule"),
            item.get("high_level_rule"),
        )
        for item in best_modes.values()
        if item
    }
    special = [
        asset_id for asset_id, strategy in best_modes.items()
        if strategy and (
            strategy.get("amount_mode") != "fixed"
            or strategy.get("drawdown_rule") != "none"
            or strategy.get("high_level_rule") != "none"
        )
    ]
    return {
        "unified_dca_optimal": len(unique_strategies) <= 1,
        "assets_requiring_special_strategy": special,
        "dividend_low_vol_volatility_scaled": best_modes.get("DIVIDEND_LOW_VOL", {}).get("amount_mode") == "volatility_scaled",
        "gold_decreasing": best_modes.get("GOLD", {}).get("amount_mode") == "decreasing",
        "nasdaq_aggressive": best_modes.get("NASDAQ100", {}).get("drawdown_rule") == "aggressive",
        "split_strategy_recommended": len(unique_strategies) > 1 or bool(special),
    }


def _init_worker(histories):
    global _WORKER_HISTORIES
    _WORKER_HISTORIES = histories


def _run_dca_worker(task):
    return _run_dca_worker_with_histories(_WORKER_HISTORIES, task)


def _run_dca_worker_with_histories(histories, task):
    scenario_id, asset, combination, start_date, end_date = task
    fund_code = asset.get("representative_fund")
    result = simulate_dca_strategy(asset, histories.get(fund_code, []), combination, start_date, end_date)
    return {
        "scenario_id": scenario_id,
        "asset_id": asset.get("asset_id"),
        "asset_name": asset.get("asset_name"),
        **result,
    }


def _notify_progress(progress_callback, checkpoint_path, results, preset, workers, total, started_at):
    completed = len(results)
    elapsed = time.perf_counter() - started_at
    eta = elapsed / completed * (total - completed) if completed else None
    if progress_callback:
        progress_callback(completed, total, elapsed, eta)
    if checkpoint_path and (completed == total or completed % max(1, min(100, total // 10 or 1)) == 0):
        _save_checkpoint(checkpoint_path, results, preset, workers, total, started_at)


def _save_checkpoint(checkpoint_path, results, preset, workers, total, started_at):
    if not checkpoint_path:
        return
    path = Path(checkpoint_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "preset": preset,
                "workers": workers,
                "planned_count": total,
                "tested_count": len(results),
                "duration_seconds": round(time.perf_counter() - started_at, 3),
                "results": results,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")


def _load_checkpoint(checkpoint_path):
    if not checkpoint_path:
        return {"results": []}
    path = Path(checkpoint_path)
    if not path.exists():
        return {"results": []}
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return {"results": data.get("results", [])}
    except Exception:
        return {"results": []}


def _combo(frequency, amount_mode, drawdown_rule, high_level_rule):
    return {
        "frequency": frequency,
        "amount_mode": amount_mode,
        "drawdown_rule": drawdown_rule,
        "high_level_rule": high_level_rule,
    }


def _scenario_id(asset_id, combination):
    return (
        f"{asset_id}__{combination['frequency']}__{combination['amount_mode']}__"
        f"{combination['drawdown_rule']}__{combination['high_level_rule']}"
    )


def _empty_result(asset, combination):
    return {
        **combination,
        "total_return_rate": 0,
        "max_drawdown": 0,
        "volatility": 0,
        "sharpe_like_ratio": None,
        "total_invested": 0,
        "final_value": 0,
        "buy_count": 0,
        "events": [],
    }


def _is_buy_day(frequency, current_date, next_buy_date, current_month, last_monthly_buy):
    if frequency == "monthly":
        return current_month != last_monthly_buy and current_date >= next_buy_date
    return current_date >= next_buy_date


def _advance_buy_date(frequency, current_date, next_buy_date):
    if frequency == "weekly":
        step = timedelta(days=7)
    elif frequency == "biweekly":
        step = timedelta(days=14)
    else:
        return _first_day_next_month(current_date)
    next_date = next_buy_date + step
    while current_date >= next_date:
        next_date += step
    return next_date


def _apply_drawdown_rule(amount, rule, navs):
    if len(navs) < 2:
        return amount
    peak = max(navs)
    drawdown = navs[-1] / peak - 1 if peak > 0 else 0
    if rule == "mild" and drawdown <= -0.10:
        return amount * 2
    if rule == "aggressive":
        if drawdown <= -0.10:
            return amount * 2
        if drawdown <= -0.05:
            return amount * 1.5
    return amount


def _apply_high_level_rule(amount, rule, navs):
    if rule == "none" or len(navs) < 20:
        return amount
    moving_average = mean(navs[-60:])
    if moving_average <= 0 or navs[-1] <= moving_average * 1.10:
        return amount
    if rule == "reduce":
        return amount * 0.7
    if rule == "strong_reduce":
        return amount * 0.5
    return amount


def _nav_returns(navs):
    return [
        navs[index] / navs[index - 1] - 1
        for index in range(1, len(navs))
        if navs[index - 1] > 0
    ]


def _next_weekday(start, weekday):
    days = (weekday - start.weekday()) % 7
    return start + timedelta(days=days)


def _first_day_next_month(current):
    if current.month == 12:
        return date(current.year + 1, 1, 1)
    return date(current.year, current.month + 1, 1)


def _month_delta(start_month, current_month):
    start_year, start_mon = [int(item) for item in start_month.split("-")]
    current_year, current_mon = [int(item) for item in current_month.split("-")]
    return (current_year - start_year) * 12 + current_mon - start_mon


def _compact_strategy(item):
    return {
        "scenario_id": item["scenario_id"],
        "frequency": item["frequency"],
        "amount_mode": item["amount_mode"],
        "drawdown_rule": item["drawdown_rule"],
        "high_level_rule": item["high_level_rule"],
        "total_return_rate": item["total_return_rate"],
        "max_drawdown": item["max_drawdown"],
        "volatility": item["volatility"],
        "sharpe_like_ratio": item["sharpe_like_ratio"],
        "total_invested": item["total_invested"],
        "final_value": item["final_value"],
    }


def _fmt_pct(value):
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _fmt_num(value):
    return "N/A" if value is None else f"{value:.2f}"
