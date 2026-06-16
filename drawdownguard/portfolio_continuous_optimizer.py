import random

from .portfolio_constraint_optimizer import (
    ASSET_LIMITS,
    HIGH_VOL_ASSETS,
    HIGH_VOL_LIMIT,
    MAX_DRAWDOWN_LIMIT,
    MIN_BULLET_CASH_WEIGHT,
    _asset_metrics,
    check_constraints,
    evaluate_candidate,
    score_portfolio,
)


def run_portfolio_continuous_optimizer(portfolio_report, dca_report, discrete_report=None, preset="quick", seed=42):
    assets = _asset_metrics(portfolio_report, dca_report)
    asset_ids = [asset_id for asset_id in ASSET_LIMITS if asset_id in assets]
    iterations = 50 if preset == "quick" else 180
    population_size = max(20, len(asset_ids) * (6 if preset == "quick" else 14))
    best = differential_evolution_optimize(assets, asset_ids, iterations, population_size, seed)
    discrete_best = (discrete_report or {}).get("recommendations", {}).get("best_portfolio") or {}
    discrete_return = discrete_best.get("return", 0)
    continuous_return = best.get("return", 0)
    sensitivity = sensitivity_analysis(best.get("asset_weights", {}), assets)
    active = active_constraints(best)
    return {
        "preset": preset,
        "seed": seed,
        "method": "differential_evolution",
        "iterations": iterations,
        "population_size": population_size,
        "asset_weights": best.get("asset_weights", {}),
        "discrete_comparison": {
            "discrete_optimal_return": discrete_return,
            "continuous_optimal_return": continuous_return,
            "improvement_delta": continuous_return - discrete_return,
            "discrete_candidate_id": discrete_best.get("candidate_id"),
        },
        "risk_metrics": {
            "max_drawdown": best.get("drawdown", 0),
            "volatility": best.get("volatility", 0),
            "sharpe_like_ratio": best.get("sharpe", None),
            "score": best.get("score", 0),
        },
        "constraints": best.get("constraints", {}),
        "active_constraints": active,
        "sensitivity_analysis": sensitivity,
        "conclusion": build_conclusion(best, discrete_return, sensitivity, active),
    }


def differential_evolution_optimize(assets, asset_ids, iterations=50, population_size=20, seed=42):
    rng = random.Random(seed)
    population = [_random_weights(asset_ids, rng) for _ in range(population_size)]
    scored = [_penalized_candidate(weights, assets) for weights in population]
    factor = 0.7
    crossover_rate = 0.8

    for _ in range(iterations):
        next_scored = []
        for index, current in enumerate(scored):
            choices = [item for idx, item in enumerate(scored) if idx != index]
            a, b, c = rng.sample(choices, 3)
            trial_vector = {}
            force_asset = rng.choice(asset_ids)
            for asset_id in asset_ids:
                use_mutation = rng.random() < crossover_rate or asset_id == force_asset
                if use_mutation:
                    value = (
                        a["asset_weights"].get(asset_id, 0)
                        + factor * (b["asset_weights"].get(asset_id, 0) - c["asset_weights"].get(asset_id, 0))
                    )
                else:
                    value = current["asset_weights"].get(asset_id, 0)
                trial_vector[asset_id] = value
            trial_weights = project_weights(trial_vector, asset_ids)
            trial = _penalized_candidate(trial_weights, assets)
            next_scored.append(trial if trial["optimization_score"] > current["optimization_score"] else current)
        scored = next_scored
    return max(scored, key=lambda item: item["optimization_score"])


def project_weights(weights, asset_ids):
    projected = {asset_id: max(0, float(weights.get(asset_id, 0))) for asset_id in asset_ids}
    if sum(projected.values()) <= 0:
        projected = {asset_id: 1 / len(asset_ids) for asset_id in asset_ids}
    projected = _normalize(projected)
    capped = {}
    remaining_ids = list(asset_ids)
    remaining_mass = 1.0
    while remaining_ids:
        over = [asset_id for asset_id in remaining_ids if projected.get(asset_id, 0) * remaining_mass > ASSET_LIMITS[asset_id]]
        if not over:
            total = sum(projected.get(asset_id, 0) for asset_id in remaining_ids)
            for asset_id in remaining_ids:
                capped[asset_id] = remaining_mass * projected.get(asset_id, 0) / total if total else 0
            break
        for asset_id in over:
            capped[asset_id] = ASSET_LIMITS[asset_id]
            remaining_mass -= ASSET_LIMITS[asset_id]
            remaining_ids.remove(asset_id)
        projected = _normalize({asset_id: projected.get(asset_id, 0) for asset_id in remaining_ids})
    return _normalize(capped)


def sensitivity_analysis(weights, assets):
    baseline = evaluate_candidate(weights, assets)
    rows = []
    for asset_id in weights:
        for direction, multiplier in [("plus_10pct", 1.10), ("minus_10pct", 0.90)]:
            perturbed = dict(weights)
            perturbed[asset_id] = perturbed[asset_id] * multiplier
            perturbed = project_weights(perturbed, list(weights.keys()))
            result = evaluate_candidate(perturbed, assets)
            rows.append(
                {
                    "asset_id": asset_id,
                    "direction": direction,
                    "asset_weights": result["asset_weights"],
                    "return_delta": result["return"] - baseline["return"],
                    "drawdown_delta": result["drawdown"] - baseline["drawdown"],
                    "score_delta": result["score"] - baseline["score"],
                }
            )
    return rows


def active_constraints(candidate, tolerance=0.01):
    weights = candidate.get("asset_weights", {})
    active = []
    for asset_id, limit in ASSET_LIMITS.items():
        if abs(weights.get(asset_id, 0) - limit) <= tolerance:
            active.append(f"{asset_id}_max_weight")
    if abs(candidate.get("drawdown", 0) - MAX_DRAWDOWN_LIMIT) <= tolerance:
        active.append("max_drawdown")
    high_vol = sum(weights.get(asset_id, 0) for asset_id in HIGH_VOL_ASSETS)
    if abs(high_vol - HIGH_VOL_LIMIT) <= tolerance:
        active.append("high_volatility_budget")
    active.append("min_bullet_cash")
    return active


def build_conclusion(best, discrete_return, sensitivity, active):
    improvement = best.get("return", 0) - discrete_return
    stable_assets = [
        item["asset_id"] for item in sensitivity
        if abs(item["return_delta"]) < 0.01 and abs(item["drawdown_delta"]) < 0.01
    ]
    stable_assets = sorted(set(stable_assets))
    local_optimal_note = (
        "差分进化为全局启发式方法，固定 seed 可复现，但仍可能存在局部最优或参数敏感性。"
    )
    pareto_note = (
        "当前解已接近 Pareto frontier。"
        if "max_drawdown" in active or improvement < 0.02
        else "连续优化仍显示存在可改进空间。"
    )
    return {
        "continuous_better_than_discrete": improvement > 0,
        "improvement_material": improvement > 0.02,
        "local_optimum_risk": local_optimal_note,
        "pareto_frontier_assessment": pareto_note,
        "stable_assets": stable_assets,
    }


def summarize_portfolio_continuous_report(report):
    lines = ["Portfolio Continuous Optimizer 摘要"]
    if not report:
        lines.append("暂无连续组合优化报告。")
        return "\n".join(lines)
    comparison = report.get("discrete_comparison", {})
    risk = report.get("risk_metrics", {})
    lines.append(f"method：{report.get('method')} | preset：{report.get('preset')} | seed：{report.get('seed')}")
    lines.append(f"连续最优权重：{_format_weights(report.get('asset_weights', {}))}")
    lines.append(
        f"离散收益 {_fmt_pct(comparison.get('discrete_optimal_return'))} | "
        f"连续收益 {_fmt_pct(comparison.get('continuous_optimal_return'))} | "
        f"改善 {_fmt_pct(comparison.get('improvement_delta'))}"
    )
    lines.append(
        f"最大回撤 {_fmt_pct(risk.get('max_drawdown'))} | "
        f"波动率 {_fmt_pct(risk.get('volatility'))} | "
        f"夏普 {_fmt_num(risk.get('sharpe_like_ratio'))} | score {_fmt_num(risk.get('score'))}"
    )
    constraints = report.get("constraints", {})
    lines.append(f"约束是否全部满足：{constraints.get('all_satisfied')}")
    lines.append(f"active constraints：{', '.join(report.get('active_constraints', [])) or '无'}")
    conclusion = report.get("conclusion", {})
    lines.append(f"连续优化优于离散优化：{conclusion.get('continuous_better_than_discrete')}")
    lines.append(f"局部最优说明：{conclusion.get('local_optimum_risk')}")
    lines.append(f"Pareto 判断：{conclusion.get('pareto_frontier_assessment')}")
    lines.append(f"权重稳定资产：{', '.join(conclusion.get('stable_assets', [])) or '无'}")
    return "\n".join(lines)


def _penalized_candidate(weights, assets):
    candidate = evaluate_candidate(weights, assets)
    penalty = _constraint_penalty(candidate)
    candidate["optimization_score"] = candidate["score"] - penalty
    return candidate


def _constraint_penalty(candidate):
    penalty = 0
    constraints = candidate["constraints"]
    if not constraints.get("drawdown_satisfied"):
        penalty += max(0, candidate["drawdown"] - MAX_DRAWDOWN_LIMIT) * 100
    if not constraints.get("high_volatility_satisfied"):
        penalty += max(0, constraints.get("high_volatility_weight", 0) - 0.70) * 100
    for status in constraints.get("asset_limit_status", {}).values():
        if not status.get("satisfied"):
            penalty += max(0, status["weight"] - status["limit"]) * 100
    return penalty


def _random_weights(asset_ids, rng):
    raw = {asset_id: rng.random() for asset_id in asset_ids}
    return project_weights(raw, asset_ids)


def _normalize(weights):
    total = sum(weights.values())
    if total <= 0:
        return {key: 0 for key in weights}
    return {key: value / total for key, value in weights.items()}


def _format_weights(weights):
    return ", ".join(f"{asset_id} {weight * 100:.2f}%" for asset_id, weight in sorted(weights.items()))


def _fmt_pct(value):
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _fmt_num(value):
    return "N/A" if value is None else f"{value:.2f}"
