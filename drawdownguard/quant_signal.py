from datetime import date
from math import sqrt


SUPPORTED_QUANT_ASSETS = {
    "NASDAQ100": {
        "representative_fund": "270042",
        "nav_mode": "unit_nav",
        "role": "core",
    },
    "HSTECH": {
        "representative_fund": "012349",
        "nav_mode": "unit_nav",
        "role": "satellite",
    },
    "CASHFLOW": {
        "representative_fund": "023918",
        "nav_mode": "unit_nav",
        "role": "satellite",
    },
    "DIVIDEND_LOW_VOL": {
        "representative_fund": "008163",
        "nav_mode": "accumulated_nav",
        "role": "satellite",
    },
    "GOLD": {
        "representative_fund": "000216",
        "nav_mode": "unit_nav",
        "role": "defensive",
    },
}


def run_quant_signal(config, provider):
    assets = []
    warnings = []
    portfolio_assets = {asset.get("asset_id"): asset for asset in config.get("portfolio_backtest", {}).get("assets", [])}
    holdings = {asset.get("asset_id"): asset for asset in config.get("holdings", [])}

    for asset_id, default in SUPPORTED_QUANT_ASSETS.items():
        configured = portfolio_assets.get(asset_id, {})
        holding = holdings.get(asset_id, {})
        fund_code = configured.get("representative_fund") or default["representative_fund"]
        nav_mode = configured.get("nav_mode") or holding.get("nav_mode") or default["nav_mode"]
        if asset_id == "DIVIDEND_LOW_VOL":
            nav_mode = "accumulated_nav"

        try:
            nav_data = provider.get_full_history(fund_code, nav_mode=nav_mode)
        except TypeError:
            nav_data = provider.get_full_history(fund_code)
        except Exception as exc:
            nav_data = {"history": [], "source": "skipped", "warnings": [f"净值获取失败：{exc}"], "nav_mode": nav_mode}

        item = build_asset_signal(
            asset_id=asset_id,
            asset_name=holding.get("asset_name") or configured.get("asset_name") or asset_id,
            fund_code=fund_code,
            nav_mode=nav_data.get("nav_mode", nav_mode),
            history=nav_data.get("history", []),
            source=nav_data.get("source", "unknown"),
            warnings=nav_data.get("warnings", []),
        )
        assets.append(item)
        for warning in item.get("warnings", []):
            warnings.append(f"{asset_id}: {warning}")

    for asset in config.get("holdings", []):
        asset_id = asset.get("asset_id")
        if asset_id in SUPPORTED_QUANT_ASSETS or asset_id == "CASH":
            continue
        assets.append(
            {
                "asset_id": asset_id,
                "asset_name": asset.get("asset_name", asset_id),
                "status": "unsupported",
                "warnings": ["第一版暂不支持该资产量化信号。"],
            }
        )

    summary = build_portfolio_quant_summary(assets)
    return {
        "generated_at": date.today().isoformat(),
        "source": "current_holdings.json + policy_config.json",
        "assets": assets,
        "portfolio_quant_summary": summary,
        "warnings": warnings,
        "disclaimer": "量化信号只作为投委会辅助判断，不自动交易，不构成买卖指令。",
    }


def build_asset_signal(asset_id, asset_name, fund_code, nav_mode, history, source="unknown", warnings=None):
    warnings = list(warnings or [])
    history = _normalize_history(history)
    if not history:
        return {
            "asset_id": asset_id,
            "asset_name": asset_name,
            "representative_fund": fund_code,
            "nav_mode": nav_mode,
            "status": "skipped",
            "source": source,
            "warnings": [*warnings, "净值数据不足，无法生成量化信号。"],
        }

    metrics = calculate_quant_metrics(history)
    if len(history) < 120:
        warnings.append(f"净值数据不足120条，当前仅{len(history)}条，趋势评分仅供参考。")
    if len(history) < 250:
        warnings.append(f"净值数据不足250条，当前仅{len(history)}条，250日高点和回撤仅按现有数据计算。")

    trend = trend_score(metrics)
    momentum = momentum_score(metrics)
    risk = risk_score(metrics)
    volatility = volatility_score(metrics)
    quant = clamp_score(0.35 * trend + 0.30 * momentum + 0.25 * risk + 0.10 * volatility)
    status = signal_status(quant)
    tags = signal_tags(metrics)

    return {
        "asset_id": asset_id,
        "asset_name": asset_name,
        "representative_fund": fund_code,
        "nav_mode": nav_mode,
        "status": "available",
        "source": source,
        "warnings": warnings,
        **metrics,
        "momentum_score": momentum,
        "trend_score": trend,
        "risk_score": risk,
        "volatility_score": volatility,
        "quant_score": quant,
        "signal_status": status,
        "tags": tags,
        "human_readable_summary": human_summary(asset_id, metrics, status, tags, nav_mode),
    }


def calculate_quant_metrics(history):
    history = _normalize_history(history)
    current = history[-1]
    current_nav = current["nav"]
    window_250 = history[-250:]
    high_250d = max(item["nav"] for item in window_250)
    return {
        "current_nav": current_nav,
        "latest_date": current["date"],
        "high_250d": high_250d,
        "drawdown_from_250d_high": safe_div(current_nav - high_250d, high_250d),
        "ma_20": moving_average(history, 20),
        "ma_60": moving_average(history, 60),
        "ma_120": moving_average(history, 120),
        "price_vs_ma20": price_vs_ma(history, 20),
        "price_vs_ma60": price_vs_ma(history, 60),
        "price_vs_ma120": price_vs_ma(history, 120),
        "return_20d": period_return(history, 20),
        "return_60d": period_return(history, 60),
        "return_120d": period_return(history, 120),
        "volatility_20d": volatility(history, 20),
        "volatility_60d": volatility(history, 60),
        "max_drawdown_250d": max_drawdown(window_250),
    }


def moving_average(history, window):
    if len(history) < window:
        return None
    return sum(item["nav"] for item in history[-window:]) / window


def price_vs_ma(history, window):
    ma = moving_average(history, window)
    if ma in (None, 0):
        return None
    return history[-1]["nav"] / ma - 1


def period_return(history, days):
    if len(history) <= days:
        return None
    start = history[-days - 1]["nav"]
    if start == 0:
        return None
    return history[-1]["nav"] / start - 1


def volatility(history, days):
    returns = daily_returns(history)
    if len(returns) < days:
        return None
    sample = returns[-days:]
    mean = sum(sample) / len(sample)
    variance = sum((value - mean) ** 2 for value in sample) / len(sample)
    return sqrt(variance)


def daily_returns(history):
    values = []
    for previous, current in zip(history, history[1:]):
        if previous["nav"] == 0:
            continue
        values.append(current["nav"] / previous["nav"] - 1)
    return values


def max_drawdown(history):
    if not history:
        return None
    peak = history[0]["nav"]
    worst = 0
    for item in history:
        peak = max(peak, item["nav"])
        if peak:
            worst = min(worst, item["nav"] / peak - 1)
    return worst


def trend_score(metrics):
    current = metrics.get("current_nav")
    ma20 = metrics.get("ma_20")
    ma60 = metrics.get("ma_60")
    ma120 = metrics.get("ma_120")
    if None in (current, ma20, ma60, ma120):
        return 50
    if current > ma20 > ma60 > ma120:
        return 90
    if current > ma60 and ma20 >= ma60:
        return 75
    if current > ma60:
        return 65
    if current < ma120:
        return 25
    if current < ma60:
        return 40
    return 50


def momentum_score(metrics):
    score = 50
    for key, weight in [("return_20d", 0.40), ("return_60d", 0.35), ("return_120d", 0.25)]:
        value = metrics.get(key)
        if value is None:
            continue
        score += 50 * weight if value > 0 else -50 * weight
    return clamp_score(score)


def risk_score(metrics):
    drawdown = metrics.get("drawdown_from_250d_high")
    if drawdown is None:
        return 50
    if drawdown >= -0.05:
        return 90
    if drawdown >= -0.10:
        return 70
    if drawdown >= -0.20:
        return 40
    return 15


def volatility_score(metrics):
    vol = metrics.get("volatility_60d") or metrics.get("volatility_20d")
    if vol is None:
        return 50
    if vol <= 0.01:
        return 85
    if vol <= 0.02:
        return 75
    if vol <= 0.03:
        return 60
    if vol <= 0.05:
        return 40
    return 20


def signal_status(score):
    if score >= 80:
        return "strong_uptrend"
    if score >= 60:
        return "healthy"
    if score >= 40:
        return "neutral"
    if score >= 20:
        return "weak"
    return "high_risk"


def signal_tags(metrics):
    tags = []
    drawdown = metrics.get("drawdown_from_250d_high")
    if drawdown is not None:
        if drawdown <= -0.20:
            tags.append("deep_drawdown")
        if drawdown >= -0.03:
            tags.append("near_high")
    if metrics.get("price_vs_ma120") is not None and metrics["price_vs_ma120"] < 0:
        tags.append("below_ma120")
    if (metrics.get("volatility_60d") or 0) > 0.03:
        tags.append("high_volatility")
    if (metrics.get("return_20d") or 0) > 0 and (metrics.get("return_60d") or 0) < 0:
        tags.append("momentum_recovering")
    if (
        metrics.get("current_nav") is not None
        and metrics.get("ma_20") is not None
        and metrics.get("ma_60") is not None
        and metrics["current_nav"] < metrics["ma_20"] < metrics["ma_60"]
    ):
        tags.append("trend_breakdown")
    return tags


def build_portfolio_quant_summary(assets):
    available = [asset for asset in assets if asset.get("status") == "available"]
    if not available:
        return {
            "average_quant_score": None,
            "core_asset_score": None,
            "defensive_asset_score": None,
            "satellite_asset_score": None,
            "market_regime": "unknown",
        }
    average = sum(asset["quant_score"] for asset in available) / len(available)
    by_id = {asset["asset_id"]: asset for asset in available}
    core = by_id.get("NASDAQ100", {}).get("quant_score")
    defensive_assets = [by_id[key]["quant_score"] for key in ("GOLD",) if key in by_id]
    satellite_assets = [
        by_id[key]["quant_score"]
        for key in ("HSTECH", "CASHFLOW", "DIVIDEND_LOW_VOL")
        if key in by_id
    ]
    defensive = _average(defensive_assets)
    satellite = _average(satellite_assets)
    return {
        "average_quant_score": round(average, 2),
        "core_asset_score": _round_or_none(core),
        "defensive_asset_score": _round_or_none(defensive),
        "satellite_asset_score": _round_or_none(satellite),
        "market_regime": classify_market_regime(available),
    }


def classify_market_regime(assets):
    by_id = {asset["asset_id"]: asset for asset in assets}
    core = by_id.get("NASDAQ100", {})
    gold = by_id.get("GOLD", {})
    high_vol_count = sum(1 for asset in assets if "high_volatility" in asset.get("tags", []))
    core_drawdown = core.get("drawdown_from_250d_high")
    if core_drawdown is not None and core_drawdown <= -0.08:
        return "drawdown_watch"
    if high_vol_count >= 3:
        return "high_volatility"
    if core.get("quant_score", 0) >= 70 and gold.get("quant_score", 50) >= 40:
        return "risk_on"
    if core.get("quant_score", 50) < 40 and gold.get("quant_score", 0) >= 60:
        return "defensive"
    return "neutral"


def human_summary(asset_id, metrics, status, tags, nav_mode):
    if asset_id == "NASDAQ100":
        if "near_high" in tags and status in ("strong_uptrend", "healthy"):
            return "当前接近250日高点，趋势健康，未触发补仓，适合继续定投。"
        if "deep_drawdown" in tags:
            return "当前处于较深回撤区，补仓仍以 DrawdownGuard 规则为准。"
        return "NASDAQ100 仍是长期核心，量化信号用于辅助观察定投节奏。"
    if asset_id == "HSTECH":
        if "deep_drawdown" in tags:
            return "当前处于深度回撤区，历史回撤不追补，维持小仓位观察。"
        return "恒生科技维持小仓位卫星观察，不使用量化信号自动交易。"
    if asset_id == "GOLD":
        return "黄金长期表现可作为对冲资产观察，但需注意阶段性高位和回撤风险。"
    if asset_id == "DIVIDEND_LOW_VOL":
        return f"红利低波使用 {nav_mode} 口径，当前作为价值因子观察。"
    if asset_id == "CASHFLOW":
        return "自由现金流作为质量因子资产，当前量化信号用于判断趋势和波动状态。"
    return "该资产量化信号仅供投委会辅助判断。"


def summarize_quant_signal_report(report, detail=False):
    summary = report.get("portfolio_quant_summary", {})
    lines = [
        "量化信号报告",
        "",
        f"组合市场状态：{summary.get('market_regime', 'unknown')}",
        f"组合平均分：{_fmt_score(summary.get('average_quant_score'))}",
        "",
    ]
    for asset in report.get("assets", []):
        if asset.get("status") == "unsupported":
            if detail:
                lines.append(f"* {asset.get('asset_id')}：unsupported | {asset.get('warnings', [''])[0]}")
            continue
        if asset.get("status") != "available":
            lines.append(f"* {asset.get('asset_id')}：skipped | {'；'.join(asset.get('warnings', []))}")
            continue
        lines.append(
            f"* {asset.get('asset_id')}：{_fmt_score(asset.get('quant_score'))} | "
            f"{asset.get('signal_status')} | {asset.get('human_readable_summary')}"
        )
        if detail:
            lines.extend(
                [
                    f"  - fund：{asset.get('representative_fund')} | nav_mode：{asset.get('nav_mode')} | source：{asset.get('source')}",
                    f"  - latest：{asset.get('latest_date')} | current_nav：{_fmt_number(asset.get('current_nav'))}",
                    f"  - high_250d：{_fmt_number(asset.get('high_250d'))} | drawdown：{_fmt_pct(asset.get('drawdown_from_250d_high'))}",
                    f"  - MA20/60/120：{_fmt_number(asset.get('ma_20'))} / {_fmt_number(asset.get('ma_60'))} / {_fmt_number(asset.get('ma_120'))}",
                    f"  - return20/60/120：{_fmt_pct(asset.get('return_20d'))} / {_fmt_pct(asset.get('return_60d'))} / {_fmt_pct(asset.get('return_120d'))}",
                    f"  - volatility20/60：{_fmt_pct(asset.get('volatility_20d'))} / {_fmt_pct(asset.get('volatility_60d'))}",
                    f"  - scores trend/momentum/risk/vol：{asset.get('trend_score')} / {asset.get('momentum_score')} / {asset.get('risk_score')} / {asset.get('volatility_score')}",
                    f"  - tags：{', '.join(asset.get('tags', [])) or '无'}",
                ]
            )
    if report.get("warnings"):
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in report["warnings"])
    return "\n".join(lines)


def clamp_score(value):
    return round(max(0, min(100, value)), 2)


def safe_div(numerator, denominator):
    if denominator in (None, 0):
        return None
    return numerator / denominator


def _normalize_history(history):
    normalized = []
    for item in history or []:
        if "date" not in item or "nav" not in item:
            continue
        normalized.append({"date": str(item["date"])[:10], "nav": float(item["nav"])})
    return sorted(normalized, key=lambda item: item["date"])


def _average(values):
    if not values:
        return None
    return sum(values) / len(values)


def _round_or_none(value):
    if value is None:
        return None
    return round(value, 2)


def _fmt_score(value):
    if value is None:
        return "N/A"
    return f"{float(value):.0f}"


def _fmt_number(value):
    if value is None:
        return "N/A"
    return f"{float(value):.4f}"


def _fmt_pct(value):
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.2f}%"
