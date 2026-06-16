from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import os


ASSET_LIMITS = {
    "NASDAQ100": 0.60,
    "HSTECH": 0.15,
    "GOLD": 0.25,
    "CASHFLOW": 0.10,
    "DIVIDEND_LOW_VOL": 0.30,
}
HIGH_VOL_ASSETS = {"NASDAQ100", "HSTECH"}
MIN_BULLET_CASH_WEIGHT = 0.05
MAX_DRAWDOWN_LIMIT = 0.25
HIGH_VOL_LIMIT = 0.70


def default_optimizer_workers():
    return max(1, (os.cpu_count() or 2) - 1)


def run_portfolio_constraint_optimizer(portfolio_report, dca_report, preset="quick", workers=1):
    assets = _asset_metrics(portfolio_report, dca_report)
    candidates = generate_weight_candidates(preset, assets.keys())
    tasks = [(candidate, assets) for candidate in candidates]
    if workers and workers > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("fork")) as executor:
            evaluated = list(executor.map(_evaluate_task, tasks))
    else:
        evaluated = [_evaluate_task(task) for task in tasks]

    feasible = [item for item in evaluated if item["constraints"]["all_satisfied"]]
    pool = feasible or evaluated
    modes = {
        "max_return_mode": max(pool, key=lambda item: item["total_return_rate"], default=None),
        "min_risk_mode": min(pool, key=lambda item: item["drawdown"], default=None),
        "balanced_mode": max(pool, key=lambda item: item["score"], default=None),
    }
    ranked = sorted(pool, key=lambda item: item["score"], reverse=True)
    return {
        "preset": preset,
        "planned_count": len(candidates),
        "tested_count": len(evaluated),
        "feasible_count": len(feasible),
        "constraints": {
            "max_drawdown": MAX_DRAWDOWN_LIMIT,
            "asset_limits": ASSET_LIMITS,
            "min_bullet_cash_weight": MIN_BULLET_CASH_WEIGHT,
            "high_volatility_weight_limit": HIGH_VOL_LIMIT,
        },
        "modes": {key: _compact_result(value) for key, value in modes.items()},
        "recommendations": {
            "best_portfolio": _compact_result(modes["balanced_mode"]),
            "runner_up_portfolio": _compact_result(ranked[1] if len(ranked) > 1 else None),
            "conservative_portfolio": _compact_result(modes["min_risk_mode"]),
        },
        "binding_constraints": binding_constraints(ranked[0] if ranked else None),
        "compressed_assets": compressed_assets(ranked[0] if ranked else None),
        "top_results": [_compact_result(item) for item in ranked[:10]],
        "all_results": [_compact_result(item) for item in evaluated],
        "explanation": build_explanation(ranked[0] if ranked else None, len(feasible), len(evaluated)),
    }


def generate_weight_candidates(preset, asset_ids):
    asset_ids = [asset_id for asset_id in asset_ids if asset_id in ASSET_LIMITS]
    if preset == "quick":
        raw_candidates = [
            {"NASDAQ100": 0.55, "HSTECH": 0.05, "CASHFLOW": 0.05, "DIVIDEND_LOW_VOL": 0.10, "GOLD": 0.25},
            {"NASDAQ100": 0.45, "HSTECH": 0.05, "CASHFLOW": 0.05, "DIVIDEND_LOW_VOL": 0.20, "GOLD": 0.25},
            {"NASDAQ100": 0.35, "HSTECH": 0.05, "CASHFLOW": 0.10, "DIVIDEND_LOW_VOL": 0.30, "GOLD": 0.20},
            {"NASDAQ100": 0.60, "HSTECH": 0.05, "CASHFLOW": 0.05, "DIVIDEND_LOW_VOL": 0.05, "GOLD": 0.25},
            {"NASDAQ100": 0.30, "HSTECH": 0.10, "CASHFLOW": 0.10, "DIVIDEND_LOW_VOL": 0.30, "GOLD": 0.20},
        ]
        return [_filter_and_normalize(candidate, asset_ids) for candidate in raw_candidates]
    if preset != "full":
        raise ValueError(f"未知 portfolio optimize preset：{preset}")
    return _generate_full_candidates(asset_ids)


def normalize_weights(weights):
    total = sum(value for value in weights.values() if value > 0)
    if total <= 0:
        return {key: 0 for key in weights}
    return {key: value / total for key, value in weights.items()}


def check_constraints(weights, drawdown, bullet_cash_weight=MIN_BULLET_CASH_WEIGHT):
    violations = []
    asset_limit_status = {}
    for asset_id, limit in ASSET_LIMITS.items():
        weight = weights.get(asset_id, 0)
        ok = weight <= limit + 1e-9
        asset_limit_status[asset_id] = {"weight": weight, "limit": limit, "satisfied": ok}
        if not ok:
            violations.append(f"{asset_id} weight {weight:.2%} > {limit:.2%}")
    high_vol_weight = sum(weights.get(asset_id, 0) for asset_id in HIGH_VOL_ASSETS)
    if high_vol_weight > HIGH_VOL_LIMIT + 1e-9:
        violations.append(f"高波动资产权重 {high_vol_weight:.2%} > {HIGH_VOL_LIMIT:.2%}")
    if drawdown > MAX_DRAWDOWN_LIMIT + 1e-9:
        violations.append(f"最大回撤 {drawdown:.2%} > {MAX_DRAWDOWN_LIMIT:.2%}")
    if bullet_cash_weight < MIN_BULLET_CASH_WEIGHT - 1e-9:
        violations.append(f"现金仓位 {bullet_cash_weight:.2%} < {MIN_BULLET_CASH_WEIGHT:.2%}")
    return {
        "all_satisfied": not violations,
        "violations": violations,
        "asset_limit_status": asset_limit_status,
        "drawdown_satisfied": drawdown <= MAX_DRAWDOWN_LIMIT + 1e-9,
        "cash_satisfied": bullet_cash_weight >= MIN_BULLET_CASH_WEIGHT - 1e-9,
        "high_volatility_weight": high_vol_weight,
        "high_volatility_satisfied": high_vol_weight <= HIGH_VOL_LIMIT + 1e-9,
    }


def score_portfolio(total_return_rate, drawdown, sharpe_like_ratio):
    return 0.5 * total_return_rate - 0.3 * drawdown + 0.2 * (sharpe_like_ratio or 0)


def summarize_portfolio_optimize_report(report):
    lines = ["Portfolio Constraint Optimizer 摘要"]
    if not report:
        lines.append("暂无组合约束优化报告。")
        return "\n".join(lines)
    lines.append(
        f"preset：{report.get('preset')} | 测试组合：{report.get('tested_count')} | "
        f"可行组合：{report.get('feasible_count')}"
    )
    for mode_name, result in report.get("modes", {}).items():
        lines.append(
            f"{mode_name}：收益 {_fmt_pct(result.get('return'))} | "
            f"回撤 {_fmt_pct(result.get('drawdown'))} | 夏普 {_fmt_num(result.get('sharpe'))} | "
            f"现金利用 {_fmt_pct(result.get('cash_utilization'))}"
        )
    best = report.get("recommendations", {}).get("best_portfolio", {})
    lines.append(f"最优组合：{best.get('candidate_id')}")
    lines.append(f"binding constraints：{', '.join(report.get('binding_constraints', [])) or '无'}")
    lines.append(f"自动压缩权重资产：{', '.join(report.get('compressed_assets', [])) or '无'}")
    lines.append(f"解释：{report.get('explanation')}")
    return "\n".join(lines)


def binding_constraints(result):
    if not result:
        return []
    bindings = []
    for asset_id, status in result["constraints"].get("asset_limit_status", {}).items():
        if abs(status["weight"] - status["limit"]) <= 0.01:
            bindings.append(f"{asset_id}_max_weight")
    if abs(result["drawdown"] - MAX_DRAWDOWN_LIMIT) <= 0.01:
        bindings.append("max_drawdown")
    if abs(result["constraints"].get("high_volatility_weight", 0) - HIGH_VOL_LIMIT) <= 0.01:
        bindings.append("high_volatility_budget")
    bindings.append("min_bullet_cash")  # Optimizer reserves the minimum 5% cash by design.
    return bindings


def compressed_assets(result):
    if not result:
        return []
    return [
        asset_id for asset_id, status in result["constraints"].get("asset_limit_status", {}).items()
        if abs(status["weight"] - status["limit"]) <= 0.01
    ]


def build_explanation(best, feasible_count, tested_count):
    if not best:
        return "没有可评估组合。"
    if feasible_count == 0:
        return "没有组合完全满足约束，报告展示的是约束违反最少的候选结果。"
    ratio = feasible_count / tested_count if tested_count else 0
    if ratio < 0.25:
        return "可行组合空间较窄，当前组合接近约束边界。"
    return "存在可行优化空间，可在收益、回撤和现金仓位之间继续细化权衡。"


def _evaluate_task(task):
    weights, assets = task
    return evaluate_candidate(weights, assets)


def evaluate_candidate(weights, assets):
    weights = normalize_weights(weights)
    total_return = sum(weights.get(asset_id, 0) * assets[asset_id]["return"] for asset_id in assets)
    drawdown = sum(weights.get(asset_id, 0) * assets[asset_id]["drawdown"] for asset_id in assets)
    volatility = sum(weights.get(asset_id, 0) * assets[asset_id]["volatility"] for asset_id in assets)
    sharpe = total_return / volatility if volatility else None
    cash_utilization = 1 - MIN_BULLET_CASH_WEIGHT
    constraints = check_constraints(weights, drawdown, MIN_BULLET_CASH_WEIGHT)
    return {
        "candidate_id": _candidate_id(weights),
        "asset_weights": weights,
        "return": total_return,
        "total_return_rate": total_return,
        "drawdown": drawdown,
        "max_drawdown": -drawdown,
        "volatility": volatility,
        "sharpe": sharpe,
        "sharpe_like_ratio": sharpe,
        "cash_utilization": cash_utilization,
        "bullet_cash_weight": MIN_BULLET_CASH_WEIGHT,
        "score": score_portfolio(total_return, drawdown, sharpe),
        "constraints": constraints,
    }


def _asset_metrics(portfolio_report, dca_report):
    dca_assets = {asset.get("asset_id"): asset for asset in dca_report.get("assets", [])}
    metrics = {}
    for asset in portfolio_report.get("assets", []):
        asset_id = asset.get("asset_id")
        if asset_id not in ASSET_LIMITS:
            continue
        dca_best = dca_assets.get(asset_id, {}).get("best_strategy", {})
        return_rate = dca_best.get("total_return_rate", asset.get("total_return_rate", 0))
        drawdown = abs(dca_best.get("max_drawdown", _asset_drawdown(asset.get("series", []))))
        volatility = dca_best.get("volatility", _asset_volatility(asset.get("series", [])))
        metrics[asset_id] = {
            "return": return_rate or 0,
            "drawdown": drawdown or 0,
            "volatility": volatility or 0,
        }
    return metrics


def _generate_full_candidates(asset_ids):
    ordered = [asset_id for asset_id in ASSET_LIMITS if asset_id in asset_ids]
    step = 0.05
    units_total = int(round(1 / step))
    limits = {asset_id: int(round(ASSET_LIMITS[asset_id] / step)) for asset_id in ordered}
    results = []

    def walk(index, remaining, current):
        if index == len(ordered) - 1:
            asset_id = ordered[index]
            if 0 <= remaining <= limits[asset_id]:
                candidate = {**current, asset_id: remaining * step}
                results.append(candidate)
            return
        asset_id = ordered[index]
        for units in range(0, min(limits[asset_id], remaining) + 1):
            walk(index + 1, remaining - units, {**current, asset_id: units * step})

    walk(0, units_total, {})
    return [normalize_weights(candidate) for candidate in results]


def _filter_and_normalize(candidate, asset_ids):
    return normalize_weights({asset_id: candidate.get(asset_id, 0) for asset_id in asset_ids})


def _compact_result(result):
    if not result:
        return None
    return {
        "candidate_id": result["candidate_id"],
        "asset_weights": result["asset_weights"],
        "return": result["return"],
        "drawdown": result["drawdown"],
        "sharpe": result["sharpe"],
        "cash_utilization": result["cash_utilization"],
        "volatility": result["volatility"],
        "score": result["score"],
        "constraints": result["constraints"],
    }


def _asset_drawdown(series):
    values = [item.get("nav", 0) for item in series if item.get("nav", 0) > 0]
    if not values:
        return 0
    peak = values[0]
    result = 0
    for value in values:
        peak = max(peak, value)
        if peak:
            result = min(result, value / peak - 1)
    return result


def _asset_volatility(series):
    values = [item.get("nav", 0) for item in series if item.get("nav", 0) > 0]
    returns = [values[index] / values[index - 1] - 1 for index in range(1, len(values)) if values[index - 1] > 0]
    if len(returns) <= 1:
        return 0
    avg = sum(returns) / len(returns)
    return (sum((value - avg) ** 2 for value in returns) / len(returns)) ** 0.5


def _candidate_id(weights):
    return "_".join(f"{asset_id}{int(round(weight * 100))}" for asset_id, weight in sorted(weights.items()))


def _fmt_pct(value):
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _fmt_num(value):
    return "N/A" if value is None else f"{value:.2f}"
