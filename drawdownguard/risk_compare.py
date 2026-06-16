from copy import deepcopy
from statistics import pstdev

from .take_profit import TakeProfitBacktester, summarize_take_profit_report


def run_risk_compare(config, history):
    original_config = deepcopy(config)
    take_profit_config = deepcopy(config)

    original_report = TakeProfitBacktester(original_config).run_without_take_profit(history)
    take_profit_report = TakeProfitBacktester(take_profit_config).run(history)
    original_metrics = build_strategy_metrics("original", "原始策略", original_report)
    take_profit_metrics = build_strategy_metrics("take_profit", "阶梯止盈策略", take_profit_report)

    comparison = build_comparison(original_metrics, take_profit_metrics)
    return {
        "strategies": [original_metrics, take_profit_metrics],
        "comparison": comparison,
        "source_reports": {
            "original": original_report,
            "take_profit": take_profit_report,
        },
    }


def build_strategy_metrics(strategy_id, strategy_name, report):
    total_asset_value = report.get("total_asset_value", 0)
    final_cash = report.get("final_cash", 0)
    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "total_invested": report.get("total_dca_invested", 0) + report.get("total_buy_amount", 0),
        "final_market_value": report.get("final_market_value", 0),
        "final_cash": final_cash,
        "total_asset_value": total_asset_value,
        "total_profit": report.get("total_profit", 0),
        "total_return_rate": report.get("total_return_rate", 0),
        "max_drawdown": max_drawdown(report.get("series", [])),
        "volatility": volatility(report.get("series", [])),
        "cash_ratio_final": final_cash / total_asset_value if total_asset_value > 0 else 0,
        "buy_count": report.get("trigger_count_buy", 0),
        "sell_count": report.get("trigger_count_sell", 0),
    }


def build_comparison(original, take_profit):
    return_difference = take_profit["total_return_rate"] - original["total_return_rate"]
    max_drawdown_improvement = take_profit["max_drawdown"] - original["max_drawdown"]
    volatility_reduction = original["volatility"] - take_profit["volatility"]
    conclusion = build_conclusion(return_difference, max_drawdown_improvement, volatility_reduction)
    return {
        "return_rate_difference": return_difference,
        "max_drawdown_improvement": max_drawdown_improvement,
        "volatility_reduction": volatility_reduction,
        "return_tradeoff": -return_difference,
        "conclusion": conclusion,
    }


def summarize_risk_compare_report(report):
    strategies = {item["strategy_id"]: item for item in report.get("strategies", [])}
    original = strategies.get("original", {})
    take_profit = strategies.get("take_profit", {})
    comparison = report.get("comparison", {})
    lines = ["止盈策略风险对比摘要"]
    if not original or not take_profit:
        lines.append("暂无风险对比结果。")
        return "\n".join(lines)

    lines.append(f"原始策略收益率：{original['total_return_rate'] * 100:.2f}%")
    lines.append(f"止盈策略收益率：{take_profit['total_return_rate'] * 100:.2f}%")
    lines.append(f"原始策略最大回撤：{original['max_drawdown'] * 100:.2f}%")
    lines.append(f"止盈策略最大回撤：{take_profit['max_drawdown'] * 100:.2f}%")
    lines.append(f"最大回撤改善幅度：{comparison.get('max_drawdown_improvement', 0) * 100:.2f}%")
    lines.append(f"波动率降低幅度：{comparison.get('volatility_reduction', 0) * 100:.2f}%")
    lines.append(f"收益率差异：{comparison.get('return_rate_difference', 0) * 100:.2f}%")
    lines.append(f"结论：{comparison.get('conclusion', '暂无结论')}")
    lines.append("说明：风险对比为基于历史净值、定投、补仓和止盈事件的策略模拟，不代表真实账户收益。")
    return "\n".join(lines)


def build_conclusion(return_difference, max_drawdown_improvement, volatility_reduction):
    meaningful_risk_reduction = max_drawdown_improvement >= 0.03 or volatility_reduction >= 0.03
    acceptable_return_tradeoff = return_difference >= -0.03
    poor_tradeoff = max_drawdown_improvement < 0.02 and return_difference < -0.03
    if meaningful_risk_reduction and acceptable_return_tradeoff:
        return "止盈有效"
    if poor_tradeoff:
        return "止盈不划算"
    return "需要结合收益和风险偏好判断"


def max_drawdown(series):
    values = [item.get("total_asset_value", item.get("position_market_value", 0) + item.get("cash_after", 0)) for item in series]
    if not values:
        return 0
    peak = values[0]
    result = 0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            result = min(result, value / peak - 1)
    return result


def volatility(series):
    values = [item.get("total_asset_value", item.get("position_market_value", 0) + item.get("cash_after", 0)) for item in series]
    returns = [
        values[index] / values[index - 1] - 1
        for index in range(1, len(values))
        if values[index - 1] > 0
    ]
    return pstdev(returns) if len(returns) > 1 else 0
