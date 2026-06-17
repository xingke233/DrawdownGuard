from datetime import date

from .quant_signal import build_asset_signal, calculate_quant_metrics, max_drawdown, volatility


DEFAULT_WATCHLIST = {"funds": []}


def add_watchlist_fund(watchlist, fund_code, fund_name, role="unknown", reason="", nav_mode="unit_nav"):
    funds = list(watchlist.get("funds", []))
    if any(item.get("fund_code") == fund_code for item in funds):
        raise ValueError(f"观察池已存在基金：{fund_code}")
    item = {
        "fund_code": fund_code,
        "fund_name": fund_name,
        "reason": reason,
        "candidate_role": role,
        "nav_mode": nav_mode,
        "status": "watching",
        "allow_drawdown_buy": False,
        "allow_dca": False,
        "created_at": date.today().isoformat(),
    }
    funds.append(item)
    return {"funds": funds}, item


def remove_watchlist_fund(watchlist, fund_code):
    funds = list(watchlist.get("funds", []))
    remaining = [item for item in funds if item.get("fund_code") != fund_code]
    if len(remaining) == len(funds):
        raise ValueError(f"观察池中不存在基金：{fund_code}")
    return {"funds": remaining}


def find_watchlist_fund(watchlist, fund_code):
    return next((item for item in watchlist.get("funds", []) if item.get("fund_code") == fund_code), None)


def summarize_watchlist(watchlist):
    lines = ["基金观察池", ""]
    funds = watchlist.get("funds", [])
    if not funds:
        lines.append("暂无观察基金。")
        return "\n".join(lines)
    for item in funds:
        lines.append(
            f"- {item.get('fund_code')} | {item.get('fund_name')} | role {item.get('candidate_role')} | "
            f"status {item.get('status')} | allow_dca {item.get('allow_dca')} | "
            f"allow_drawdown_buy {item.get('allow_drawdown_buy')} | reason {item.get('reason')}"
        )
    return "\n".join(lines)


def analyze_watchlist_fund(config, provider, watchlist, fund_code, weekly_dca=20, start_date=None):
    item = find_watchlist_fund(watchlist, fund_code)
    if not item:
        raise ValueError(f"观察池中不存在基金：{fund_code}")
    nav_mode = item.get("nav_mode", "unit_nav")
    try:
        nav_data = provider.get_full_history(fund_code, nav_mode=nav_mode)
    except TypeError:
        nav_data = provider.get_full_history(fund_code)
    except Exception as exc:
        nav_data = {"history": [], "source": "skipped", "warnings": [f"净值获取失败：{exc}"], "nav_mode": nav_mode}

    history = nav_data.get("history", [])
    signal = build_asset_signal(
        asset_id=f"WATCHLIST_{fund_code}",
        asset_name=item.get("fund_name", fund_code),
        fund_code=fund_code,
        nav_mode=nav_data.get("nav_mode", nav_mode),
        history=history,
        source=nav_data.get("source", "unknown"),
        warnings=nav_data.get("warnings", []),
    )
    dca = simulate_candidate_dca(history, weekly_dca=weekly_dca, start_date=start_date)
    relationship = analyze_portfolio_fit(config, item)
    report = {
        "generated_at": date.today().isoformat(),
        "fund": item,
        "data_check": build_data_check(history, nav_data),
        "quant_signal": signal,
        "dca_simulation": dca,
        "portfolio_fit": relationship,
        "warnings": [*nav_data.get("warnings", []), *signal.get("warnings", [])],
        "disclaimer": "观察池分析只用于候选基金研究，不自动买入、不自动定投、不自动允许补仓。",
    }
    return report


def analyze_all_watchlist(config, provider, watchlist, weekly_dca=20, start_date=None):
    reports = []
    warnings = []
    for item in watchlist.get("funds", []):
        try:
            report = analyze_watchlist_fund(
                config,
                provider,
                watchlist,
                item["fund_code"],
                weekly_dca=weekly_dca,
                start_date=start_date,
            )
        except Exception as exc:
            report = {
                "generated_at": date.today().isoformat(),
                "fund": item,
                "status": "failed",
                "warnings": [str(exc)],
            }
        reports.append(report)
        for warning in report.get("warnings", []):
            warnings.append(f"{item.get('fund_code')}: {warning}")
    return {
        "generated_at": date.today().isoformat(),
        "funds": reports,
        "warnings": warnings,
    }


def simulate_candidate_dca(history, weekly_dca=20, start_date=None):
    rows = [item for item in _normalize_history(history) if not start_date or item["date"] >= start_date]
    if not rows:
        return {
            "status": "skipped",
            "weekly_dca": weekly_dca,
            "start_date": start_date,
            "total_invested": 0,
            "final_market_value": 0,
            "total_return_rate": 0,
            "max_drawdown": None,
            "volatility": None,
            "sharpe_like_ratio": None,
            "warnings": ["净值数据不足，无法模拟定投。"],
        }
    invested = 0
    shares = 0
    value_series = []
    for index, row in enumerate(rows):
        if index % 5 == 0:
            amount = float(weekly_dca)
            invested += amount
            shares += amount / row["nav"]
        value_series.append({"date": row["date"], "nav": shares * row["nav"]})
    final_value = shares * rows[-1]["nav"]
    profit = final_value - invested
    return_rate = profit / invested if invested else 0
    daily_vol = volatility(value_series, min(60, max(1, len(value_series) - 1)))
    return {
        "status": "available",
        "weekly_dca": float(weekly_dca),
        "start_date": rows[0]["date"],
        "end_date": rows[-1]["date"],
        "buy_count": sum(1 for index, _ in enumerate(rows) if index % 5 == 0),
        "total_invested": round(invested, 2),
        "final_market_value": round(final_value, 2),
        "total_profit": round(profit, 2),
        "total_return_rate": return_rate,
        "max_drawdown": max_drawdown(value_series),
        "volatility": daily_vol,
        "sharpe_like_ratio": return_rate / daily_vol if daily_vol else None,
    }


def build_data_check(history, nav_data):
    rows = _normalize_history(history)
    if not rows:
        return {
            "status": "missing",
            "source": nav_data.get("source", "unknown"),
            "nav_mode": nav_data.get("nav_mode"),
            "history_count": 0,
        }
    metrics = calculate_quant_metrics(rows)
    return {
        "status": "available",
        "source": nav_data.get("source", "unknown"),
        "nav_mode": nav_data.get("nav_mode"),
        "earliest_nav_date": rows[0]["date"],
        "latest_nav_date": rows[-1]["date"],
        "history_count": len(rows),
        "current_nav": rows[-1]["nav"],
        "high_250d": metrics.get("high_250d"),
        "drawdown_from_250d_high": metrics.get("drawdown_from_250d_high"),
        "ma_20": metrics.get("ma_20"),
        "ma_60": metrics.get("ma_60"),
        "ma_120": metrics.get("ma_120"),
        "return_20d": metrics.get("return_20d"),
        "return_60d": metrics.get("return_60d"),
        "return_120d": metrics.get("return_120d"),
        "volatility_20d": metrics.get("volatility_20d"),
        "volatility_60d": metrics.get("volatility_60d"),
        "max_drawdown_250d": metrics.get("max_drawdown_250d"),
    }


def analyze_portfolio_fit(config, item):
    role = item.get("candidate_role", "unknown")
    fund_code = item.get("fund_code")
    existing_codes = {
        fund.get("code")
        for asset in config.get("holdings", [])
        for fund in asset.get("funds", [])
    }
    if fund_code in existing_codes:
        return {
            "fit_type": "重复资产",
            "is_duplicate": True,
            "message": "该基金已存在于真实持仓中，不应通过观察池重复新增。",
        }
    if role == "core":
        fit_type = "核心增强"
    elif role in ("satellite", "factor"):
        fit_type = "卫星机会"
    elif role == "hedge":
        fit_type = "防守资产"
    elif role == "theme":
        fit_type = "高风险主题"
    else:
        fit_type = "待分类"
    duplicate_roles = {
        asset.get("role")
        for asset in config.get("holdings", [])
        if str(asset.get("role", "")).startswith(role)
    }
    message = "可继续观察，暂不进入真实持仓或定投。"
    if duplicate_roles:
        message = "可能与现有资产重复，不建议直接新增，除非替换原有资产。"
    return {"fit_type": fit_type, "is_duplicate": bool(duplicate_roles), "message": message}


def promote_watchlist_fund(watchlist, fund_code):
    item = find_watchlist_fund(watchlist, fund_code)
    if not item:
        raise ValueError(f"观察池中不存在基金：{fund_code}")
    return {
        "fund_code": fund_code,
        "message": "第一版只生成建议，不自动修改真实持仓、定投计划或补仓策略。",
        "holding_snippet": {
            "asset_id": "请填写资产ID",
            "asset_name": "请填写资产名称",
            "amount": 0,
            "weight": 0,
            "role": item.get("candidate_role", "unknown"),
            "nav_mode": item.get("nav_mode", "unit_nav"),
            "funds": [
                {
                    "code": item.get("fund_code"),
                    "name": item.get("fund_name"),
                    "amount": 0,
                    "weight": 0,
                    "role": item.get("candidate_role", "unknown"),
                    "nav_mode": item.get("nav_mode", "unit_nav"),
                }
            ],
        },
        "policy_reminder": {
            "allow_dca": False,
            "allow_drawdown_buy": False,
            "manual_steps": [
                "手动评估是否纳入 current_holdings.json。",
                "如需定投，手动更新 dca_plan.json。",
                "如需补仓，必须手动更新 policy_config.json allow list；默认不允许。",
            ],
        },
    }


def summarize_watchlist_analysis(report):
    fund = report.get("fund", {})
    data = report.get("data_check", {})
    signal = report.get("quant_signal", {})
    dca = report.get("dca_simulation", {})
    fit = report.get("portfolio_fit", {})
    lines = [
        "观察基金分析",
        "",
        f"基金：{fund.get('fund_code')} {fund.get('fund_name')}",
        f"角色：{fund.get('candidate_role')} | 原因：{fund.get('reason')}",
        f"净值口径：{fund.get('nav_mode', 'unit_nav')}",
        "",
        "数据检查：",
        f"- 最早净值日期：{data.get('earliest_nav_date', 'N/A')}",
        f"- 最新净值日期：{data.get('latest_nav_date', 'N/A')}",
        f"- 当前净值：{_fmt_num(data.get('current_nav'))}",
        f"- 250日高点：{_fmt_num(data.get('high_250d'))}",
        f"- 当前回撤：{_fmt_pct(data.get('drawdown_from_250d_high'))}",
        "",
        "量化信号：",
        f"- quant_score：{_fmt_score(signal.get('quant_score'))}",
        f"- signal_status：{signal.get('signal_status', 'N/A')}",
        f"- MA20/60/120：{_fmt_num(data.get('ma_20'))} / {_fmt_num(data.get('ma_60'))} / {_fmt_num(data.get('ma_120'))}",
        f"- 20/60/120日收益：{_fmt_pct(data.get('return_20d'))} / {_fmt_pct(data.get('return_60d'))} / {_fmt_pct(data.get('return_120d'))}",
        f"- 20/60日波动率：{_fmt_pct(data.get('volatility_20d'))} / {_fmt_pct(data.get('volatility_60d'))}",
        f"- 最大回撤：{_fmt_pct(data.get('max_drawdown_250d'))}",
        "",
        "候选基金定投模拟：",
        f"- 总投入：{_fmt_money(dca.get('total_invested'))}",
        f"- 估算市值：{_fmt_money(dca.get('final_market_value'))}",
        f"- 收益率：{_fmt_pct(dca.get('total_return_rate'))}",
        f"- 最大回撤：{_fmt_pct(dca.get('max_drawdown'))}",
        f"- 波动率：{_fmt_pct(dca.get('volatility'))}",
        f"- 简化夏普：{_fmt_num(dca.get('sharpe_like_ratio'))}",
        "",
        "组合适配：",
        f"- 类型：{fit.get('fit_type')}",
        f"- 结论：{fit.get('message')}",
    ]
    if report.get("warnings"):
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in report["warnings"])
    return "\n".join(lines)


def summarize_watchlist_analysis_report(report):
    lines = ["观察池分析汇总", ""]
    for item in report.get("funds", []):
        fund = item.get("fund", {})
        signal = item.get("quant_signal", {})
        fit = item.get("portfolio_fit", {})
        lines.append(
            f"- {fund.get('fund_code')} {fund.get('fund_name')} | "
            f"{signal.get('quant_score', 'N/A')} | {signal.get('signal_status', 'N/A')} | "
            f"{fit.get('fit_type', 'N/A')} | {fit.get('message', '')}"
        )
    return "\n".join(lines)


def _normalize_history(history):
    rows = []
    for item in history or []:
        if "date" not in item or "nav" not in item:
            continue
        rows.append({"date": str(item["date"])[:10], "nav": float(item["nav"])})
    return sorted(rows, key=lambda item: item["date"])


def _fmt_num(value):
    if value is None:
        return "N/A"
    return f"{float(value):.4f}"


def _fmt_score(value):
    if value is None:
        return "N/A"
    return f"{float(value):.0f}"


def _fmt_pct(value):
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def _fmt_money(value):
    if value is None:
        return "N/A"
    return f"{float(value):.2f} 元"
