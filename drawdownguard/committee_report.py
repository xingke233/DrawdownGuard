from datetime import date

from .real_config import summarize_holdings


MISSING_TEXT = "暂无数据，请先运行对应命令。"

COMMITTEE_ASSET_ORDER = [
    "NASDAQ100",
    "HSTECH",
    "CASHFLOW",
    "DIVIDEND_LOW_VOL",
    "GOLD",
    "BONDS",
    "ACTIVE_ADVANCED_MANUFACTURING",
    "NONFERROUS_METALS",
]


def build_committee_report(
    config,
    policy_check_report=None,
    daily_logs=None,
    portfolio_backtest_report=None,
    contribution_report=None,
    rebalance_advice=None,
    daily_run_report=None,
    quant_signal_report=None,
    watchlist_report=None,
    plain=False,
):
    daily_logs = daily_logs or []
    portfolio_backtest_report = portfolio_backtest_report or {}
    contribution_report = contribution_report or {}
    rebalance_advice = rebalance_advice or {}
    policy_check_report = policy_check_report or {}
    daily_run_report = daily_run_report or {}
    quant_signal_report = quant_signal_report or {}
    watchlist_report = watchlist_report or {}

    sections = {
        "account_overview": build_account_overview(config),
        "holdings_structure": build_holdings_structure(config),
        "daily_drawdown_check": build_daily_drawdown_check(config, daily_logs),
        "portfolio_backtest_summary": build_portfolio_backtest_summary(portfolio_backtest_report),
        "contribution_analysis": build_contribution_summary(contribution_report),
        "rebalance_advice": build_rebalance_summary(rebalance_advice),
        "quant_signal": build_quant_signal_summary(quant_signal_report),
        "watchlist": build_watchlist_summary(watchlist_report),
        "committee_conclusion": build_committee_conclusion(config, rebalance_advice, contribution_report),
        "risk_disclosure": [
            "历史回测不代表未来收益。",
            "系统只辅助决策，不自动交易。",
            "生活账户不参与投资。",
        ],
        "policy_check": build_policy_check_summary(policy_check_report),
    }
    apply_daily_quant_summary(sections, daily_run_report)
    traffic_light_status = build_traffic_light_status(sections)
    one_page_summary = build_one_page_summary(traffic_light_status)
    action_checklist = build_action_checklist(sections)
    system_health = build_system_health(daily_run_report)

    report = {
        "generated_at": date.today().isoformat(),
        "config_version": config.get("real_config_version"),
        "sections": sections,
        "one_page_summary": one_page_summary,
        "action_checklist": action_checklist,
        "traffic_light_status": traffic_light_status,
        "system_health": system_health,
        "daily_messages": {
            "infos": daily_run_report.get("infos", []),
            "warnings": daily_run_report.get("warnings", []),
            "errors": daily_run_report.get("errors", []),
        },
    }
    report["markdown"] = render_committee_markdown(report, plain=plain)
    return report


def build_account_overview(config):
    profile = config.get("investor_profile", {})
    totals = summarize_holdings(config)
    return {
        "total_assets": totals.get("total_amount", 0),
        "bullet_cash_balance": config.get("bullet_account", {}).get("balance", 0),
        "cash_weight": totals.get("cash_weight", 0),
        "core_weight": totals.get("core_weight", 0),
        "satellite_weight": totals.get("satellite_weight", 0),
        "defensive_weight": totals.get("defensive_weight", 0),
        "max_account_drawdown_tolerance": profile.get("max_account_drawdown_tolerance"),
        "target_annual_return": profile.get("target_annual_return"),
        "style": profile.get("style"),
    }


def build_holdings_structure(config):
    by_id = {asset.get("asset_id"): asset for asset in config.get("holdings", [])}
    holdings = []
    for asset_id in COMMITTEE_ASSET_ORDER:
        asset = by_id.get(asset_id)
        if not asset:
            holdings.append({"asset_id": asset_id, "status": "missing", "message": "当前持仓中不存在。"})
            continue
        holdings.append(
            {
                "asset_id": asset_id,
                "asset_name": asset.get("asset_name"),
                "amount": float(asset.get("amount", 0)),
                "weight": float(asset.get("weight", 0)),
                "role": asset.get("role"),
                "nav_mode": asset.get("nav_mode", "unit_nav"),
                "funds": asset.get("funds", []),
                "status": "active",
            }
        )
    return holdings


def build_daily_drawdown_check(config, daily_logs):
    allowed = config.get("drawdown_buy_policy", {}).get("allowed_fund_codes", [])
    if not daily_logs:
        return {"status": "missing", "message": MISSING_TEXT, "allowed_drawdown_assets": allowed, "items": []}

    latest_date = max(item.get("date", "") for item in daily_logs if item.get("date"))
    latest_logs = [item for item in daily_logs if item.get("date") == latest_date]
    items = []
    for item in latest_logs:
        drawdown = item.get("drawdown")
        suggestions = item.get("suggestions", {}) or {}
        warnings = item.get("warnings", []) or []
        items.append(
            {
                "date": item.get("date"),
                "fund_code": item.get("fund_code"),
                "fund_name": item.get("fund_name"),
                "current_drawdown": drawdown,
                "triggered": bool(suggestions),
                "suggestions": suggestions,
                "status": item.get("status"),
                "historical_drawdown_not_chased": any("历史" in warning or "不追补" in warning for warning in warnings),
                "warnings": warnings,
                "action_advice": "按待确认补仓处理" if suggestions else "今日无补仓操作",
            }
        )
    return {
        "status": "available",
        "date": latest_date,
        "allowed_drawdown_assets": allowed,
        "items": items,
    }


def build_portfolio_backtest_summary(report):
    summary = report.get("portfolio_summary", {})
    if not summary:
        return {"status": "missing", "message": MISSING_TEXT}
    return {
        "status": "available",
        "start_date": summary.get("start_date"),
        "end_date": summary.get("end_date"),
        "total_invested": summary.get("total_invested", 0),
        "final_market_value": summary.get("final_market_value", 0),
        "total_return_rate": summary.get("total_return_rate", 0),
        "trigger_count_total": summary.get("trigger_count_total", 0),
        "total_bullet_invested": summary.get("total_bullet_invested", 0),
        "bullet_cash_initial": summary.get("bullet_cash_initial", 0),
        "bullet_cash_final": summary.get("bullet_cash_final", 0),
        "bullet_cash_used": summary.get("total_bullet_invested", 0),
    }


def build_contribution_summary(report):
    summary = report.get("portfolio_summary", {})
    if not summary:
        return {"status": "missing", "message": MISSING_TEXT, "assets": []}
    assets = []
    for asset in report.get("assets", []):
        assets.append(
            {
                "asset_id": asset.get("asset_id"),
                "asset_name": asset.get("asset_name"),
                "total_profit": asset.get("total_profit"),
                "profit_contribution_percent": asset.get("profit_contribution_percent"),
                "total_return_rate": asset.get("total_return_rate"),
                "investment_weight": asset.get("investment_weight"),
                "market_value_weight": asset.get("market_value_weight"),
                "max_drawdown": asset.get("max_drawdown"),
            }
        )
    return {
        "status": "available",
        "best_profit_contributor": summary.get("best_profit_contributor"),
        "worst_profit_contributor": summary.get("worst_profit_contributor"),
        "assets": assets,
        "dividend_low_vol_note": "DIVIDEND_LOW_VOL / 008163 使用 accumulated_nav 口径观察，避免分红基金单位净值低估。",
    }


def build_rebalance_summary(report):
    if not report:
        return {"status": "missing", "message": MISSING_TEXT}
    conclusion = report.get("conclusion", {})
    return {
        "status": "available",
        "needs_immediate_rebalance": conclusion.get("needs_immediate_rebalance"),
        "underweight_categories": conclusion.get("underweight_categories", []),
        "overweight_categories": conclusion.get("overweight_categories", []),
        "sell_recommended": conclusion.get("sell_recommended"),
        "future_dca_bias": conclusion.get("future_dca_bias"),
        "summary": conclusion.get("summary"),
        "category_summary": report.get("category_summary", {}),
        "asset_advice": report.get("asset_advice", []),
    }


def build_quant_signal_summary(report):
    if not report:
        return {"status": "missing", "message": MISSING_TEXT, "assets": []}
    summary = report.get("portfolio_quant_summary", {})
    assets = []
    for asset in report.get("assets", []):
        if asset.get("status") != "available":
            continue
        assets.append(
            {
                "asset_id": asset.get("asset_id"),
                "asset_name": asset.get("asset_name"),
                "quant_score": asset.get("quant_score"),
                "signal_status": asset.get("signal_status"),
                "trend_score": asset.get("trend_score"),
                "risk_score": asset.get("risk_score"),
                "human_readable_summary": asset.get("human_readable_summary"),
            }
        )
    return {
        "status": "available",
        "market_regime": summary.get("market_regime"),
        "average_quant_score": summary.get("average_quant_score"),
        "core_asset_score": summary.get("core_asset_score"),
        "defensive_asset_score": summary.get("defensive_asset_score"),
        "satellite_asset_score": summary.get("satellite_asset_score"),
        "assets": assets,
    }


def build_watchlist_summary(report):
    if not report:
        return {"status": "missing", "message": MISSING_TEXT, "funds": []}
    funds = []
    for item in report.get("funds", []):
        fund = item.get("fund", {})
        signal = item.get("quant_signal", {})
        fit = item.get("portfolio_fit", {})
        funds.append(
            {
                "fund_code": fund.get("fund_code"),
                "fund_name": fund.get("fund_name"),
                "candidate_role": fund.get("candidate_role"),
                "reason": fund.get("reason"),
                "quant_score": signal.get("quant_score"),
                "signal_status": signal.get("signal_status"),
                "fit_type": fit.get("fit_type"),
                "message": fit.get("message"),
            }
        )
    return {
        "status": "available",
        "funds": funds,
        "warnings": report.get("warnings", []),
    }


def apply_daily_quant_summary(sections, daily_run_report):
    conclusion = (daily_run_report or {}).get("today_conclusion", {})
    regime = conclusion.get("quant_market_regime")
    if not regime:
        return
    section = sections.setdefault("quant_signal", {"status": "missing", "message": MISSING_TEXT, "assets": []})
    if section.get("status") == "missing":
        section["status"] = "available"
        section["message"] = None
    section["market_regime"] = regime
    if conclusion.get("average_quant_score") is not None:
        section["average_quant_score"] = conclusion.get("average_quant_score")
    if conclusion.get("core_asset_score") is not None:
        section["core_asset_score"] = conclusion.get("core_asset_score")


def build_policy_check_summary(report):
    if not report:
        return {"status": "missing", "message": MISSING_TEXT}
    return {
        "status": "available",
        "passed": report.get("passed"),
        "issues": report.get("issues", []),
    }


def build_committee_conclusion(config, rebalance_advice, contribution_report):
    allowed = config.get("drawdown_buy_policy", {}).get("allowed_fund_codes", [])
    conclusions = [
        "当前不需要立即卖出。" if not rebalance_advice.get("conclusion", {}).get("sell_recommended") else "当前存在需要处理的超配项目。",
        "NASDAQ100 仍是长期核心。",
        f"子弹仓应保留用于规则内补仓：{', '.join(allowed)}。",
        "HSTECH 不追补历史回撤。",
        "债券不新增或少新增，未来现金流向 CORE 倾斜。",
        "黄金维持月定投。",
        "红利低波维持观察，并使用 accumulated_nav 口径。",
    ]
    if not contribution_report:
        conclusions.append("资产贡献分析暂无数据，请先运行 contribution-report。")
    return conclusions


def build_traffic_light_status(sections):
    account = sections.get("account_overview", {})
    drawdown = sections.get("daily_drawdown_check", {})
    rebalance = sections.get("rebalance_advice", {})
    category_summary = rebalance.get("category_summary", {}) if rebalance.get("status") == "available" else {}

    return {
        "drawdown": _drawdown_traffic(drawdown),
        "cash": _category_traffic(
            "子弹仓",
            account.get("cash_weight"),
            _category_bounds(category_summary, "CASH", 0.10, 0.25, 0.15),
            cash=True,
        ),
        "core": _category_traffic(
            "核心资产",
            account.get("core_weight"),
            _category_bounds(category_summary, "CORE", 0.25, 0.50, 0.35),
        ),
        "satellite": _category_traffic(
            "卫星资产",
            account.get("satellite_weight"),
            _category_bounds(category_summary, "SATELLITE", 0.10, 0.30, 0.20),
        ),
        "defensive": _defensive_traffic(
            account.get("defensive_weight"),
            _category_bounds(category_summary, "DEFENSIVE", 0.20, 0.45, 0.30),
        ),
        "rebalance": _rebalance_traffic(rebalance),
        "quant": _quant_traffic(sections.get("quant_signal", {})),
    }


def build_one_page_summary(traffic_light_status):
    order = [
        ("drawdown", "补仓状态"),
        ("cash", "子弹仓"),
        ("core", "核心资产"),
        ("satellite", "卫星资产"),
        ("defensive", "防守资产"),
        ("rebalance", "再平衡"),
        ("quant", "市场环境"),
    ]
    return [
        {
            "item": label,
            "color": traffic_light_status[key]["color"],
            "status": traffic_light_status[key]["status"],
            "conclusion": traffic_light_status[key]["conclusion"],
        }
        for key, label in order
    ]


def build_action_checklist(sections):
    drawdown = sections.get("daily_drawdown_check", {})
    items = drawdown.get("items", []) if drawdown.get("status") == "available" else []
    triggered = [item for item in items if item.get("triggered")]
    checklist = []
    if triggered:
        for item in triggered:
            suggestions = item.get("suggestions", {}) or {}
            for level, amount in suggestions.items():
                checklist.append(
                    {
                        "checked": False,
                        "text": f"确认是否执行补仓：{item.get('fund_code')} / {_money(amount)} / {level}档",
                    }
                )
    else:
        checklist.append({"checked": False, "text": "是否需要补仓：否"})

    rebalance = sections.get("rebalance_advice", {})
    sell_recommended = bool(rebalance.get("sell_recommended")) if rebalance.get("status") == "available" else False
    checklist.extend(
        [
            {"checked": False, "text": f"是否需要卖出：{'是' if sell_recommended else '否'}"},
            {"checked": False, "text": "是否需要调整定投：暂不调整"},
            {"checked": False, "text": "是否需要关注：HSTECH 深度回撤，但不追补历史档位"},
            {"checked": False, "text": "下一次建议运行：python3 main.py daily --quick"},
        ]
    )
    return checklist


def build_system_health(daily_run_report):
    steps = daily_run_report.get("steps", []) if daily_run_report else []
    if not steps:
        return {
            "status": "missing",
            "message": "暂无 daily workflow 数据，请先运行 python3 main.py daily --quick。",
            "steps": [],
        }
    return {
        "status": daily_run_report.get("status", "unknown"),
        "message": daily_run_report.get("date"),
        "steps": [
            {"name": step.get("name"), "status": _normalize_step_status(step.get("status"))}
            for step in steps
        ],
    }


def render_committee_markdown(report, plain=False):
    if plain:
        return render_committee_plain_markdown(report)

    sections = report.get("sections", {})
    lines = [
        "# DrawdownGuard 个人投委会日报",
        "",
        f"生成日期：{report.get('generated_at')}",
        f"账户状态：{_account_status(report)}",
        f"今日结论：{_today_conclusion(report)}",
        "",
    ]
    lines.extend(render_one_page_summary(report.get("one_page_summary", [])))
    lines.extend(render_action_checklist(report.get("action_checklist", [])))
    lines.extend(render_system_health(report.get("system_health", {})))
    lines.extend(render_daily_messages(report.get("daily_messages", {})))
    lines.extend(render_account_overview(sections.get("account_overview", {})))
    lines.extend(render_holdings_structure(sections.get("holdings_structure", [])))
    lines.extend(render_daily_drawdown_check(sections.get("daily_drawdown_check", {})))
    lines.extend(render_portfolio_backtest(sections.get("portfolio_backtest_summary", {})))
    lines.extend(render_contribution(sections.get("contribution_analysis", {})))
    lines.extend(render_rebalance(sections.get("rebalance_advice", {})))
    lines.extend(render_quant_signal(sections.get("quant_signal", {})))
    lines.extend(render_watchlist(sections.get("watchlist", {})))
    lines.extend(render_conclusion(sections.get("committee_conclusion", [])))
    lines.extend(render_risk(sections.get("risk_disclosure", [])))
    return "\n".join(lines) + "\n"


def render_committee_plain_markdown(report):
    sections = report.get("sections", {})
    lines = [
        "# DrawdownGuard 个人投委会报告",
        "",
        f"- 生成日期：{report.get('generated_at')}",
        f"- 配置版本：{report.get('config_version')}",
        "",
    ]
    lines.extend(render_account_overview(sections.get("account_overview", {})))
    lines.extend(render_holdings_structure(sections.get("holdings_structure", [])))
    lines.extend(render_daily_drawdown_check(sections.get("daily_drawdown_check", {}), plain=True))
    lines.extend(render_portfolio_backtest(sections.get("portfolio_backtest_summary", {})))
    lines.extend(render_contribution(sections.get("contribution_analysis", {})))
    lines.extend(render_rebalance(sections.get("rebalance_advice", {})))
    lines.extend(render_quant_signal(sections.get("quant_signal", {})))
    lines.extend(render_watchlist(sections.get("watchlist", {})))
    lines.extend(render_conclusion(sections.get("committee_conclusion", [])))
    lines.extend(render_risk(sections.get("risk_disclosure", [])))
    return "\n".join(lines) + "\n"


def render_one_page_summary(summary):
    lines = ["## 一页摘要", "", "| 项目 | 状态 | 结论 |", "| --- | --- | --- |"]
    for row in summary:
        lines.append(
            f"| {row.get('item')} | {_traffic_label(row.get('color'), row.get('status'))} | {row.get('conclusion')} |"
        )
    lines.append("")
    return lines


def render_action_checklist(checklist):
    lines = ["## 今日操作清单", ""]
    for item in checklist:
        marker = "x" if item.get("checked") else " "
        lines.append(f"- [{marker}] {item.get('text')}")
    lines.append("")
    return lines


def render_system_health(system_health):
    lines = ["## 系统健康状态", ""]
    if system_health.get("status") == "missing":
        lines.append(f"- {system_health.get('message')}")
        lines.append("")
        return lines
    lines.extend(["| 模块 | 状态 |", "| --- | --- |"])
    for step in system_health.get("steps", []):
        lines.append(f"| {step.get('name')} | {step.get('status')} |")
    lines.append("")
    return lines


def render_daily_messages(messages):
    lines = ["## Infos / Warnings / Errors", ""]
    groups = [("Infos", messages.get("infos", []), "当前无 info。"), ("Warnings", messages.get("warnings", []), "当前无 warning。"), ("Errors", messages.get("errors", []), "当前无 error。")]
    for title, items, empty in groups:
        lines.append(f"### {title}")
        if items:
            for item in items:
                lines.append(f"- {item}")
        else:
            lines.append(f"- {empty}")
        lines.append("")
    return lines


def render_account_overview(section):
    return [
        "## 一、账户总览",
        "",
        f"- 总资产：{_money(section.get('total_assets'))}",
        f"- 子弹仓余额：{_money(section.get('bullet_cash_balance'))}",
        f"- 子弹仓占比：{_pct(section.get('cash_weight'))}",
        f"- 核心资产占比：{_pct(section.get('core_weight'))}",
        f"- 卫星资产占比：{_pct(section.get('satellite_weight'))}",
        f"- 防守资产占比：{_pct(section.get('defensive_weight'))}",
        f"- 最大可接受回撤：{_pct(section.get('max_account_drawdown_tolerance'))}",
        "",
    ]


def render_holdings_structure(section):
    lines = ["## 二、当前持仓结构", ""]
    for asset in section:
        if asset.get("status") == "missing":
            lines.append(f"- {asset.get('asset_id')}：{asset.get('message')}")
            continue
        lines.append(
            f"- {asset.get('asset_id')} / {asset.get('asset_name')}："
            f"{_money(asset.get('amount'))}，权重 {_pct(asset.get('weight'))}，role {asset.get('role')}"
        )
    lines.append("")
    return lines


def render_daily_drawdown_check(section, plain=False):
    lines = ["## 三、今日补仓检查", ""]
    lines.append(f"- 允许补仓资产：{', '.join(section.get('allowed_drawdown_assets', [])) or '无'}")
    if section.get("status") == "missing":
        lines.append(f"- {section.get('message')}")
        lines.append("")
        return lines
    lines.append(f"- 检查日期：{section.get('date')}")
    lines.extend(["", "| 基金 | 当前回撤 | 状态 | 建议 |", "| --- | ---: | --- | --- |"])
    for item in section.get("items", []):
        status = _drawdown_item_status(item)
        advice = _drawdown_item_advice(item)
        lines.append(f"| {item.get('fund_code')} {item.get('fund_name')} | {_pct(item.get('current_drawdown'))} | {status} | {advice} |")
    lines.append("")
    return lines


def render_portfolio_backtest(section):
    lines = ["## 四、组合回测摘要", ""]
    if section.get("status") == "missing":
        lines.append(f"- {section.get('message')}")
        lines.append("")
        return lines
    lines.extend(
        [
            f"- 回测区间：{section.get('start_date')} 至 {section.get('end_date')}",
            f"- 总投入：{_money(section.get('total_invested'))}",
            f"- 当前估算市值：{_money(section.get('final_market_value'))}",
            f"- 总收益率：{_pct(section.get('total_return_rate'))}",
            f"- 补仓次数：{section.get('trigger_count_total')}",
            f"- 子弹仓消耗：{_money(section.get('bullet_cash_used'))}",
            "",
        ]
    )
    return lines


def render_contribution(section):
    lines = ["## 五、资产贡献分析", ""]
    if section.get("status") == "missing":
        lines.append(f"- {section.get('message')}")
        lines.append("")
        return lines
    lines.append(f"- 最大收益贡献资产：{_asset_ref(section.get('best_profit_contributor'))}")
    lines.append(f"- 最大拖累资产：{_asset_ref(section.get('worst_profit_contributor'))}")
    lines.extend(["", "| 资产 | 投入权重 | 市值权重 | 收益率 | 收益贡献 | 最大回撤 |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for asset in section.get("assets", []):
        lines.append(
            f"| {asset.get('asset_id')} | {_pct(asset.get('investment_weight'))} | "
            f"{_pct(asset.get('market_value_weight'))} | {_pct(asset.get('total_return_rate'))} | "
            f"{_pct(asset.get('profit_contribution_percent'))} | {_pct(asset.get('max_drawdown'))} |"
        )
    lines.extend(
        [
            "",
            "- NASDAQ100 是核心收益来源。",
            "- GOLD 是重要收益贡献资产，但不是无风险资产。",
            f"- {section.get('dividend_low_vol_note')}",
            "- HSTECH 维持小仓位卫星。",
        ]
    )
    lines.append("")
    return lines


def render_rebalance(section):
    lines = ["## 六、再平衡建议", ""]
    if section.get("status") == "missing":
        lines.append(f"- {section.get('message')}")
        lines.append("")
        return lines
    lines.extend(["| 大类 | 当前权重 | 目标区间 | 状态 | 建议 |", "| --- | ---: | --- | --- | --- |"])
    for category in ["CASH", "CORE", "SATELLITE", "DEFENSIVE"]:
        item = section.get("category_summary", {}).get(category, {})
        if not item:
            continue
        target_range = f"{_pct(item.get('min_weight'))}-{_pct(item.get('max_weight'))}"
        lines.append(
            f"| {category} | {_pct(item.get('current_weight'))} | {target_range} | "
            f"{_category_status_label(item)} | {_action_label(item.get('action'))} |"
        )
    lines.extend(
        [
            "",
            f"- 当前是否需要立即再平衡：{section.get('needs_immediate_rebalance')}",
            f"- 低配资产：{', '.join(section.get('underweight_categories', [])) or '无'}",
            f"- 高配资产：{', '.join(section.get('overweight_categories', [])) or '无'}",
            f"- 是否建议卖出：{section.get('sell_recommended')}",
            f"- 未来定投应偏向：{section.get('future_dca_bias')}",
            f"- 摘要：{section.get('summary')}",
            "",
        ]
    )
    return lines


def render_quant_signal(section):
    lines = ["## 七、量化信号", ""]
    if section.get("status") == "missing":
        lines.append(f"- {section.get('message')}")
        lines.append("")
        return lines
    lines.extend(
        [
            f"- 组合市场状态：{section.get('market_regime')}",
            f"- 组合平均分：{_score(section.get('average_quant_score'))}",
            "",
            "| 资产 | 分数 | 状态 | 趋势 | 风险 | 结论 |",
            "| --- | ---: | --- | ---: | ---: | --- |",
        ]
    )
    for asset in section.get("assets", []):
        lines.append(
            f"| {asset.get('asset_id')} | {_score(asset.get('quant_score'))} | "
            f"{asset.get('signal_status')} | {_score(asset.get('trend_score'))} | "
            f"{_score(asset.get('risk_score'))} | {asset.get('human_readable_summary')} |"
        )
    lines.append("")
    return lines


def render_watchlist(section):
    lines = ["## 八、观察基金", ""]
    if section.get("status") == "missing":
        lines.append(f"- {section.get('message')}")
        lines.append("")
        return lines
    if not section.get("funds"):
        lines.append("- 当前观察池为空。")
        lines.append("")
        return lines
    lines.extend(["| 基金 | 角色 | 分数 | 状态 | 组合适配 | 结论 |", "| --- | --- | ---: | --- | --- | --- |"])
    for item in section.get("funds", []):
        lines.append(
            f"| {item.get('fund_code')} {item.get('fund_name')} | {item.get('candidate_role')} | "
            f"{_score(item.get('quant_score'))} | {item.get('signal_status', 'N/A')} | "
            f"{item.get('fit_type', 'N/A')} | {item.get('message', '')} |"
        )
    lines.append("")
    return lines


def render_conclusion(section):
    lines = ["## 九、投委会结论", ""]
    for item in section:
        lines.append(f"- {item}")
    lines.append("")
    return lines


def render_risk(section):
    lines = ["## 十、风险提示", ""]
    for item in section:
        lines.append(f"- {item}")
    lines.append("")
    return lines


def _money(value):
    if value is None:
        return "N/A"
    return f"{float(value):.2f} 元"


def _pct(value):
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def _score(value):
    if value is None:
        return "N/A"
    return f"{float(value):.0f}"


def _asset_ref(asset):
    if not asset:
        return "暂无"
    return f"{asset.get('asset_id')} / {asset.get('asset_name')}"


def _drawdown_traffic(section):
    if section.get("status") == "missing":
        return {"color": "red", "status": "数据缺失", "conclusion": "请先运行每日补仓检查"}
    items = section.get("items", [])
    if any(_has_data_error(item) for item in items):
        return {"color": "red", "status": "数据异常", "conclusion": "补仓检查需要处理数据问题"}
    if any(item.get("triggered") for item in items):
        return {"color": "yellow", "status": "待确认", "conclusion": "存在待确认补仓"}
    return {"color": "green", "status": "无触发", "conclusion": "今日不补仓"}


def _category_bounds(category_summary, category, min_weight, max_weight, target_weight):
    item = category_summary.get(category, {})
    return {
        "min": item.get("min_weight", min_weight),
        "max": item.get("max_weight", max_weight),
        "target": item.get("target_weight", target_weight),
    }


def _category_traffic(label, current, bounds, cash=False):
    current = float(current or 0)
    min_weight = float(bounds["min"])
    max_weight = float(bounds["max"])
    target = float(bounds["target"])
    if cash:
        if current < 0.05:
            return {"color": "red", "status": "不足", "conclusion": f"子弹仓仅 {_pct(current)}，低于安全线"}
        if current < min_weight or current > max_weight:
            status = "偏低" if current < min_weight else "偏高"
            return {"color": "yellow", "status": status, "conclusion": f"{_pct(current)}，需关注现金水位"}
        return {"color": "green", "status": "健康", "conclusion": f"{_pct(current)}，处于健康区间"}
    if current < min_weight:
        return {"color": "yellow", "status": "低配", "conclusion": f"{label}低于目标区间，未来定投倾斜"}
    if current > max_weight:
        return {"color": "yellow", "status": "超配", "conclusion": f"{label}高于目标区间，减少新增"}
    if current < target and label == "核心资产":
        return {"color": "green", "status": "合理偏低", "conclusion": "NASDAQ100 继续作为定投优先级"}
    return {"color": "green", "status": "合理", "conclusion": "保持观察"}


def _defensive_traffic(current, bounds):
    current = float(current or 0)
    max_weight = float(bounds["max"])
    target = float(bounds["target"])
    if current > 0.60:
        return {"color": "red", "status": "极端超配", "conclusion": "防守资产明显过高，需要单独处理"}
    if current > max_weight:
        return {"color": "yellow", "status": "超配", "conclusion": "防守资产超过上限，暂停或减少新增"}
    if current > target:
        return {"color": "yellow", "status": "偏高", "conclusion": "不卖出，未来少新增债券"}
    return {"color": "green", "status": "合理", "conclusion": "维持防守仓位"}


def _rebalance_traffic(section):
    if section.get("status") == "missing":
        return {"color": "yellow", "status": "暂无数据", "conclusion": "请先运行 rebalance-advice"}
    if section.get("needs_immediate_rebalance") or section.get("sell_recommended"):
        return {"color": "red", "status": "需处理", "conclusion": "存在立即再平衡事项"}
    if section.get("future_dca_bias"):
        return {"color": "yellow", "status": "定投倾斜", "conclusion": "不卖出，未来资金按建议倾斜"}
    return {"color": "green", "status": "不需要", "conclusion": "不做卖出调仓"}


def _quant_traffic(section):
    if section.get("status") == "missing":
        return {"color": "yellow", "status": "暂无数据", "conclusion": "请先运行 quant-signal"}
    regime = section.get("market_regime") or "unknown"
    score = section.get("average_quant_score")
    if regime in ("risk_on",) and (score is None or score >= 60):
        return {"color": "green", "status": regime, "conclusion": "量化环境偏健康"}
    if regime in ("high_volatility", "drawdown_watch"):
        return {"color": "red", "status": regime, "conclusion": "量化信号提示风险升高"}
    if regime == "defensive":
        return {"color": "yellow", "status": regime, "conclusion": "市场偏防守，维持风险控制"}
    return {"color": "yellow", "status": regime, "conclusion": "市场环境中性，继续观察"}


def _traffic_label(color, status):
    icons = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
    return f"{icons.get(color, '⚪')} {status}"


def _account_status(report):
    statuses = report.get("traffic_light_status", {}).values()
    if any(item.get("color") == "red" for item in statuses):
        return "需要处理"
    if any(item.get("color") == "yellow" for item in statuses):
        return "关注"
    return "正常"


def _today_conclusion(report):
    summary = {item.get("item"): item for item in report.get("one_page_summary", [])}
    drawdown = summary.get("补仓状态", {}).get("conclusion", "补仓检查暂无数据")
    rebalance = summary.get("再平衡", {}).get("conclusion", "再平衡建议暂无数据")
    core = summary.get("核心资产", {}).get("conclusion", "未来定投继续偏向 CORE / NASDAQ100")
    return f"{drawdown}，{rebalance}，{core}"


def _drawdown_item_status(item):
    if _has_data_error(item):
        return "数据异常"
    if item.get("triggered"):
        return "待确认"
    if item.get("historical_drawdown_not_chased"):
        return "深度回撤中"
    return "观察中"


def _drawdown_item_advice(item):
    if item.get("triggered"):
        suggestions = item.get("suggestions", {}) or {}
        return "；".join(f"{level}档 {_money(amount)}" for level, amount in suggestions.items()) or "确认补仓"
    if item.get("historical_drawdown_not_chased"):
        return "历史回撤不追补"
    if _has_data_error(item):
        return "检查数据源"
    return "无"


def _has_data_error(item):
    status_text = str(item.get("status", ""))
    if any(keyword in status_text for keyword in ["缺失", "策略计算失败", "错误", "异常"]):
        return True
    warnings = [
        warning for warning in (item.get("warnings", []) or [])
        if "已切换到缓存数据" not in str(warning) and "使用缓存净值" not in str(warning)
    ]
    warning_text = " ".join(str(warning) for warning in warnings)
    return any(keyword in warning_text for keyword in ["缺失", "策略计算失败", "错误", "异常"])


def _category_status_label(item):
    category = item.get("category")
    status = item.get("status")
    current = float(item.get("current_weight", 0))
    target = float(item.get("target_weight", 0))
    if category == "CASH" and item.get("health") == "healthy":
        return "健康"
    if category == "DEFENSIVE" and current > target and status == "neutral":
        return "偏高但可接受"
    return {"underweight": "低配", "neutral": "合理", "overweight": "超配"}.get(status, status or "未知")


def _action_label(action):
    return {
        "increase_dca": "定投倾斜",
        "maintain": "维持",
        "reduce_dca": "减少定投",
        "pause_dca": "暂停定投",
        "watch": "观察",
        "no_action": "保持",
        "future_dca_tilt_to_core": "未来资金倾向 CORE",
    }.get(action, action or "无")


def _normalize_step_status(status):
    return {
        "success": "OK",
        "warning": "WARNING",
        "failed": "FAILED",
        "skipped": "SKIPPED",
    }.get(status, str(status or "UNKNOWN").upper())
