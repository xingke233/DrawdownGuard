from datetime import date, timedelta
from statistics import mean, median


ALIPAY_PERFORMANCE_HINTS = {
    "008163": 0.8816,
}


def run_asset_dca_audit(config, provider, query, portfolio_report=None):
    portfolio_config = config.get("portfolio_backtest", {})
    asset = find_portfolio_asset(portfolio_config, query)
    if not asset:
        raise ValueError(f"未找到资产或基金代码：{query}")

    fund_code = asset.get("representative_fund", "")
    fund_name = _fund_name(config, fund_code, asset)
    nav_mode = asset.get("nav_mode", "unit_nav")
    start_date, end_date = _resolve_backtest_range(portfolio_config, portfolio_report)
    portfolio_asset = _find_portfolio_report_asset(portfolio_report, asset.get("asset_id"), fund_code)
    nav_data = _get_full_history(provider, fund_code, nav_mode)
    unit_nav_data = _get_full_history(provider, fund_code, "unit_nav")
    full_history = nav_data.get("history", [])
    fallback_warnings = []
    if not full_history and portfolio_asset and portfolio_asset.get("series"):
        full_history = [
            {"date": item["date"], "nav": item["nav"]}
            for item in portfolio_asset.get("series", [])
            if item.get("date") and item.get("nav") is not None
        ]
        fallback_warnings.append("实时/本地净值缺失，已使用 portfolio_backtest_report.json 中的资产 series 进行审计。")
    history = [
        item for item in full_history
        if item.get("date") >= start_date and (not end_date or item.get("date") <= end_date)
    ]
    if not history and full_history:
        history = [item for item in full_history if not end_date or item.get("date") <= end_date]

    unit_check = _build_nav_profile_check(provider, fund_code, unit_nav_data.get("history", []), nav_mode)
    dca_audit = _simulate_dca(asset, history, start_date, end_date, portfolio_config)
    high_buy = _high_buy_diagnosis(dca_audit.get("buy_records", []), dca_audit.get("final_nav"))
    fund_comparison = _fund_comparison(full_history, history, dca_audit)

    warnings = []
    warnings.extend(nav_data.get("warnings", []))
    warnings.extend(fallback_warnings)
    warnings.extend(unit_check.get("warnings", []))
    warnings.extend(dca_audit.get("warnings", []))
    warnings.extend(high_buy.get("warnings", []))
    warnings.extend(_data_issue_warnings(fund_code, unit_check, dca_audit, start_date, full_history))

    report = {
        "asset_id": asset.get("asset_id"),
        "asset_name": asset.get("asset_name"),
        "representative_fund": fund_code,
        "fund_name": fund_name,
        "strategy": asset.get("strategy", "dca_only"),
        "weekly_dca_amount": int(asset.get("weekly_dca_amount", 0)),
        "nav_mode": nav_data.get("nav_mode", nav_mode),
        "backtest_start_date": start_date,
        "backtest_end_date": end_date or (history[-1]["date"] if history else None),
        "earliest_nav_date": full_history[0]["date"] if full_history else None,
        "latest_nav_date": full_history[-1]["date"] if full_history else None,
        "total_nav_records": len(full_history),
        "nav_source": nav_data.get("source"),
        "nav_profile_check": unit_check,
        "dca_audit": dca_audit,
        "buy_record_samples": {
            "first_10": dca_audit.get("buy_records", [])[:10],
            "last_10": dca_audit.get("buy_records", [])[-10:],
        },
        "high_buy_diagnosis": high_buy,
        "fund_vs_dca_comparison": fund_comparison,
        "portfolio_report_asset": _compact_portfolio_asset(portfolio_asset),
        "warnings": warnings,
    }
    return report


def find_portfolio_asset(portfolio_config, query):
    query = str(query)
    for asset in portfolio_config.get("assets", []):
        if query == asset.get("asset_id") or query == asset.get("representative_fund"):
            return asset
    return None


def summarize_asset_dca_audit(report):
    lines = ["资产定投审计报告"]
    lines.append("基础信息")
    lines.append(f"asset_id：{report.get('asset_id')}")
    lines.append(f"asset_name：{report.get('asset_name')}")
    lines.append(f"representative_fund：{report.get('representative_fund')}")
    lines.append(f"fund_name：{report.get('fund_name')}")
    lines.append(f"strategy：{report.get('strategy')}")
    lines.append(f"weekly_dca_amount：{report.get('weekly_dca_amount')}")
    lines.append(f"nav_mode：{report.get('nav_mode')}")
    lines.append(f"回测开始日期：{report.get('backtest_start_date')}")
    lines.append(f"回测结束日期：{report.get('backtest_end_date')}")
    lines.append(f"最早可用净值日期：{report.get('earliest_nav_date')}")
    lines.append(f"最新净值日期：{report.get('latest_nav_date')}")
    lines.append(f"总净值记录数：{report.get('total_nav_records')}")

    nav_check = report.get("nav_profile_check", {})
    lines.append("净值口径检查")
    lines.append(f"使用的净值字段名称：{nav_check.get('unit_nav_field_name')}")
    lines.append(f"是否为单位净值：{_yes_no(nav_check.get('is_unit_nav'))}")
    lines.append(f"尝试获取累计净值：{nav_check.get('accumulated_nav_status')}")
    lines.append(f"尝试获取累计收益率：{nav_check.get('accumulated_return_status')}")
    lines.append(f"unit_nav_start：{_format_number(nav_check.get('unit_nav_start'))}")
    lines.append(f"unit_nav_end：{_format_number(nav_check.get('unit_nav_end'))}")
    lines.append(f"unit_nav_return：{_format_percent(nav_check.get('unit_nav_return'))}")
    lines.append(f"accumulated_nav_start：{_format_number(nav_check.get('accumulated_nav_start'))}")
    lines.append(f"accumulated_nav_end：{_format_number(nav_check.get('accumulated_nav_end'))}")
    lines.append(f"accumulated_nav_return：{_format_percent(nav_check.get('accumulated_nav_return'))}")

    dca = report.get("dca_audit", {})
    lines.append("定投买入审计")
    lines.append(f"buy_count：{dca.get('buy_count', 0)}")
    lines.append(f"first_buy_date：{dca.get('first_buy_date')}")
    lines.append(f"last_buy_date：{dca.get('last_buy_date')}")
    lines.append(f"total_invested：{_format_money(dca.get('total_invested'))}")
    lines.append(f"total_shares：{_format_number(dca.get('total_shares'))}")
    lines.append(f"average_cost：{_format_number(dca.get('average_cost'))}")
    lines.append(f"final_nav：{_format_number(dca.get('final_nav'))}")
    lines.append(f"final_market_value：{_format_money(dca.get('final_market_value'))}")
    lines.append(f"total_profit：{_format_money(dca.get('total_profit'))}")
    lines.append(f"total_return_rate：{_format_percent(dca.get('total_return_rate'))}")

    lines.append("定投记录抽样：前 10 笔")
    lines.extend(_format_buy_records(report.get("buy_record_samples", {}).get("first_10", [])))
    lines.append("定投记录抽样：后 10 笔")
    lines.extend(_format_buy_records(report.get("buy_record_samples", {}).get("last_10", [])))

    high_buy = report.get("high_buy_diagnosis", {})
    lines.append("高位买入诊断")
    lines.append(f"min_buy_nav：{_format_number(high_buy.get('min_buy_nav'))}")
    lines.append(f"max_buy_nav：{_format_number(high_buy.get('max_buy_nav'))}")
    lines.append(f"median_buy_nav：{_format_number(high_buy.get('median_buy_nav'))}")
    lines.append(f"average_buy_nav：{_format_number(high_buy.get('average_buy_nav'))}")
    lines.append(f"buys_above_final_nav_count：{high_buy.get('buys_above_final_nav_count', 0)}")
    lines.append(f"buys_above_final_nav_percent：{_format_percent(high_buy.get('buys_above_final_nav_percent'))}")
    if high_buy.get("explanation"):
        lines.append(high_buy["explanation"])

    comparison = report.get("fund_vs_dca_comparison", {})
    lines.append("与基金自身涨幅对比")
    lines.append(f"fund_start_nav：{_format_number(comparison.get('fund_start_nav'))}")
    lines.append(f"fund_final_nav：{_format_number(comparison.get('fund_final_nav'))}")
    lines.append(f"fund_lump_sum_return：{_format_percent(comparison.get('fund_lump_sum_return'))}")
    lines.append(f"dca_return：{_format_percent(comparison.get('dca_return'))}")
    lines.append(
        "difference_between_lump_sum_and_dca："
        f"{_format_percent(comparison.get('difference_between_lump_sum_and_dca'))}"
    )
    lines.append("成立来业绩走势代表一次性持有收益；DCA 回测代表分批买入收益，两者不一定相同。")

    if report.get("warnings"):
        lines.append("可能的数据问题")
        for warning in report["warnings"]:
            lines.append(f"WARNING：{warning}")
    return "\n".join(lines)


def _simulate_dca(asset, history, start_date, end_date, portfolio_config):
    if not history:
        return {
            "buy_count": 0,
            "first_buy_date": None,
            "last_buy_date": None,
            "total_invested": 0,
            "total_shares": 0,
            "average_cost": None,
            "final_nav": None,
            "final_market_value": 0,
            "total_profit": 0,
            "total_return_rate": 0,
            "buy_records": [],
            "warnings": ["净值数据缺失，无法模拟定投。"],
        }

    amount = int(asset.get("weekly_dca_amount", 0))
    dca_weekday = int(portfolio_config.get("dca_weekday", 0))
    next_dca_date = _initial_dca_date(start_date, history[0]["date"], dca_weekday)
    buy_records = []
    total_invested = 0
    total_shares = 0

    for row in history:
        current = date.fromisoformat(row["date"])
        if current < next_dca_date:
            continue
        if amount > 0:
            nav = float(row["nav"])
            shares = amount / nav if nav else 0
            total_invested += amount
            total_shares += shares
            buy_records.append(
                {
                    "date": row["date"],
                    "nav": nav,
                    "amount": amount,
                    "shares": shares,
                    "cumulative_invested": total_invested,
                    "cumulative_shares": total_shares,
                    "average_cost_after_buy": total_invested / total_shares if total_shares else None,
                }
            )
        next_dca_date += timedelta(days=7)
        while current >= next_dca_date:
            next_dca_date += timedelta(days=7)

    final_nav = float(history[-1]["nav"])
    final_market_value = total_shares * final_nav
    total_profit = final_market_value - total_invested
    warnings = []
    if date.fromisoformat(start_date) < date.fromisoformat(history[0]["date"]):
        warnings.append(f"回测开始日早于基金最早净值日 {history[0]['date']}，实际从可用净值开始。")
    if len(buy_records) < 10:
        warnings.append("买入次数异常少，请检查回测区间、交易日数据或 weekly_dca_amount。")
    return {
        "buy_count": len(buy_records),
        "first_buy_date": buy_records[0]["date"] if buy_records else None,
        "last_buy_date": buy_records[-1]["date"] if buy_records else None,
        "total_invested": total_invested,
        "total_shares": total_shares,
        "average_cost": total_invested / total_shares if total_shares else None,
        "final_nav": final_nav,
        "final_market_value": final_market_value,
        "total_profit": total_profit,
        "total_return_rate": total_profit / total_invested if total_invested else 0,
        "buy_records": buy_records,
        "warnings": warnings,
    }


def _build_nav_profile_check(provider, fund_code, unit_history, selected_nav_mode):
    unit_start = float(unit_history[0]["nav"]) if unit_history else None
    unit_end = float(unit_history[-1]["nav"]) if unit_history else None
    accumulated_nav = _try_fetch_real_nav_series(provider, fund_code, "累计净值走势", ["累计净值", "accumulated_nav"])
    accumulated_return = _try_fetch_real_nav_series(provider, fund_code, "累计收益率走势", ["累计收益率", "收益率"])
    acc_start = accumulated_nav["history"][0]["nav"] if accumulated_nav["history"] else None
    acc_end = accumulated_nav["history"][-1]["nav"] if accumulated_nav["history"] else None
    unit_return = _return_rate(unit_start, unit_end)
    acc_return = _return_rate(acc_start, acc_end)
    warnings = []
    if acc_return is not None and unit_return is not None and acc_return - unit_return > 0.2:
        warnings.append("该基金可能存在分红或复权影响，单位净值回测可能低估收益。")
    return {
        "unit_nav_field_name": "单位净值",
        "is_unit_nav": True,
        "selected_nav_mode": selected_nav_mode,
        "accumulated_nav_status": accumulated_nav["status"],
        "accumulated_return_status": accumulated_return["status"],
        "unit_nav_start": unit_start,
        "unit_nav_end": unit_end,
        "unit_nav_return": unit_return,
        "accumulated_nav_start": acc_start,
        "accumulated_nav_end": acc_end,
        "accumulated_nav_return": acc_return,
        "accumulated_return_latest": accumulated_return["history"][-1]["nav"] if accumulated_return["history"] else None,
        "warnings": [*accumulated_nav["warnings"], *accumulated_return["warnings"], *warnings],
    }


def _try_fetch_real_nav_series(provider, fund_code, indicator, value_keys):
    try:
        akshare = provider.akshare_client
        if akshare is None:
            import akshare
        data_frame = akshare.fund_open_fund_info_em(symbol=fund_code, indicator=indicator)
        records = data_frame.to_dict("records")
        history = []
        for item in records:
            date_value = _first_present(item, ["净值日期", "日期", "date"])
            nav_value = _first_present(item, value_keys)
            if date_value is None or nav_value is None:
                continue
            history.append({"date": str(date_value)[:10], "nav": float(nav_value)})
        history = sorted(history, key=lambda item: item["date"])
        return {"status": "success" if history else "empty", "history": history, "warnings": []}
    except Exception as exc:
        return {"status": "failed", "history": [], "warnings": [f"{indicator} 获取失败：{exc}"]}


def _get_full_history(provider, fund_code, nav_mode):
    try:
        return provider.get_full_history(fund_code, nav_mode=nav_mode)
    except TypeError:
        return provider.get_full_history(fund_code)


def _high_buy_diagnosis(buy_records, final_nav):
    if not buy_records or final_nav is None:
        return {
            "min_buy_nav": None,
            "max_buy_nav": None,
            "median_buy_nav": None,
            "average_buy_nav": None,
            "buys_above_final_nav_count": 0,
            "buys_above_final_nav_percent": 0,
            "explanation": None,
            "warnings": [],
        }
    navs = [item["nav"] for item in buy_records]
    above_count = sum(1 for nav in navs if nav > final_nav)
    above_percent = above_count / len(navs)
    explanation = None
    warnings = []
    if above_percent >= 0.5:
        explanation = "基金成立来涨幅为正，但定投收益可能较差，因为较多资金投入在阶段高位。"
        warnings.append(explanation)
    return {
        "min_buy_nav": min(navs),
        "max_buy_nav": max(navs),
        "median_buy_nav": median(navs),
        "average_buy_nav": mean(navs),
        "buys_above_final_nav_count": above_count,
        "buys_above_final_nav_percent": above_percent,
        "explanation": explanation,
        "warnings": warnings,
    }


def _fund_comparison(full_history, history, dca_audit):
    comparison_history = history or full_history
    start_nav = float(comparison_history[0]["nav"]) if comparison_history else None
    final_nav = float(comparison_history[-1]["nav"]) if comparison_history else None
    lump_sum_return = _return_rate(start_nav, final_nav)
    dca_return = dca_audit.get("total_return_rate")
    return {
        "fund_start_nav": start_nav,
        "fund_final_nav": final_nav,
        "fund_lump_sum_return": lump_sum_return,
        "dca_return": dca_return,
        "difference_between_lump_sum_and_dca": (
            lump_sum_return - dca_return if lump_sum_return is not None and dca_return is not None else None
        ),
    }


def _data_issue_warnings(fund_code, nav_check, dca_audit, start_date, full_history):
    warnings = []
    average_cost = dca_audit.get("average_cost")
    final_nav = dca_audit.get("final_nav")
    fund_code_hint = ALIPAY_PERFORMANCE_HINTS.get(str(fund_code))
    if final_nav is not None and average_cost is not None and final_nav < average_cost:
        warnings.append("final_nav < average_cost，当前定投账面收益为负。")

    unit_return = nav_check.get("unit_nav_return")
    alipay_hint = fund_code_hint
    if unit_return is not None and alipay_hint is not None and abs(unit_return - alipay_hint) > 0.2:
        warnings.append("unit_nav_return 与支付宝显示的成立来涨幅差距大于 20%。")

    acc_return = nav_check.get("accumulated_nav_return")
    if acc_return is not None and unit_return is not None and acc_return - unit_return > 0.2:
        warnings.append("累计净值收益率明显高于单位净值收益率，可能需要使用累计净值或复权净值排查分红影响。")
    if full_history and start_date and start_date < full_history[0]["date"]:
        warnings.append("回测开始日早于基金最早净值日。")
    return warnings


def _resolve_backtest_range(portfolio_config, portfolio_report):
    if portfolio_report:
        summary = portfolio_report.get("portfolio_summary", {})
        return (
            summary.get("requested_start_date") or summary.get("start_date") or portfolio_config.get("start_date", ""),
            summary.get("requested_end_date") or summary.get("end_date") or portfolio_config.get("end_date"),
        )
    return portfolio_config.get("start_date", ""), portfolio_config.get("end_date")


def _initial_dca_date(start_date, first_history_date, dca_weekday):
    requested_start = date.fromisoformat(start_date)
    first_available = date.fromisoformat(first_history_date)
    if (first_available - requested_start).days > 7:
        return first_available
    return _next_weekday(requested_start, dca_weekday)


def _next_weekday(start, weekday):
    days = (weekday - start.weekday()) % 7
    return start + timedelta(days=days)


def _find_portfolio_report_asset(portfolio_report, asset_id, fund_code):
    if not portfolio_report:
        return None
    for asset in portfolio_report.get("assets", []):
        if asset.get("asset_id") == asset_id or asset.get("representative_fund") == fund_code:
            return asset
    return None


def _compact_portfolio_asset(asset):
    if not asset:
        return None
    return {
        "total_invested": asset.get("total_invested"),
        "final_market_value": asset.get("final_market_value"),
        "total_profit": asset.get("total_profit"),
        "total_return_rate": asset.get("total_return_rate"),
        "event_count": len(asset.get("events", [])),
        "series_count": len(asset.get("series", [])),
    }


def _fund_name(config, fund_code, asset):
    for fund in config.get("funds", []):
        if fund.get("code") == fund_code:
            return fund.get("name")
    return asset.get("fund_name") or asset.get("asset_name") or fund_code


def _return_rate(start, end):
    if start in (None, 0) or end is None:
        return None
    return (end - start) / start


def _first_present(item, keys):
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _format_buy_records(records):
    if not records:
        return ["- 无"]
    return [
        "- "
        f"{item['date']} | nav {item['nav']:.4f} | amount {item['amount']:.2f} | "
        f"shares {item['shares']:.4f} | cumulative_invested {item['cumulative_invested']:.2f} | "
        f"cumulative_shares {item['cumulative_shares']:.4f} | "
        f"average_cost_after_buy {_format_number(item['average_cost_after_buy'])}"
        for item in records
    ]


def _format_money(value):
    return "N/A" if value is None else f"{float(value):.2f}"


def _format_number(value):
    return "N/A" if value is None else f"{float(value):.4f}"


def _format_percent(value):
    return "N/A" if value is None else f"{float(value) * 100:.2f}%"


def _yes_no(value):
    return "是" if value else "否"
