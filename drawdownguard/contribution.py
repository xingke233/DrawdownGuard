from statistics import pstdev


def run_contribution_analysis(portfolio_report):
    assets = portfolio_report.get("assets", [])
    summary = portfolio_report.get("portfolio_summary", {})
    total_invested = _to_number(summary.get("total_invested", sum(_to_number(a.get("total_invested")) for a in assets)))
    final_market_value = _to_number(
        summary.get("final_market_value", sum(_to_number(a.get("final_market_value")) for a in assets))
    )
    total_profit = _to_number(summary.get("total_profit", final_market_value - total_invested))
    total_return_rate = _safe_div(total_profit, total_invested, default=0)

    asset_reports = [
        _build_asset_contribution(asset, total_invested, final_market_value, total_profit) for asset in assets
    ]
    active_assets = [asset for asset in asset_reports if asset.get("status") != "skipped"]
    profit_assets = [asset for asset in active_assets if asset.get("total_profit") is not None]
    return_assets = [asset for asset in active_assets if asset.get("total_return_rate") is not None]
    drawdown_assets = [asset for asset in active_assets if asset.get("max_drawdown") is not None]

    best_profit = max(profit_assets, key=lambda item: item["total_profit"], default=None)
    worst_profit = min(profit_assets, key=lambda item: item["total_profit"], default=None)
    highest_return = max(return_assets, key=lambda item: item["total_return_rate"], default=None)
    lowest_return = min(return_assets, key=lambda item: item["total_return_rate"], default=None)
    highest_drawdown = min(drawdown_assets, key=lambda item: item["max_drawdown"], default=None)

    return {
        "source": "portfolio_backtest_report.json",
        "portfolio_summary": {
            "total_invested": total_invested,
            "final_market_value": final_market_value,
            "total_profit": total_profit,
            "total_return_rate": total_return_rate,
            "best_profit_contributor": _asset_ref(best_profit),
            "worst_profit_contributor": _asset_ref(worst_profit),
            "highest_return_asset": _asset_ref(highest_return),
            "lowest_return_asset": _asset_ref(lowest_return),
            "highest_drawdown_asset": _asset_ref(highest_drawdown),
            "conclusion": build_conclusion(asset_reports),
        },
        "assets": asset_reports,
        "warnings": portfolio_report.get("warnings", []),
    }


def summarize_contribution_report(report, detail=False):
    summary = report.get("portfolio_summary", {})
    lines = ["资产贡献分析报告"]
    lines.append(
        f"组合总收益率：{_format_percent(summary.get('total_return_rate'))} | "
        f"总投入：{_format_money(summary.get('total_invested'))} | "
        f"总市值：{_format_money(summary.get('final_market_value'))} | "
        f"总盈亏：{_format_money(summary.get('total_profit'))}"
    )
    lines.append(f"最大收益贡献资产：{_format_asset_ref(summary.get('best_profit_contributor'))}")
    lines.append(f"最大拖累资产：{_format_asset_ref(summary.get('worst_profit_contributor'))}")

    if detail:
        lines.append("资产明细：")
        for asset in report.get("assets", []):
            lines.extend(_detail_lines(asset))
    else:
        lines.append("各资产贡献：")
        for asset in report.get("assets", []):
            lines.append(
                f"- {asset.get('asset_id')} {asset.get('asset_name')} | "
                f"投入 {_format_money(asset.get('total_invested'))} | "
                f"市值 {_format_money(asset.get('final_market_value'))} | "
                f"盈亏 {_format_money(asset.get('total_profit'))} | "
                f"收益贡献 {_format_percent(asset.get('profit_contribution_percent'))} | "
                f"投入权重 {_format_percent(asset.get('investment_weight'))} | "
                f"市值权重 {_format_percent(asset.get('market_value_weight'))} | "
                f"最大回撤 {_format_percent(asset.get('max_drawdown'))} | "
                f"波动率 {_format_percent(asset.get('volatility'))} | "
                f"简化夏普 {_format_optional_number(asset.get('sharpe_like_ratio'))}"
            )

    lines.append("判断：")
    for item in summary.get("conclusion", []):
        lines.append(f"- {item}")
    return "\n".join(lines)


def build_conclusion(assets):
    by_id = {asset.get("asset_id"): asset for asset in assets}
    conclusions = []

    nasdaq = by_id.get("NASDAQ100")
    if nasdaq:
        contribution = nasdaq.get("profit_contribution_percent")
        if contribution is not None and contribution >= 0.5:
            conclusions.append("NASDAQ100 是当前组合的核心收益来源。")
        elif contribution is not None:
            conclusions.append("NASDAQ100 不是唯一收益来源，但仍需结合回撤和波动率判断核心仓位。")
        else:
            conclusions.append("NASDAQ100 数据不足，暂不能判断是否为核心收益来源。")

    gold = by_id.get("GOLD")
    if gold:
        if _to_number(gold.get("total_profit")) > 0 and _abs_or_large(gold.get("max_drawdown")) <= 0.2:
            conclusions.append("GOLD 当前表现为有效防守资产。")
        elif gold.get("max_drawdown") is None:
            conclusions.append("GOLD 风险数据不足，暂不能判断防守效果。")
        else:
            conclusions.append("GOLD 防守效果需要继续观察，当前回撤或收益贡献不够理想。")

    dividend = by_id.get("DIVIDEND_LOW_VOL")
    if dividend:
        if _to_number(dividend.get("total_profit")) < 0:
            conclusions.append("DIVIDEND_LOW_VOL 当前拖累组合收益。")
        else:
            conclusions.append("DIVIDEND_LOW_VOL 当前未明显拖累组合，但需继续观察收益贡献。")

    cashflow = by_id.get("CASHFLOW")
    if cashflow:
        if _to_number(cashflow.get("total_profit")) > 0 and _abs_or_large(cashflow.get("max_drawdown")) <= 0.15:
            conclusions.append("CASHFLOW 当前贡献较稳定收益。")
        elif cashflow.get("max_drawdown") is None:
            conclusions.append("CASHFLOW 数据不足，暂不能判断稳定性。")
        else:
            conclusions.append("CASHFLOW 的稳定收益特征不明显，需要继续观察。")

    hstech = by_id.get("HSTECH")
    if hstech:
        if _abs_or_large(hstech.get("max_drawdown")) >= 0.25 or _to_number(hstech.get("total_return_rate")) < 0:
            conclusions.append("HSTECH 更适合作为小仓位卫星资产。")
        else:
            conclusions.append("HSTECH 当前未显示明显拖累，但仍属于高波动卫星资产。")

    return conclusions


def _build_asset_contribution(asset, portfolio_invested, portfolio_value, portfolio_profit):
    total_invested = _to_number(asset.get("total_invested"))
    final_market_value = _to_number(asset.get("final_market_value"))
    total_profit = _to_number(asset.get("total_profit", final_market_value - total_invested))
    total_return_rate = _safe_div(total_profit, total_invested, default=0)
    risk_series = _asset_risk_series(asset)
    max_dd = _max_drawdown(risk_series)
    vol = _volatility(risk_series)

    warnings = []
    if len(risk_series) < 2:
        warnings.append("风险指标数据不足，最大回撤和波动率可能不具备参考意义。")

    return {
        "asset_id": asset.get("asset_id"),
        "asset_name": asset.get("asset_name"),
        "representative_fund": asset.get("representative_fund"),
        "status": asset.get("status"),
        "skip_reason": asset.get("skip_reason"),
        "total_invested": total_invested,
        "final_market_value": final_market_value,
        "total_profit": total_profit,
        "total_return_rate": total_return_rate,
        "profit_contribution_amount": total_profit,
        "profit_contribution_percent": _safe_div(total_profit, portfolio_profit),
        "investment_weight": _safe_div(total_invested, portfolio_invested, default=0),
        "market_value_weight": _safe_div(final_market_value, portfolio_value, default=0),
        "max_drawdown": max_dd,
        "volatility": vol,
        "sharpe_like_ratio": _safe_div(total_return_rate, vol) if vol else None,
        "event_count": len(asset.get("events", [])),
        "series_count": len(asset.get("series", [])),
        "warnings": warnings,
    }


def _asset_risk_series(asset):
    series = asset.get("series", [])
    if not series:
        return []

    events_by_date = {}
    for event in asset.get("events", []):
        events_by_date.setdefault(event.get("date"), []).append(event)

    values = []
    shares = 0
    has_events = bool(asset.get("events"))
    for row in sorted(series, key=lambda item: item.get("date", "")):
        for event in events_by_date.get(row.get("date"), []):
            shares += _to_number(event.get("shares"))
        nav = _to_number(row.get("nav"))
        if has_events:
            value = shares * nav
            if value > 0:
                values.append(value)
        elif nav > 0:
            values.append(nav)

    if len(values) >= 2:
        return values
    return [_to_number(row.get("nav")) for row in series if _to_number(row.get("nav")) > 0]


def _max_drawdown(values):
    if len(values) < 2:
        return None
    peak = values[0]
    max_dd = 0
    for value in values:
        if value > peak:
            peak = value
        if peak:
            max_dd = min(max_dd, (value - peak) / peak)
    return max_dd


def _volatility(values):
    if len(values) < 3:
        return 0
    returns = []
    previous = values[0]
    for value in values[1:]:
        if previous > 0:
            returns.append((value - previous) / previous)
        previous = value
    if len(returns) < 2:
        return 0
    return pstdev(returns)


def _asset_ref(asset):
    if not asset:
        return None
    return {
        "asset_id": asset.get("asset_id"),
        "asset_name": asset.get("asset_name"),
        "value": asset.get("total_profit"),
    }


def _detail_lines(asset):
    lines = [
        f"- {asset.get('asset_id')} {asset.get('asset_name')}",
        f"  状态：{asset.get('status') or 'unknown'}",
        f"  事件数量：{asset.get('event_count', 0)} | 序列天数：{asset.get('series_count', 0)}",
        (
            f"  投入：{_format_money(asset.get('total_invested'))} | "
            f"市值：{_format_money(asset.get('final_market_value'))} | "
            f"盈亏：{_format_money(asset.get('total_profit'))} | "
            f"收益率：{_format_percent(asset.get('total_return_rate'))}"
        ),
        (
            f"  收益贡献：{_format_percent(asset.get('profit_contribution_percent'))} | "
            f"投入权重：{_format_percent(asset.get('investment_weight'))} | "
            f"市值权重：{_format_percent(asset.get('market_value_weight'))}"
        ),
        (
            f"  最大回撤：{_format_percent(asset.get('max_drawdown'))} | "
            f"波动率：{_format_percent(asset.get('volatility'))} | "
            f"简化夏普：{_format_optional_number(asset.get('sharpe_like_ratio'))}"
        ),
    ]
    for warning in asset.get("warnings", []):
        lines.append(f"  数据提示：{warning}")
    if asset.get("skip_reason"):
        lines.append(f"  跳过原因：{asset.get('skip_reason')}")
    return lines


def _safe_div(numerator, denominator, default=None):
    denominator = _to_number(denominator)
    if denominator == 0:
        return default
    return _to_number(numerator) / denominator


def _to_number(value):
    if value is None:
        return 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def _abs_or_large(value):
    if value is None:
        return 999
    return abs(value)


def _format_money(value):
    return f"{_to_number(value):.2f}"


def _format_percent(value):
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def _format_optional_number(value):
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def _format_asset_ref(ref):
    if not ref:
        return "N/A"
    return f"{ref.get('asset_id')} {ref.get('asset_name')} ({_format_money(ref.get('value'))})"
