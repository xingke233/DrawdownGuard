ASSET_ROLES = {
    "NASDAQ100": "growth",
    "GOLD": "hedge",
    "DIVIDEND_LOW_VOL": "defensive",
    "HSTECH": "satellite",
    "CASHFLOW": "experimental",
}

STRATEGY_WEIGHTS = {
    "growth_leaning": {
        "NASDAQ100": 0.55,
        "HSTECH": 0.10,
        "CASHFLOW": 0.10,
        "DIVIDEND_LOW_VOL": 0.10,
        "GOLD": 0.15,
    },
    "balanced": {
        "NASDAQ100": 0.40,
        "HSTECH": 0.08,
        "CASHFLOW": 0.12,
        "DIVIDEND_LOW_VOL": 0.20,
        "GOLD": 0.20,
    },
    "defensive": {
        "NASDAQ100": 0.25,
        "HSTECH": 0.05,
        "CASHFLOW": 0.15,
        "DIVIDEND_LOW_VOL": 0.30,
        "GOLD": 0.25,
    },
}


def run_portfolio_strategy_synth(portfolio_report, dca_report, audit_reports=None):
    audit_reports = audit_reports or {}
    assets = _build_asset_context(portfolio_report, dca_report, audit_reports)
    strategies = [
        _build_strategy(name, weights, assets)
        for name, weights in STRATEGY_WEIGHTS.items()
    ]
    rankings = {
        "best_strategy_by_return": _strategy_ref(max(strategies, key=lambda item: item["total_return_rate"], default=None)),
        "best_strategy_by_risk": _strategy_ref(max(strategies, key=lambda item: item["max_drawdown"], default=None)),
        "best_strategy_balanced": _strategy_ref(max(strategies, key=lambda item: item["balanced_score"], default=None)),
    }
    conclusion = build_portfolio_conclusion(assets, strategies, rankings)
    return {
        "source_reports": {
            "portfolio_backtest_report": bool(portfolio_report),
            "dca_strategy_report": bool(dca_report),
            "asset_dca_audit_reports": sorted(audit_reports.keys()),
        },
        "asset_roles": {asset_id: item["role"] for asset_id, item in assets.items()},
        "assets": assets,
        "strategies": strategies,
        "rankings": rankings,
        "conclusion": conclusion,
    }


def summarize_portfolio_strategy_report(report):
    lines = ["Portfolio Strategy Synthesizer 摘要"]
    if not report:
        lines.append("暂无组合策略合成报告。")
        return "\n".join(lines)
    conclusion = report.get("conclusion", {})
    rankings = report.get("rankings", {})
    lines.append(f"当前组合结构健康：{conclusion.get('structure_healthy')}")
    lines.append(f"最优收益策略：{_ref_name(rankings.get('best_strategy_by_return'))}")
    lines.append(f"最优风险策略：{_ref_name(rankings.get('best_strategy_by_risk'))}")
    lines.append(f"最优均衡策略：{_ref_name(rankings.get('best_strategy_balanced'))}")
    lines.append(f"冗余资产：{', '.join(conclusion.get('redundant_assets', [])) or '无'}")
    lines.append(f"建议降权：{', '.join(conclusion.get('assets_to_reduce', [])) or '无'}")
    lines.append(f"建议加权：{', '.join(conclusion.get('assets_to_increase', [])) or '无'}")
    lines.append(f"需要核心-卫星结构：{conclusion.get('core_satellite_needed')}")
    lines.append("组合策略：")
    for strategy in report.get("strategies", []):
        lines.append(
            f"- {strategy['strategy_name']} | 收益率 {_fmt_pct(strategy['total_return_rate'])} | "
            f"最大回撤 {_fmt_pct(strategy['max_drawdown'])} | 波动率 {_fmt_pct(strategy['volatility'])} | "
            f"夏普 {_fmt_num(strategy['sharpe_like_ratio'])} | 稳定 {_fmt_num(strategy['stability_score'])} | "
            f"成长 {_fmt_num(strategy['growth_score'])}"
        )
    lines.append(f"结论：{conclusion.get('summary')}")
    return "\n".join(lines)


def classify_asset(asset_id):
    return ASSET_ROLES.get(asset_id, "experimental")


def normalize_weights(weights):
    total = sum(value for value in weights.values() if value > 0)
    if total <= 0:
        return {key: 0 for key in weights}
    return {key: value / total for key, value in weights.items()}


def drawdown_actions(portfolio_drawdown):
    if portfolio_drawdown <= -0.20:
        return {
            "level": "-20%",
            "actions": ["全部资金集中纳指 + 黄金", "暂停卫星资产定投", "削减非核心资产"],
        }
    if portfolio_drawdown <= -0.15:
        return {"level": "-15%", "actions": ["削减非核心资产", "保留核心资产定投"]}
    if portfolio_drawdown <= -0.10:
        return {"level": "-10%", "actions": ["暂停卫星资产定投"]}
    return {"level": "normal", "actions": ["维持当前现金流分配"]}


def calculate_strategy_scores(total_return_rate, max_drawdown, volatility, cash_utilization, growth_weight):
    sharpe_like = total_return_rate / volatility if volatility else None
    stability_score = (1 + max_drawdown) * 0.6 + (1 - volatility) * 0.3 + (1 - cash_utilization) * 0.1
    growth_score = total_return_rate * 0.7 + growth_weight * 0.3
    balanced_score = total_return_rate + max_drawdown - volatility + stability_score * 0.2
    return {
        "sharpe_like_ratio": sharpe_like,
        "stability_score": stability_score,
        "growth_score": growth_score,
        "balanced_score": balanced_score,
    }


def build_portfolio_conclusion(assets, strategies, rankings):
    redundant = [
        asset_id for asset_id, asset in assets.items()
        if asset.get("total_return_rate", 0) <= 0 and asset.get("market_value_weight", 0) < 0.08
    ]
    assets_to_reduce = [
        asset_id for asset_id, asset in assets.items()
        if asset.get("total_return_rate", 0) < 0
        or (asset.get("role") not in ("growth", "hedge") and asset.get("max_drawdown", 0) < -0.25)
    ]
    assets_to_increase = [
        asset_id for asset_id, asset in assets.items()
        if asset.get("role") in ("growth", "hedge") and asset.get("total_return_rate", 0) > 0.2
    ]
    assets_to_reduce = [asset_id for asset_id in assets_to_reduce if asset_id not in assets_to_increase]
    structure_healthy = len(redundant) == 0 and len(assets_to_reduce) <= 1
    return {
        "structure_healthy": structure_healthy,
        "redundant_assets": redundant,
        "assets_to_reduce": assets_to_reduce,
        "assets_to_increase": assets_to_increase,
        "core_satellite_needed": True,
        "summary": (
            "当前组合需要核心-卫星结构统一管理。"
            if not structure_healthy
            else "当前组合结构基本健康，但仍建议用核心-卫星结构管理风险预算。"
        ),
    }


def _build_asset_context(portfolio_report, dca_report, audit_reports):
    context = {}
    dca_assets = {asset.get("asset_id"): asset for asset in dca_report.get("assets", [])}
    for asset in portfolio_report.get("assets", []):
        asset_id = asset.get("asset_id")
        if not asset_id:
            continue
        dca_asset = dca_assets.get(asset_id, {})
        best_strategy = dca_asset.get("best_strategy") or {}
        audit = audit_reports.get(asset_id, {})
        context[asset_id] = {
            "asset_id": asset_id,
            "asset_name": asset.get("asset_name"),
            "role": classify_asset(asset_id),
            "total_invested": asset.get("total_invested", 0),
            "final_market_value": asset.get("final_market_value", 0),
            "total_profit": asset.get("total_profit", 0),
            "total_return_rate": asset.get("total_return_rate", 0),
            "market_value_weight": 0,
            "max_drawdown": _asset_max_drawdown(asset.get("series", [])),
            "volatility": _asset_volatility(asset.get("series", [])),
            "best_dca_strategy": best_strategy,
            "audit_warning_count": len(audit.get("warnings", [])),
        }
    total_value = sum(item["final_market_value"] for item in context.values())
    for item in context.values():
        item["market_value_weight"] = item["final_market_value"] / total_value if total_value else 0
    return context


def _build_strategy(strategy_name, raw_weights, assets):
    weights = normalize_weights({asset_id: raw_weights.get(asset_id, 0) for asset_id in assets})
    total_return = sum(weights[asset_id] * assets[asset_id].get("total_return_rate", 0) for asset_id in weights)
    max_drawdown = sum(weights[asset_id] * assets[asset_id].get("max_drawdown", 0) for asset_id in weights)
    volatility = sum(weights[asset_id] * assets[asset_id].get("volatility", 0) for asset_id in weights)
    growth_weight = sum(weight for asset_id, weight in weights.items() if assets[asset_id].get("role") == "growth")
    cash_utilization = min(1, sum(weight for asset_id, weight in weights.items() if assets[asset_id].get("role") in ("growth", "satellite")))
    scores = calculate_strategy_scores(total_return, max_drawdown, volatility, cash_utilization, growth_weight)
    return {
        "strategy_name": strategy_name,
        "asset_weights": weights,
        "dca_strategy_mapping": {
            asset_id: assets[asset_id].get("best_dca_strategy", {}) for asset_id in weights
        },
        "cash_allocation": _cash_allocation(weights),
        "drawdown_linkage": {
            "-10%": drawdown_actions(-0.10)["actions"],
            "-15%": drawdown_actions(-0.15)["actions"],
            "-20%": drawdown_actions(-0.20)["actions"],
        },
        "total_return_rate": total_return,
        "max_drawdown": max_drawdown,
        "volatility": volatility,
        "cash_utilization": cash_utilization,
        **scores,
    }


def _cash_allocation(weights):
    return {
        "bull_market": {
            "dca_weight": 0.75,
            "bullet_cash_weight": 0.25,
            "note": "减少补仓，提高定投",
        },
        "bear_market": {
            "dca_weight": 0.45,
            "bullet_cash_weight": 0.55,
            "note": "增加补仓",
        },
        "sideways": {
            "dca_weight": 0.60,
            "bullet_cash_weight": 0.40,
            "note": "均衡分配",
        },
        "asset_dca_weights": weights,
    }


def _asset_max_drawdown(series):
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
    return _pstdev(returns)


def _pstdev(values):
    if len(values) <= 1:
        return 0
    mean_value = sum(values) / len(values)
    return (sum((value - mean_value) ** 2 for value in values) / len(values)) ** 0.5


def _strategy_ref(strategy):
    if not strategy:
        return None
    return {
        "strategy_name": strategy["strategy_name"],
        "total_return_rate": strategy["total_return_rate"],
        "max_drawdown": strategy["max_drawdown"],
        "volatility": strategy["volatility"],
        "sharpe_like_ratio": strategy["sharpe_like_ratio"],
        "stability_score": strategy["stability_score"],
        "growth_score": strategy["growth_score"],
        "balanced_score": strategy["balanced_score"],
    }


def _ref_name(ref):
    return ref.get("strategy_name") if ref else "N/A"


def _fmt_pct(value):
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _fmt_num(value):
    return "N/A" if value is None else f"{value:.2f}"
