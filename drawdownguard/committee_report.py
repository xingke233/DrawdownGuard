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
):
    daily_logs = daily_logs or []
    portfolio_backtest_report = portfolio_backtest_report or {}
    contribution_report = contribution_report or {}
    rebalance_advice = rebalance_advice or {}
    policy_check_report = policy_check_report or {}

    sections = {
        "account_overview": build_account_overview(config),
        "holdings_structure": build_holdings_structure(config),
        "daily_drawdown_check": build_daily_drawdown_check(config, daily_logs),
        "portfolio_backtest_summary": build_portfolio_backtest_summary(portfolio_backtest_report),
        "contribution_analysis": build_contribution_summary(contribution_report),
        "rebalance_advice": build_rebalance_summary(rebalance_advice),
        "committee_conclusion": build_committee_conclusion(config, rebalance_advice, contribution_report),
        "risk_disclosure": [
            "历史回测不代表未来收益。",
            "系统只辅助决策，不自动交易。",
            "生活账户不参与投资。",
        ],
        "policy_check": build_policy_check_summary(policy_check_report),
    }

    report = {
        "generated_at": date.today().isoformat(),
        "config_version": config.get("real_config_version"),
        "sections": sections,
    }
    report["markdown"] = render_committee_markdown(report)
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


def render_committee_markdown(report):
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
    lines.extend(render_daily_drawdown_check(sections.get("daily_drawdown_check", {})))
    lines.extend(render_portfolio_backtest(sections.get("portfolio_backtest_summary", {})))
    lines.extend(render_contribution(sections.get("contribution_analysis", {})))
    lines.extend(render_rebalance(sections.get("rebalance_advice", {})))
    lines.extend(render_conclusion(sections.get("committee_conclusion", [])))
    lines.extend(render_risk(sections.get("risk_disclosure", [])))
    return "\n".join(lines) + "\n"


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


def render_daily_drawdown_check(section):
    lines = ["## 三、今日补仓检查", ""]
    lines.append(f"- 允许补仓资产：{', '.join(section.get('allowed_drawdown_assets', [])) or '无'}")
    if section.get("status") == "missing":
        lines.append(f"- {section.get('message')}")
        lines.append("")
        return lines
    lines.append(f"- 检查日期：{section.get('date')}")
    for item in section.get("items", []):
        lines.append(
            f"- {item.get('fund_code')} {item.get('fund_name')}："
            f"当前回撤 {_pct(item.get('current_drawdown'))}，"
            f"触发补仓 {item.get('triggered')}，"
            f"历史回撤不追补 {item.get('historical_drawdown_not_chased')}，"
            f"建议：{item.get('action_advice')}"
        )
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
    lines.append("- 各资产收益贡献：")
    for asset in section.get("assets", []):
        lines.append(
            f"  - {asset.get('asset_id')}：盈亏 {_money(asset.get('total_profit'))}，"
            f"贡献 {_pct(asset.get('profit_contribution_percent'))}，"
            f"收益率 {_pct(asset.get('total_return_rate'))}"
        )
    lines.append(f"- 红利低波说明：{section.get('dividend_low_vol_note')}")
    lines.append("")
    return lines


def render_rebalance(section):
    lines = ["## 六、再平衡建议", ""]
    if section.get("status") == "missing":
        lines.append(f"- {section.get('message')}")
        lines.append("")
        return lines
    lines.extend(
        [
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


def render_conclusion(section):
    lines = ["## 七、投委会结论", ""]
    for item in section:
        lines.append(f"- {item}")
    lines.append("")
    return lines


def render_risk(section):
    lines = ["## 八、风险提示", ""]
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


def _asset_ref(asset):
    if not asset:
        return "暂无"
    return f"{asset.get('asset_id')} / {asset.get('asset_name')}"

