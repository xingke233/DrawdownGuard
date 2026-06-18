from datetime import date

from .quant_signal import build_asset_signal, calculate_quant_metrics, max_drawdown, volatility


DEFAULT_WATCHLIST = {"funds": []}


def add_watchlist_fund(watchlist, fund_code, fund_name, role="unknown", reason="", nav_mode="unit_nav", notes=""):
    funds = list(watchlist.get("funds", []))
    existing = next((item for item in funds if item.get("fund_code") == fund_code), None)
    if existing:
        return {"funds": funds}, {**existing, "already_exists": True}
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
        "notes": notes,
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
    funds = sorted(watchlist.get("funds", []), key=lambda item: item.get("created_at", ""))
    if not funds:
        lines.append("当前没有观察基金。")
        return "\n".join(lines)
    for item in funds:
        lines.append(
            f"- {item.get('fund_code')} | {item.get('fund_name')} | role {item.get('candidate_role')} | "
            f"status {item.get('status')} | allow_dca {item.get('allow_dca')} | "
            f"allow_drawdown_buy {item.get('allow_drawdown_buy')} | nav_mode {item.get('nav_mode', 'unit_nav')} | "
            f"created_at {item.get('created_at')} | reason {item.get('reason')} | notes {item.get('notes', '')}"
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
    relationship = analyze_portfolio_fit(config, item, signal, dca)
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
        if item.get("status", "watching") != "watching":
            continue
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
        "summary_funds": [compact_watchlist_analysis(item) for item in reports],
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


def analyze_portfolio_fit(config, item, signal=None, dca=None):
    role = item.get("candidate_role", "unknown")
    fund_code = item.get("fund_code")
    signal = signal or {}
    dca = dca or {}
    category = classify_candidate_category(item)
    available_assets = {asset.get("asset_id") for asset in config.get("holdings", [])}
    existing_codes = {
        fund.get("code")
        for asset in config.get("holdings", [])
        for fund in asset.get("funds", [])
    }
    if fund_code in existing_codes:
        return {
            "candidate_category": category,
            "possible_overlap_assets": ["current_holdings"],
            "diversification_effect": "duplicate",
            "overlap_type": "exact_overlap",
            "risk_level": "existing",
            "suggested_action": "consider_replace_existing",
            "reasoning": "该基金代码已存在于真实持仓中，属于精确重复，不应通过观察池再次新增。",
            "confidence": "high",
            "is_duplicate": True,
            "fit_type": "重复资产",
            "message": "该基金已存在于真实持仓中，不应通过观察池重复新增。",
        }
    possible_overlap, overlap_type, fit_type, base_reasoning = classify_overlap(category, role, available_assets, item)
    quant_score = signal.get("quant_score")
    drawdown = signal.get("drawdown_from_250d_high")
    warning_text = " ".join(signal.get("warnings") or [])
    risk_level = "medium"
    suggested_action = "keep_watching"
    confidence = "medium" if category != "unknown" else "low"
    reasoning = base_reasoning
    if signal.get("status") == "skipped":
        suggested_action = "data_insufficient"
        risk_level = "unknown"
        overlap_type = "insufficient_history"
        reasoning = "净值数据缺失，无法判断候选基金的长期有效性。"
        confidence = "high"
    elif "净值数据不足250条" in warning_text:
        suggested_action = "need_more_history"
        risk_level = "unknown"
        overlap_type = "insufficient_history"
        reasoning = "历史数据不足250条，不能直接判断长期有效性。"
        confidence = "high"
    elif overlap_type == "exact_overlap":
        suggested_action = "consider_replace_existing"
        risk_level = "existing"
        reasoning = base_reasoning
        confidence = "high"
    elif category == "commodity_cycle":
        risk_level = "high" if (drawdown is not None and drawdown <= -0.2) or "high_volatility" in signal.get("tags", []) else "medium"
        suggested_action = "keep_watching"
        reasoning = "与黄金同属贵金属大类但风险结构不同，白银等商品周期资产波动和回撤通常更高。"
    elif category == "high_risk_tech_theme":
        risk_level = "high_risk_theme"
        suggested_action = "consider_small_position" if quant_score is not None and quant_score >= 70 and drawdown is not None and drawdown > -0.2 else "keep_watching"
        reasoning = "科技成长暴露已经存在，趋势较强时也应控制仓位；主题拥挤，不建议直接新增大仓位。"
    elif role in ("theme", "satellite") and ((drawdown is not None and drawdown <= -0.2) or "high_volatility" in signal.get("tags", [])):
        risk_level = "high_risk_theme"
        suggested_action = "keep_watching"
        overlap_type = overlap_type if overlap_type != "none" else "none"
        reasoning = "候选基金波动或回撤较高，适合继续观察，不建议直接加入核心。"
    elif quant_score is not None and quant_score < 30 and drawdown is not None and drawdown <= -0.15:
        risk_level = "high"
        suggested_action = "reject"
        reasoning = "量化分数较低且回撤较深，暂不适合新增。"
    elif quant_score is not None and quant_score >= 60 and not possible_overlap:
        risk_level = "medium"
        suggested_action = "consider_small_position"
        reasoning = "候选基金量化状态较好，且提供当前组合较少的风险暴露，可考虑小仓位观察。"
    message = reasoning or "可继续观察，暂不进入真实持仓或定投。"
    return {
        "candidate_category": category,
        "possible_overlap_assets": sorted(set(possible_overlap)),
        "diversification_effect": diversification_effect_from_overlap(overlap_type),
        "overlap_type": overlap_type,
        "risk_level": risk_level,
        "suggested_action": suggested_action,
        "reasoning": reasoning,
        "confidence": confidence,
        "fit_type": fit_type,
        "is_duplicate": overlap_type == "exact_overlap",
        "message": message,
    }


def classify_candidate_category(item):
    text = f"{item.get('fund_name', '')} {item.get('reason', '')} {item.get('candidate_role', '')}".lower()
    keyword_groups = [
        ("high_risk_tech_theme", ["cpo", "半导体", "ai", "算力", "科技", "人工智能", "芯片", "先进制造"]),
        ("commodity_cycle", ["白银", "有色", "金属", "商品", "贵金属"]),
        ("infrastructure_or_utility", ["电网", "公用事业", "电力", "基建"]),
        ("value_factor", ["红利", "低波", "价值"]),
        ("index_core_or_broad_index", ["纳指", "纳斯达克", "标普", "沪深300", "中证a500", "中证 A500".lower()]),
    ]
    for category, keywords in keyword_groups:
        if any(keyword in text for keyword in keywords):
            return category
    role = item.get("candidate_role")
    if role == "hedge":
        return "hedge_candidate"
    if role == "bond":
        return "bond_candidate"
    if role == "active":
        return "active_fund_candidate"
    return "unknown"


def classify_overlap(category, role, available_assets, item=None):
    item = item or {}
    if category == "high_risk_tech_theme":
        overlaps = [asset for asset in ["NASDAQ100", "HSTECH", "ACTIVE_ADVANCED_MANUFACTURING"] if asset in available_assets]
        return overlaps, "broad_style_overlap" if overlaps else "none", "高风险科技主题", "科技成长主题与现有成长资产存在风格重叠，但不等于精确重复。"
    if category == "commodity_cycle":
        overlaps = ["GOLD"] if "GOLD" in available_assets else []
        return overlaps, "broad_commodity_overlap" if overlaps else "none", "商品周期", "商品周期资产提供周期暴露，需要与黄金区分评估。"
    if category == "infrastructure_or_utility":
        return [], "none", "公用事业/基础设施", "可能提供当前组合较少的防御和基础设施暴露。"
    if category == "value_factor":
        overlaps = ["DIVIDEND_LOW_VOL"] if "DIVIDEND_LOW_VOL" in available_assets else []
        return overlaps, "broad_style_overlap" if overlaps else "none", "价值因子", "可能与红利低波等价值因子资产存在风格重叠。"
    if category == "index_core_or_broad_index":
        text = f"{item.get('fund_name', '')} {item.get('reason', '')}".lower()
        if ("纳指" in text or "纳斯达克" in text) and "NASDAQ100" in available_assets:
            return ["NASDAQ100"], "exact_overlap", "核心或宽基指数", "纳指候选与现有 NASDAQ100 核心资产跟踪方向高度一致，属于精确重叠，应优先考虑替换而非新增。"
        overlaps = []
        if "NASDAQ100" in available_assets:
            overlaps.append("NASDAQ100")
        overlap_type = "broad_style_overlap" if overlaps else "none"
        return overlaps, overlap_type, "核心或宽基指数", "宽基或核心指数候选需要与现有核心资产比较后再决定是否替换或小仓位配置。"
    if role == "core" and "NASDAQ100" in available_assets:
        return ["NASDAQ100"], "broad_style_overlap", "核心增强", "核心候选与现有核心成长资产存在大类风格重叠。"
    if role == "factor":
        overlaps = [asset for asset in ["CASHFLOW", "DIVIDEND_LOW_VOL"] if asset in available_assets]
        return overlaps, "broad_style_overlap" if overlaps else "none", "因子候选", "因子候选需要与现有质量、价值因子资产比较。"
    if role == "hedge":
        overlaps = ["GOLD"] if "GOLD" in available_assets else []
        return overlaps, "broad_commodity_overlap" if overlaps else "none", "防守资产", "对冲候选需要与现有黄金或防守资产比较。"
    if role == "theme":
        return [], "none", "主题候选", "主题候选需要先观察波动和回撤。"
    if role == "satellite":
        return [], "none", "卫星机会", "暂无明确重叠资产，可继续观察是否提供新暴露。"
    return [], "none", "待分类", "候选基金信息不足，暂按观察处理。"


def diversification_effect_from_overlap(overlap_type):
    if overlap_type == "exact_overlap":
        return "duplicate"
    if overlap_type in ("broad_style_overlap", "broad_commodity_overlap"):
        return overlap_type
    if overlap_type == "insufficient_history":
        return "unknown"
    return "new_diversifier"


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
        "holding_add_command": (
            f"python3 main.py holding-add {item.get('fund_code')} --name \"{item.get('fund_name')}\" "
            f"--asset-id WATCH_{item.get('fund_code')} --role {item.get('candidate_role', 'unknown')} --amount <实际金额>"
        ),
        "dca_add_command": (
            f"python3 main.py dca-add {item.get('fund_code')} --amount 20 --frequency weekly --weekday thu"
        ),
    }


def compact_watchlist_analysis(report):
    fund = report.get("fund", {})
    signal = report.get("quant_signal", {})
    fit = report.get("portfolio_fit", {})
    return {
        "fund_code": fund.get("fund_code"),
        "fund_name": fund.get("fund_name"),
        "candidate_role": fund.get("candidate_role"),
        "quant_score": signal.get("quant_score"),
        "signal_status": signal.get("signal_status"),
        "candidate_category": fit.get("candidate_category"),
        "overlap_type": fit.get("overlap_type"),
        "suggested_action": fit.get("suggested_action"),
        "summary": fit.get("reasoning") or fit.get("message") or signal.get("human_readable_summary"),
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
        f"- candidate_category：{fit.get('candidate_category')}",
        f"- overlap_type：{fit.get('overlap_type')}",
        f"- possible_overlap_assets：{', '.join(fit.get('possible_overlap_assets', [])) or '无'}",
        f"- diversification_effect：{fit.get('diversification_effect')}",
        f"- risk_level：{fit.get('risk_level')}",
        f"- suggested_action：{fit.get('suggested_action')}",
        f"- confidence：{fit.get('confidence')}",
        f"- reasoning：{fit.get('reasoning')}",
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
