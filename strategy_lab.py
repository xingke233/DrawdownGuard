from copy import deepcopy

from backtest import PortfolioBacktester


DEFAULT_STRATEGIES = [
    {"strategy_name": "A", "levels": [10, 15, 20]},
    {"strategy_name": "B", "levels": [10, 20, 30]},
    {"strategy_name": "C", "levels": [5, 10, 15]},
    {"strategy_name": "D", "levels": [8, 16, 24]},
]
DEFAULT_CASH_RATIOS = [0.15, 0.25, 0.35]


def run_strategy_lab(config, representative_histories, strategies=None):
    strategies = strategies or DEFAULT_STRATEGIES
    results = []
    warnings = []

    for strategy in strategies:
        scenario_config = _build_strategy_config(config, strategy)
        report = PortfolioBacktester(scenario_config).run(representative_histories)
        summary = report.get("portfolio_summary", {})
        result = {
            "strategy_name": strategy["strategy_name"],
            "drawdown_levels": _format_drawdown_levels(strategy["levels"]),
            "total_return_rate": summary.get("total_return_rate", 0),
            "total_profit": summary.get("total_profit", 0),
            "final_market_value": summary.get("final_market_value", 0),
            "trigger_count": summary.get("trigger_count_total", 0),
            "bullet_cash_remaining": summary.get("bullet_cash_final", 0),
            "max_drawdown": _max_drawdown(report.get("assets", [])),
            "total_bullet_invested": summary.get("total_bullet_invested", 0),
            "total_invested": summary.get("total_invested", 0),
        }
        result["cash_efficiency"] = _cash_efficiency(result)
        results.append(result)
        warnings.extend(report.get("warnings", []))

    return {
        "strategies": results,
        "rankings": build_strategy_lab_rankings(results),
        "warnings": warnings,
    }


def build_strategy_lab_rankings(results):
    return {
        "return_rate": [
            item["strategy_name"]
            for item in sorted(results, key=lambda item: item["total_return_rate"], reverse=True)
        ],
        "cash_efficiency": [
            item["strategy_name"]
            for item in sorted(results, key=lambda item: item["cash_efficiency"], reverse=True)
        ],
        "risk": [
            item["strategy_name"]
            for item in sorted(results, key=lambda item: item["max_drawdown"], reverse=True)
        ],
    }


def summarize_strategy_lab_report(report):
    strategies = report.get("strategies", [])
    lines = ["Strategy Lab 回测摘要"]
    if not strategies:
        lines.append("暂无策略实验结果。")
        return "\n".join(lines)

    for item in strategies:
        lines.append(
            f"{item['strategy_name']} | 档位 {_levels_text(item['drawdown_levels'])} | "
            f"收益率 {item['total_return_rate'] * 100:.2f}% | "
            f"浮盈 {item['total_profit']:.2f} 元 | "
            f"市值 {item['final_market_value']:.2f} 元 | "
            f"触发 {item['trigger_count']} 次 | "
            f"子弹仓剩余 {item['bullet_cash_remaining']:.2f} 元 | "
            f"最大回撤 {item['max_drawdown'] * 100:.2f}%"
        )

    rankings = report.get("rankings", {})
    lines.append(f"收益率排名：{', '.join(rankings.get('return_rate', []))}")
    lines.append(f"现金效率排名：{', '.join(rankings.get('cash_efficiency', []))}")
    lines.append(f"风险排名：{', '.join(rankings.get('risk', []))}")
    lines.append("说明：Strategy Lab 结果为基于历史净值和组合回测规则的策略模拟，不代表真实账户收益。")
    return "\n".join(lines)


def _build_strategy_config(config, strategy):
    scenario_config = deepcopy(config)
    portfolio_config = scenario_config.get("portfolio_backtest", {})
    replacement_levels = _format_drawdown_levels(strategy["levels"])
    for asset in portfolio_config.get("assets", []):
        if asset.get("strategy") == "drawdown_plus_dca":
            asset["drawdown_levels"] = replacement_levels
    return scenario_config


def _format_drawdown_levels(levels):
    return [
        {"level": level, "cash_ratio": DEFAULT_CASH_RATIOS[index]}
        for index, level in enumerate(levels)
    ]


def _max_drawdown(assets):
    drawdowns = [
        item.get("drawdown", 0)
        for asset in assets
        if asset.get("status") == "active"
        for item in asset.get("series", [])
    ]
    return min(drawdowns) if drawdowns else 0


def _cash_efficiency(result):
    bullet_invested = result.get("total_bullet_invested", 0)
    if bullet_invested <= 0:
        return 0
    return result.get("total_profit", 0) / bullet_invested


def _levels_text(levels):
    return "/".join(str(item["level"]) for item in levels)
