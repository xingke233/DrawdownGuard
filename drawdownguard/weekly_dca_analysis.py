from copy import deepcopy

from .backtest import PortfolioBacktester


WEEKDAYS = [
    (0, "Monday", "周一"),
    (1, "Tuesday", "周二"),
    (2, "Wednesday", "周三"),
    (3, "Thursday", "周四"),
    (4, "Friday", "周五"),
]


def run_weekly_dca_analysis(config, representative_histories, source="backtest"):
    results = []
    warnings = []

    for weekday, weekday_name, weekday_label in WEEKDAYS:
        scenario_config = deepcopy(config)
        portfolio_config = scenario_config.setdefault("portfolio_backtest", {})
        portfolio_config["dca_weekday"] = weekday

        report = PortfolioBacktester(scenario_config).run(representative_histories)
        summary = report.get("portfolio_summary", {})
        results.append(
            {
                "weekday": weekday,
                "weekday_name": weekday_name,
                "weekday_label": weekday_label,
                "total_invested": summary.get("total_invested", 0),
                "final_market_value": summary.get("final_market_value", 0),
                "total_profit": summary.get("total_profit", 0),
                "total_return_rate": summary.get("total_return_rate", 0),
                "bullet_cash_final": summary.get("bullet_cash_final", 0),
                "trigger_count_total": summary.get("trigger_count_total", 0),
                "skipped_assets": summary.get("skipped_assets", []),
                "asset_returns": [
                    {
                        "asset_id": asset["asset_id"],
                        "asset_name": asset["asset_name"],
                        "status": asset["status"],
                        "total_invested": asset["total_invested"],
                        "final_market_value": asset["final_market_value"],
                        "total_return_rate": asset["total_return_rate"],
                        "trigger_count_total": asset["trigger_count_total"],
                    }
                    for asset in report.get("assets", [])
                ],
            }
        )
        warnings.extend(report.get("warnings", []))

    return {
        "source": source,
        "portfolio_backtest": config.get("portfolio_backtest", {}),
        "results": results,
        "warnings": warnings,
    }


def summarize_weekly_dca_analysis(report):
    lines = ["定投周几回测分析"]
    results = report.get("results", [])
    if not results:
        lines.append("暂无分析结果。")
        return "\n".join(lines)

    for item in results:
        lines.append(
            f"{item['weekday_label']} | "
            f"投入 {item['total_invested']:.2f} 元 | "
            f"市值 {item['final_market_value']:.2f} 元 | "
            f"浮盈亏 {item['total_profit']:.2f} 元 | "
            f"收益率 {item['total_return_rate'] * 100:.2f}% | "
            f"子弹仓剩余 {item['bullet_cash_final']:.2f} 元 | "
            f"触发 {item['trigger_count_total']} 次"
        )

    best = max(results, key=lambda item: item.get("total_return_rate", 0))
    lines.append(f"收益率最高：{best['weekday_label']} {best['total_return_rate'] * 100:.2f}%")
    lines.append("说明：这是基于历史净值、定投和补仓事件的策略模拟收益，不代表真实账户收益。")
    return "\n".join(lines)
