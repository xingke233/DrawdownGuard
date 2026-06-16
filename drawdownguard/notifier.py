def format_report(results, config):
    lines = []
    bullet = config["bullet_account"]
    lines.append("基金补仓管家 - 每日检查")
    lines.append(f"子弹仓：{bullet['name']}，余额：{bullet['balance']} 元")
    lines.append("生活账户资金不参与补仓计算")

    for result in results:
        lines.append("━━━━━━━━━━━━━━")
        lines.append(result["fund_name"])
        lines.append(f"数据源：{result.get('data_source', 'unknown')}")
        for warning in result.get("warnings", []):
            lines.append(f"提示：{warning}")
        if result.get("skipped"):
            lines.append("状态：净值数据缺失，已跳过")
            lines.append("建议补仓：无")
            lines.append("执行状态：无待确认")
            continue
        lines.append(f"当前日期：{result['current_date']}")
        lines.append(f"当前净值：{result['current_nav']:.4f}")
        lines.append(f"{config['peak_window_trading_days']}日高点：{result['peak_nav']:.4f}")
        lines.append(f"回撤：{result['drawdown'] * 100:.2f}%")
        lines.append(f"状态：{result['status']}")
        if result["status"] in ("历史回撤", "深度回撤中"):
            lines.append(f"历史回撤：{result['historical_drawdown'] * 100:.2f}%")
        if result.get("advice"):
            lines.append(f"建议：{result['advice']}")

        if result["suggested_amounts"]:
            for level, amount in result["suggested_amounts"].items():
                pending = "待确认" if result["pending_levels"].get(level) else "无"
                lines.append(f"建议补仓：{level}% 档 {amount} 元")
                lines.append(f"执行状态：{pending}")
        elif result["status"] in ("历史回撤", "深度回撤中"):
            lines.append("执行状态：无待确认")
        else:
            lines.append("建议补仓：无")
            lines.append("执行状态：无待确认")

    lines.append("━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_transactions(transactions):
    if not transactions:
        return "暂无执行日志。"

    lines = ["执行日志"]
    for item in transactions:
        lines.append(
            f"{item['date']} | {item['fund']} | {item['level']} | "
            f"{item['amount']} 元 | 净值 {item['nav']:.4f} | 回撤 {item['drawdown'] * 100:.2f}%"
        )
    return "\n".join(lines)


def format_daily_logs(logs, limit=10):
    if not logs:
        return "暂无每日检查日志。"

    recent = sorted(logs, key=lambda item: (item["date"], item["fund_code"]))[-limit:]
    lines = [f"最近{len(recent)}条每日检查日志"]
    for item in recent:
        nav = _format_optional_number(item.get("nav"), precision=4)
        peak_nav = _format_optional_number(item.get("peak_nav"), precision=4)
        drawdown = _format_optional_percent(item.get("drawdown"))
        suggestions = item.get("suggestions") or {}
        if suggestions:
            suggestion_text = ", ".join(
                f"{level}%:{amount}元" for level, amount in suggestions.items()
            )
        else:
            suggestion_text = "无"
        warning_count = len(item.get("warnings", []))
        lines.append(
            f"{item['date']} | {item['fund_code']} | {item['fund_name']} | "
            f"净值 {nav} | 高点 {peak_nav} | 回撤 {drawdown} | 状态 {item['status']} | "
            f"建议 {suggestion_text} | 数据源 {item.get('data_source', 'unknown')} | "
            f"提示 {warning_count}条"
        )
    return "\n".join(lines)


def _format_optional_number(value, precision):
    if value is None:
        return "-"
    return f"{value:.{precision}f}"


def _format_optional_percent(value):
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"
