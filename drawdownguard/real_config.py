REAL_PROFILE_FILES = {
    "user_profile": "user_profile.json",
    "current_holdings": "current_holdings.json",
    "dca_plan": "dca_plan.json",
    "policy_config": "policy_config.json",
}

REPRESENTATIVE_FUNDS = {
    "NASDAQ100": "270042",
    "HSTECH": "012349",
    "CASHFLOW": "023918",
    "DIVIDEND_LOW_VOL": "008163",
    "GOLD": "000216",
}

PORTFOLIO_ASSET_ORDER = ["NASDAQ100", "HSTECH", "CASHFLOW", "DIVIDEND_LOW_VOL", "GOLD"]

PROFILE_ASSET_CATEGORIES = {
    "cash": {"CASH"},
    "core": {"NASDAQ100"},
    "satellite": {
        "HSTECH",
        "CASHFLOW",
        "DIVIDEND_LOW_VOL",
        "ACTIVE_ADVANCED_MANUFACTURING",
        "NONFERROUS_METALS",
    },
    "defensive": {"GOLD", "BONDS"},
}


def load_real_profile_files(storage):
    data = {}
    for key, filename in REAL_PROFILE_FILES.items():
        value = storage._load_json(filename, {})
        if value:
            data[key] = value
    return data


def apply_real_profile(config, real_data):
    if not real_data:
        _ensure_fund_bullet_balance(config)
        return config

    profile_data = real_data.get("user_profile", {})
    holdings_data = real_data.get("current_holdings", {})
    dca_plan = real_data.get("dca_plan", {})
    policy_data = real_data.get("policy_config", {})
    bullet_cash = profile_data.get("bullet_cash", {})
    policy = policy_data.get("drawdown_buy_policy", {})

    config["real_config_version"] = (
        profile_data.get("version")
        or holdings_data.get("version")
        or dca_plan.get("version")
        or policy_data.get("version")
    )
    config["investor_profile"] = profile_data.get("investor_profile", {})
    config["target_allocation"] = profile_data.get("target_allocation", {})
    config["bullet_cash"] = bullet_cash
    config["life_account"] = {
        **config.get("life_account", {}),
        **profile_data.get("life_account", {}),
        "participates_in_replenishment": False,
    }
    config["holdings"] = holdings_data.get("holdings", [])
    config["cleared_assets"] = holdings_data.get("cleared_assets", [])
    config["dca_plan"] = dca_plan
    config["drawdown_buy_policy"] = policy

    if bullet_cash:
        config["bullet_account"] = {
            "name": bullet_cash.get("account_name", "余额宝"),
            "balance": int(bullet_cash.get("amount", 0)),
        }
    if policy:
        config["strategy_activation_date"] = policy.get("strategy_activation_date", config.get("strategy_activation_date"))
        config["peak_window_trading_days"] = policy.get("stage_high_window", config.get("peak_window_trading_days", 250))
        config["replenishment_levels"] = [
            {"drawdown_percent": item["drawdown_percent"], "cash_ratio": item["cash_ratio"]}
            for item in policy.get("levels", config.get("replenishment_levels", []))
        ]

    config["funds"] = _build_allowed_funds(holdings_data, policy, config.get("funds", []))
    config["portfolio_backtest"] = _build_portfolio_config(
        config.get("portfolio_backtest", {}),
        holdings_data,
        dca_plan,
        policy,
        bullet_cash,
    )
    _ensure_fund_bullet_balance(config)
    return config


def summarize_profile(config):
    profile = config.get("investor_profile", {})
    holdings = current_holdings(config)
    totals = summarize_holdings(config)
    allowed = config.get("drawdown_buy_policy", {}).get("allowed_fund_codes", [])
    blocked = config.get("drawdown_buy_policy", {}).get("blocked_fund_codes", [])
    lines = ["真实账户配置报告"]
    lines.append(f"配置版本：{config.get('real_config_version')}")
    lines.append(f"年龄：{profile.get('age')}")
    lines.append(f"投资期限：{profile.get('horizon_years')}")
    lines.append(f"目标年化：{_fmt_pct(profile.get('target_annual_return'))}")
    lines.append(f"账户最大回撤容忍：{_fmt_pct(profile.get('max_account_drawdown_tolerance'))}")
    lines.append(f"风格：{profile.get('style')}")
    lines.append(f"生活账户参与投资：{config.get('life_account', {}).get('investable')}")
    lines.append(f"子弹仓：{config.get('bullet_account', {}).get('name')} {config.get('bullet_account', {}).get('balance')} 元")
    lines.append(f"当前资产总额：{totals['total_amount']:.2f} 元")
    lines.append(f"子弹仓占比：{totals['cash_weight'] * 100:.2f}%")
    lines.append(f"核心资产占比：{totals['core_weight'] * 100:.2f}%")
    lines.append(f"卫星资产占比：{totals['satellite_weight'] * 100:.2f}%")
    lines.append(f"防守资产占比：{totals['defensive_weight'] * 100:.2f}%")
    lines.append("当前定投计划：")
    for item in config.get("dca_plan", {}).get("weekly", []):
        lines.append(f"- 每周四 {item['fund_code']} {item['fund_name']} {item['amount']} 元")
    for item in config.get("dca_plan", {}).get("monthly", []):
        lines.append(f"- 每月{item.get('day', 1)}日 {item['fund_code']} {item['fund_name']} {item['amount']} 元")
    lines.append(f"允许补仓资产：{', '.join(allowed)}")
    lines.append(f"禁止补仓资产：{', '.join(blocked)}")
    lines.append(f"当前持仓资产数：{len(holdings)}")
    return "\n".join(lines)


def summarize_holdings_report(config):
    totals = summarize_holdings(config)
    lines = ["当前持仓报告"]
    lines.append(f"总金额：{totals['total_amount']:.2f} 元")
    lines.append("按资产汇总：")
    for asset in current_holdings(config):
        lines.append(
            f"- {asset['asset_id']} | {asset['asset_name']} | "
            f"{asset.get('amount', 0):.2f} 元 | 权重 {asset.get('weight', 0) * 100:.2f}% | role {asset.get('role')}"
        )
        for fund in asset.get("funds", []):
            lines.append(
                f"  - {fund['code']} {fund['name']} | {fund.get('amount', 0):.2f} 元 | "
                f"{fund.get('weight', 0) * 100:.2f}%"
            )
    lines.append("按角色汇总：")
    for role, item in sorted(totals["by_role"].items()):
        lines.append(f"- {role}: {item['amount']:.2f} 元 | {item['weight'] * 100:.2f}%")
    lines.append(f"NASDAQ100 合计：{totals['nasdaq_amount']:.2f} 元 | {totals['nasdaq_weight'] * 100:.2f}%")
    lines.append(f"债券合计：{totals['bonds_amount']:.2f} 元 | {totals['bonds_weight'] * 100:.2f}%")
    return "\n".join(lines)


def run_policy_checks(config):
    issues = []
    holdings = current_holdings(config)
    allowed = set(config.get("drawdown_buy_policy", {}).get("allowed_fund_codes", []))
    blocked = set(config.get("drawdown_buy_policy", {}).get("blocked_fund_codes", []))
    fund_codes = [fund["code"] for asset in holdings for fund in asset.get("funds", [])]

    overlap = sorted(allowed & blocked)
    for code in overlap:
        issues.append(_issue("error", "drawdown_policy", f"{code} 同时出现在允许和禁止补仓列表。"))
    if config.get("life_account", {}).get("investable") or config.get("life_account", {}).get("participates_in_replenishment"):
        issues.append(_issue("error", "life_account", "生活账户进入投资或补仓计算。"))
    for asset in config.get("portfolio_backtest", {}).get("assets", []):
        if not asset.get("nav_mode"):
            issues.append(_issue("warning", "nav_mode", f"{asset.get('asset_id')} 缺少 nav_mode。"))
    for code in sorted({code for code in fund_codes if fund_codes.count(code) > 1}):
        issues.append(_issue("warning", "fund_code", f"{code} 在持仓基金中重复。"))
    known_assets = {asset["asset_id"] for asset in holdings}
    for section in ("weekly", "monthly"):
        for item in config.get("dca_plan", {}).get(section, []):
            if item.get("asset_id") not in known_assets:
                issues.append(_issue("error", "dca_plan", f"{item.get('fund_code')} 定投计划找不到持仓资产 {item.get('asset_id')}。"))
    for code in allowed:
        if code not in fund_codes:
            issues.append(_issue("warning", "drawdown_policy", f"允许补仓基金 {code} 不在当前持仓中。"))
    for asset in holdings:
        if not asset.get("role"):
            issues.append(_issue("warning", "holding_role", f"{asset.get('asset_id')} 缺少 role。"))

    return {
        "passed": not any(item["severity"] == "error" for item in issues),
        "issues": issues,
        "checked_items": {
            "allowed_drawdown_funds": sorted(allowed),
            "blocked_drawdown_funds": sorted(blocked),
            "holding_fund_codes": fund_codes,
        },
    }


def summarize_policy_check(report):
    lines = ["真实配置策略检查"]
    lines.append(f"是否通过：{report.get('passed')}")
    if not report.get("issues"):
        lines.append("未发现配置问题。")
        return "\n".join(lines)
    for issue in report["issues"]:
        lines.append(f"- {issue['severity']} | {issue['category']} | {issue['message']}")
    return "\n".join(lines)


def current_holdings(config):
    return [asset for asset in config.get("holdings", []) if asset.get("asset_id") != "CASH"]


def summarize_holdings(config):
    holdings = config.get("holdings", [])
    total_amount = sum(float(asset.get("amount", 0)) for asset in holdings)
    by_role = {}
    for asset in holdings:
        role = asset.get("role", "unknown")
        item = by_role.setdefault(role, {"amount": 0, "weight": 0})
        item["amount"] += float(asset.get("amount", 0))
        item["weight"] += float(asset.get("weight", 0))
    nasdaq = next((asset for asset in holdings if asset.get("asset_id") == "NASDAQ100"), {})
    bonds = next((asset for asset in holdings if asset.get("asset_id") == "BONDS"), {})
    cash_weight = _category_weight(holdings, "cash")
    core_weight = _category_weight(holdings, "core")
    satellite_weight = _category_weight(holdings, "satellite")
    defensive_weight = _category_weight(holdings, "defensive")
    return {
        "total_amount": total_amount,
        "by_role": by_role,
        "nasdaq_amount": float(nasdaq.get("amount", 0)),
        "nasdaq_weight": float(nasdaq.get("weight", 0)),
        "bonds_amount": float(bonds.get("amount", 0)),
        "bonds_weight": float(bonds.get("weight", 0)),
        "cash_weight": cash_weight,
        "core_weight": core_weight,
        "satellite_weight": satellite_weight,
        "defensive_weight": defensive_weight,
    }


def _category_weight(holdings, category):
    asset_ids = PROFILE_ASSET_CATEGORIES[category]
    return sum(float(asset.get("weight", 0)) for asset in holdings if asset.get("asset_id") in asset_ids)


def _build_allowed_funds(holdings_data, policy, fallback_funds):
    fund_map = {fund["code"]: fund for fund in fallback_funds}
    for asset in holdings_data.get("holdings", []):
        for fund in asset.get("funds", []):
            fund_map[fund["code"]] = {"code": fund["code"], "name": fund["name"]}
    allowed = policy.get("allowed_fund_codes")
    if allowed:
        return [fund_map[code] for code in allowed if code in fund_map]
    return list(fund_map.values())


def _build_portfolio_config(base, holdings_data, dca_plan, policy, bullet_cash):
    config = dict(base)
    config["enabled"] = True
    config["bullet_cash_initial"] = int(bullet_cash.get("amount", config.get("bullet_cash_initial", 0)))
    config["bullet_cash_monthly_addition"] = 0
    config["dca_frequency"] = "mixed"
    config["dca_weekday"] = dca_plan.get("weekly_day_index", 3)

    holdings = {asset["asset_id"]: asset for asset in holdings_data.get("holdings", [])}
    weekly_by_asset = {}
    for item in dca_plan.get("weekly", []):
        weekly_by_asset.setdefault(item["asset_id"], []).append({**item, "frequency": "weekly", "weekday": dca_plan.get("weekly_day_index", 3)})
    monthly_by_asset = {}
    for item in dca_plan.get("monthly", []):
        monthly_by_asset.setdefault(item["asset_id"], []).append({**item, "frequency": "monthly"})

    assets = []
    for asset_id in PORTFOLIO_ASSET_ORDER:
        holding = holdings.get(asset_id, {"asset_id": asset_id, "asset_name": asset_id, "role": "unknown"})
        schedules = [*weekly_by_asset.get(asset_id, []), *monthly_by_asset.get(asset_id, [])]
        weekly_amount = sum(item["amount"] for item in weekly_by_asset.get(asset_id, []))
        representative = REPRESENTATIVE_FUNDS.get(asset_id)
        if not representative:
            continue
        asset = {
            "asset_id": asset_id,
            "asset_name": holding.get("asset_name", asset_id),
            "representative_fund": representative,
            "nav_mode": holding.get("nav_mode", "unit_nav"),
            "role": holding.get("role"),
            "current_amount": float(holding.get("amount", 0)),
            "current_weight": float(holding.get("weight", 0)),
            "strategy": "drawdown_plus_dca" if asset_id in ("NASDAQ100", "HSTECH") else "dca_only",
            "weekly_dca_amount": weekly_amount,
            "dca_schedules": schedules,
        }
        if asset_id in ("NASDAQ100", "HSTECH"):
            asset["drawdown_levels"] = [
                {"level": item["drawdown_percent"], "cash_ratio": item["cash_ratio"]}
                for item in policy.get("levels", [])
            ]
        assets.append(asset)
    config["assets"] = assets
    return config


def _ensure_fund_bullet_balance(config):
    bullet_balance = int(config.get("bullet_account", {}).get("balance", 0))
    for fund in config.get("funds", []):
        fund["bullet_balance"] = bullet_balance


def _issue(severity, category, message):
    return {"severity": severity, "category": category, "message": message}


def _fmt_pct(value):
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"
