def run_fund_check(config, provider, portfolio_report=None):
    portfolio_config = config.get("portfolio_backtest", {})
    start_date, configured_end_date = _resolve_backtest_range(portfolio_config, portfolio_report)
    fund_names = {fund.get("code"): fund.get("name") for fund in config.get("funds", [])}
    funds = []
    seen_codes = set()

    for asset in portfolio_config.get("assets", []):
        fund_code = asset.get("representative_fund", "")
        if not fund_code or "请先" in fund_code:
            funds.append(_placeholder_result(asset))
            continue
        if fund_code in seen_codes:
            continue
        seen_codes.add(fund_code)
        nav_mode = asset.get("nav_mode", "unit_nav")
        try:
            nav_data = provider.get_full_history(fund_code, nav_mode=nav_mode)
        except TypeError:
            nav_data = provider.get_full_history(fund_code)
        history = nav_data.get("history", [])
        fund_name = fund_names.get(fund_code) or asset.get("fund_name") or asset.get("asset_name") or fund_code
        funds.append(_build_fund_result(asset, fund_code, fund_name, nav_data, history))

    latest_dates = [item["latest_nav_date"] for item in funds if item.get("latest_nav_date")]
    end_date = configured_end_date or (max(latest_dates) if latest_dates else "")

    for item in funds:
        _apply_coverage_check(item, start_date, end_date)

    return {
        "source": "portfolio_backtest",
        "backtest_range": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "funds": funds,
        "warnings": _collect_warnings(funds),
    }


def summarize_fund_check_report(report):
    range_info = report.get("backtest_range", {})
    start_date = range_info.get("start_date") or "N/A"
    end_date = range_info.get("end_date") or "N/A"
    lines = ["Portfolio 基金数据检查"]
    lines.append(f"当前回测区间：{start_date} ~ {end_date}")

    for fund in report.get("funds", []):
        lines.append("")
        lines.append(str(fund.get("fund_code") or "N/A"))
        lines.append(str(fund.get("fund_name") or fund.get("asset_name") or "N/A"))
        lines.append(f"净值口径：{fund.get('nav_mode') or 'unit_nav'}")
        lines.append(f"最早日期：{fund.get('earliest_nav_date') or 'N/A'}")
        lines.append(f"最新日期：{fund.get('latest_nav_date') or 'N/A'}")
        lines.append(f"交易日数：{fund.get('trading_days', 0)}")
        lines.append(f"当前净值：{_format_nav(fund.get('current_nav'))}")
        covered_text = "是" if fund.get("covers_backtest_range") else "否"
        lines.append(f"是否覆盖当前回测区间：{covered_text}")
        for warning in fund.get("warnings", []):
            lines.append(f"WARNING：{warning}")

    return "\n".join(lines)


def _resolve_backtest_range(portfolio_config, portfolio_report):
    if portfolio_report:
        summary = portfolio_report.get("portfolio_summary", {})
        start_date = summary.get("requested_start_date") or summary.get("start_date") or portfolio_config.get("start_date", "")
        end_date = summary.get("requested_end_date") or summary.get("end_date") or portfolio_config.get("end_date")
        return start_date, end_date
    return portfolio_config.get("start_date", ""), portfolio_config.get("end_date")


def _build_fund_result(asset, fund_code, fund_name, nav_data, history):
    if not history:
        return {
            "asset_id": asset.get("asset_id"),
            "asset_name": asset.get("asset_name"),
            "fund_code": fund_code,
            "fund_name": fund_name,
            "nav_mode": nav_data.get("nav_mode", asset.get("nav_mode", "unit_nav")),
            "earliest_nav_date": None,
            "latest_nav_date": None,
            "trading_days": 0,
            "current_nav": None,
            "covers_backtest_range": False,
            "data_source": nav_data.get("source"),
            "warnings": list(nav_data.get("warnings", [])) or ["净值数据缺失。"],
        }

    first = history[0]
    latest = history[-1]
    return {
        "asset_id": asset.get("asset_id"),
        "asset_name": asset.get("asset_name"),
        "fund_code": fund_code,
        "fund_name": fund_name,
        "nav_mode": nav_data.get("nav_mode", asset.get("nav_mode", "unit_nav")),
        "earliest_nav_date": first.get("date"),
        "latest_nav_date": latest.get("date"),
        "trading_days": len(history),
        "current_nav": latest.get("nav"),
        "covers_backtest_range": False,
        "data_source": nav_data.get("source"),
        "warnings": list(nav_data.get("warnings", [])),
    }


def _placeholder_result(asset):
    return {
        "asset_id": asset.get("asset_id"),
        "asset_name": asset.get("asset_name"),
        "fund_code": asset.get("representative_fund"),
        "fund_name": asset.get("asset_name"),
        "nav_mode": asset.get("nav_mode", "unit_nav"),
        "earliest_nav_date": None,
        "latest_nav_date": None,
        "trading_days": 0,
        "current_nav": None,
        "covers_backtest_range": False,
        "data_source": None,
        "warnings": ["代表基金为配置占位或为空，无法检查净值覆盖。"],
    }


def _apply_coverage_check(item, start_date, end_date):
    earliest = item.get("earliest_nav_date")
    latest = item.get("latest_nav_date")
    if not earliest or not latest or not start_date or not end_date:
        item["covers_backtest_range"] = False
        if "净值数据不足，无法判断是否覆盖当前回测区间。" not in item["warnings"]:
            item["warnings"].append("净值数据不足，无法判断是否覆盖当前回测区间。")
        return

    item["covers_backtest_range"] = earliest <= start_date and latest >= end_date
    if earliest > start_date:
        item["warnings"].append(f"基金成立或最早可用净值晚于回测起点 {start_date}。")
    if latest < end_date:
        item["warnings"].append(f"最新净值早于回测终点 {end_date}。")


def _collect_warnings(funds):
    warnings = []
    for fund in funds:
        for warning in fund.get("warnings", []):
            warnings.append(
                {
                    "fund_code": fund.get("fund_code"),
                    "fund_name": fund.get("fund_name"),
                    "warning": warning,
                }
            )
    return warnings


def _format_nav(value):
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)
