from .real_config import PROFILE_ASSET_CATEGORIES, split_dca_items, summarize_holdings


DEFAULT_TARGET_ALLOCATION = {
    "CASH": {"target": 0.15, "min": 0.10, "max": 0.25},
    "CORE": {"target": 0.35, "min": 0.25, "max": 0.50},
    "SATELLITE": {"target": 0.20, "min": 0.10, "max": 0.30},
    "DEFENSIVE": {"target": 0.30, "min": 0.20, "max": 0.45},
}

CATEGORY_LABELS = {
    "CASH": "子弹仓",
    "CORE": "核心资产",
    "SATELLITE": "卫星资产",
    "DEFENSIVE": "防守资产",
}


def build_rebalance_advice(
    config,
    portfolio_strategy_report=None,
    portfolio_optimize_report=None,
    contribution_report=None,
):
    optional_reports = {
        "portfolio_strategy_report": bool(portfolio_strategy_report),
        "portfolio_optimize_report": bool(portfolio_optimize_report),
        "contribution_report": bool(contribution_report),
    }
    category_summary = build_category_summary(config)
    asset_advice = build_asset_advice(config, contribution_report or {})
    dca_review = build_dca_review(config)
    suggested_tilt = build_future_dca_tilt(category_summary, asset_advice)

    return {
        "config_version": config.get("real_config_version"),
        "target_allocation": target_allocation(config),
        "optional_reports_loaded": optional_reports,
        "category_summary": category_summary,
        "asset_advice": asset_advice,
        "dca_review": dca_review,
        "suggested_future_dca_tilt": suggested_tilt,
        "conclusion": build_conclusion(category_summary, asset_advice),
        "disclaimer": "再平衡建议只用于辅助决策，不自动交易，不改变补仓策略。",
    }


def build_category_summary(config):
    totals = summarize_holdings(config)
    current_weights = {
        "CASH": totals.get("cash_weight", 0),
        "CORE": totals.get("core_weight", 0),
        "SATELLITE": totals.get("satellite_weight", 0),
        "DEFENSIVE": totals.get("defensive_weight", 0),
    }
    targets = target_allocation(config)
    summary = {}
    for category, current_weight in current_weights.items():
        target = targets[category]
        status = category_status(current_weight, target)
        action, reason = category_action(category, current_weight, target, status)
        summary[category] = {
            "category": category,
            "label": CATEGORY_LABELS[category],
            "current_weight": current_weight,
            "target_weight": target["target"],
            "min_weight": target["min"],
            "max_weight": target["max"],
            "deviation": current_weight - target["target"],
            "status": status,
            "health": "healthy" if category == "CASH" and status == "neutral" else status,
            "action": action,
            "reason": reason,
        }
    return summary


def target_allocation(config):
    configured = config.get("target_allocation") or {}
    targets = {}
    for category, default in DEFAULT_TARGET_ALLOCATION.items():
        item = configured.get(category, {})
        targets[category] = {
            "target": float(item.get("target", default["target"])),
            "min": float(item.get("min", default["min"])),
            "max": float(item.get("max", default["max"])),
        }
    return targets


def category_status(current_weight, target):
    if current_weight < target["min"]:
        return "underweight"
    if current_weight > target["max"]:
        return "overweight"
    return "neutral"


def category_action(category, current_weight, target, status):
    if category == "CASH":
        if current_weight < target["min"]:
            return "watch", "子弹仓低于下限，回撤补仓缓冲不足。"
        if current_weight > target["max"]:
            return "watch", "现金超过上限，存在闲置偏多。"
        return "no_action", "子弹仓处于健康区间。"
    if status == "underweight":
        if category == "CORE":
            return "increase_dca", "核心资产低于目标区间，优先通过未来定投提高 NASDAQ100 权重。"
        return "increase_dca", "该大类低于目标区间，可通过未来定投补足。"
    if status == "overweight":
        return "pause_dca", "该大类超过上限，建议暂停或减少新增定投。"
    if category == "DEFENSIVE" and current_weight > target["target"]:
        return "maintain", "防守资产高于目标但未超上限，不建议立即卖出，未来新增资金向核心资产倾斜。"
    return "maintain", "该大类处于目标区间内。"


def build_asset_advice(config, contribution_report):
    contribution_by_asset = {
        item.get("asset_id"): item
        for item in contribution_report.get("assets", [])
        if item.get("asset_id")
    }
    results = []
    for asset in config.get("holdings", []):
        if asset.get("asset_id") == "CASH":
            continue
        asset_id = asset.get("asset_id")
        category = asset_category(asset_id)
        advice = asset_rule(asset, category, contribution_by_asset.get(asset_id, {}))
        results.append(
            {
                "asset_id": asset_id,
                "asset_name": asset.get("asset_name"),
                "current_weight": float(asset.get("weight", 0)),
                "role": asset.get("role"),
                "category": category,
                "current_amount": float(asset.get("amount", 0)),
                "action": advice["action"],
                "reason": advice["reason"],
            }
        )
    return results


def asset_category(asset_id):
    for category, asset_ids in PROFILE_ASSET_CATEGORIES.items():
        if asset_id in asset_ids:
            return category.upper()
    return "OTHER"


def asset_rule(asset, category, contribution):
    asset_id = asset.get("asset_id")
    if asset_id == "NASDAQ100":
        return {
            "action": "increase_dca",
            "reason": "核心资产当前约 20.35%，低于目标权重；建议未来定投优先流向 NASDAQ100，不建议卖出。",
        }
    if asset_id == "HSTECH":
        return {
            "action": "watch",
            "reason": "小仓位卫星资产，存在深度历史回撤特征；维持观察，不使用子弹仓主动追补。",
        }
    if asset_id == "CASHFLOW":
        return {"action": "maintain", "reason": "质量因子卫星资产，维持当前定投节奏。"}
    if asset_id == "DIVIDEND_LOW_VOL":
        nav_mode = asset.get("nav_mode", "unit_nav")
        return {
            "action": "maintain",
            "reason": f"价值因子卫星资产，当前使用 {nav_mode} 观察，维持配置。",
        }
    if asset_id == "ACTIVE_ADVANCED_MANUFACTURING":
        return {"action": "watch", "reason": "主动基金持仓，除非后续策略明确允许，不新增定投。"}
    if asset_id == "NONFERROUS_METALS":
        return {"action": "watch", "reason": "周期主题小仓位，维持观察，不新增定投。"}
    if asset_id == "GOLD":
        return {"action": "maintain", "reason": "对冲资产，维持每月定投。"}
    if asset_id == "BONDS":
        return {
            "action": "future_dca_tilt_to_core",
            "reason": "债券合计对成长型投资者偏高，但小账户阶段不建议立即卖出，未来新增资金向 CORE 倾斜。",
        }
    if contribution.get("total_return_rate", 0) < 0:
        return {"action": "watch", "reason": "可选报告显示收益贡献偏弱，先观察。"}
    if category == "SATELLITE":
        return {"action": "maintain", "reason": "卫星资产维持当前配置。"}
    return {"action": "maintain", "reason": "暂无特殊调整建议。"}


def build_dca_review(config):
    active, paused = split_dca_items(config.get("dca_plan", {}))
    weekly = [item for item in active if item.get("frequency") == "weekly"]
    monthly = [item for item in active if item.get("frequency") == "monthly"]
    weekly_total = sum(float(item.get("amount", 0)) for item in weekly)
    monthly_total = sum(float(item.get("amount", 0)) for item in monthly)
    by_asset = {}
    for item in weekly:
        entry = by_asset.setdefault(item.get("asset_id"), {"weekly": 0, "monthly": 0})
        entry["weekly"] += float(item.get("amount", 0))
    for item in monthly:
        entry = by_asset.setdefault(item.get("asset_id"), {"weekly": 0, "monthly": 0})
        entry["monthly"] += float(item.get("amount", 0))
    return {
        "weekly_total": weekly_total,
        "monthly_total": monthly_total,
        "paused_count": len(paused),
        "by_asset": by_asset,
        "assessment": [
            "保留当前定投计划。",
            "NASDAQ100 是长期核心，未来新增资金优先级最高。",
            "债券不新增或少新增。",
            "HSTECH 不使用子弹仓。",
            "主动基金和有色金属不新增定投。",
            "红利低波继续使用 accumulated_nav 观察。",
        ],
    }


def build_future_dca_tilt(category_summary, asset_advice):
    low_categories = [
        category for category, item in category_summary.items()
        if item["status"] == "underweight"
    ]
    high_categories = [
        category for category, item in category_summary.items()
        if item["current_weight"] > item["target_weight"]
    ]
    priority_assets = [
        item["asset_id"] for item in asset_advice
        if item["action"] in ("increase_dca", "maintain_high_priority")
    ]
    return {
        "priority_categories": low_categories or ["CORE"],
        "de_emphasize_categories": high_categories,
        "priority_assets": priority_assets or ["NASDAQ100"],
        "notes": [
            "第一版建议通过未来定投流向调整完成再平衡。",
            "不建议为了靠近目标权重立即卖出债券。",
            "补仓仍由 DrawdownGuard run 的回撤触发规则独立决定。",
        ],
    }


def build_conclusion(category_summary, asset_advice):
    underweight = [
        category for category, item in category_summary.items()
        if item["status"] == "underweight"
    ]
    overweight = [
        category for category, item in category_summary.items()
        if item["status"] == "overweight"
    ]
    defensive = category_summary.get("DEFENSIVE", {})
    sell_recommended = bool(overweight)
    return {
        "needs_immediate_rebalance": False,
        "underweight_categories": underweight,
        "overweight_categories": overweight,
        "sell_recommended": sell_recommended,
        "future_dca_bias": "CORE",
        "summary": (
            "当前组合不需要立即卖出再平衡；核心资产低配，防守资产高于目标但未超上限，"
            "建议通过未来定投逐步向 NASDAQ100 倾斜。"
            if defensive
            else "当前组合建议通过未来定投流向调整。"
        ),
    }


def summarize_rebalance_advice(report, detail=False):
    lines = ["再平衡建议"]
    if not report:
        lines.append("暂无再平衡建议。")
        return "\n".join(lines)

    lines.append("当前组合：")
    for category in ("CASH", "CORE", "SATELLITE", "DEFENSIVE"):
        item = report.get("category_summary", {}).get(category, {})
        lines.append(
            f"- {category} {item.get('current_weight', 0) * 100:.2f}%："
            f"{_category_text(category, item)}"
        )

    lines.append("基金级建议：")
    for item in report.get("asset_advice", []):
        lines.append(f"- {item['asset_id']}：{_action_text(item['action'])}，{item['reason']}")

    conclusion = report.get("conclusion", {})
    lines.append(f"结论：{conclusion.get('summary')}")
    lines.append("说明：本模块只生成建议，不自动交易。")

    if detail:
        lines.append("大类权重偏离表：")
        for category in ("CASH", "CORE", "SATELLITE", "DEFENSIVE"):
            item = report.get("category_summary", {}).get(category, {})
            lines.append(
                f"- {category} | 当前 {item.get('current_weight', 0) * 100:.2f}% | "
                f"目标 {item.get('target_weight', 0) * 100:.2f}% | "
                f"偏离 {item.get('deviation', 0) * 100:.2f}% | "
                f"状态 {item.get('status')} | 动作 {item.get('action')}"
            )
        lines.append("当前 DCA 评估：")
        dca_review = report.get("dca_review", {})
        lines.append(f"- 周定投合计：{dca_review.get('weekly_total', 0):.2f} 元")
        lines.append(f"- 月定投合计：{dca_review.get('monthly_total', 0):.2f} 元")
        for note in dca_review.get("assessment", []):
            lines.append(f"- {note}")
        tilt = report.get("suggested_future_dca_tilt", {})
        lines.append(f"未来定投优先大类：{', '.join(tilt.get('priority_categories', []))}")
        lines.append(f"未来定投优先资产：{', '.join(tilt.get('priority_assets', []))}")

    return "\n".join(lines)


def _category_text(category, item):
    if category == "CASH" and item.get("health") == "healthy":
        return "健康"
    if category == "CORE":
        if item.get("status") == "underweight":
            return "低于目标，建议未来定投继续偏向 NASDAQ100"
    if category == "SATELLITE":
        return "合理，维持" if item.get("status") == "neutral" else item.get("status")
    if category == "DEFENSIVE":
        if item.get("current_weight", 0) > item.get("target_weight", 0):
            return "偏高但未超上限，建议不卖出，未来新增资金向核心资产倾斜"
    return item.get("reason", item.get("status", "N/A"))


def _action_text(action):
    labels = {
        "increase_dca": "优先定投",
        "maintain": "维持",
        "reduce_dca": "减少定投",
        "pause_dca": "暂停定投",
        "watch": "观察",
        "no_action": "不操作",
        "future_dca_tilt_to_core": "未来定投向核心倾斜",
        "maintain_high_priority": "高优先级维持",
    }
    return labels.get(action, action)
