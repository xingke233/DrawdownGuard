from datetime import date, timedelta
from math import ceil


class StrategyBacktester:
    def __init__(self, config):
        self.config = config
        self.backtest_config = config.get("backtest", {})
        self.window = int(config.get("peak_window_trading_days", 250))
        self.round_to = int(config.get("round_amount_to", 10))
        self.levels = [
            (str(item["drawdown_percent"]), item["cash_ratio"])
            for item in sorted(config["replenishment_levels"], key=lambda x: x["drawdown_percent"])
        ]
        self.start_date = self.backtest_config.get("start_date", "1900-01-01")
        self.initial_cash = int(self.backtest_config.get("initial_cash", config["bullet_account"]["balance"]))
        self.monthly_cash_addition = int(self.backtest_config.get("monthly_cash_addition", 0))

    def run(self, fund_histories):
        return {
            "backtest": self.backtest_config,
            "fund_reports": [
                self.run_fund(fund, history) for fund, history in fund_histories if history
            ],
        }

    def run_fund(self, fund, history):
        full_history = sorted(history, key=lambda item: item["date"])
        filtered_history = [item for item in full_history if item["date"] >= self.start_date]
        remaining_cash = self.initial_cash
        total_invested = 0
        total_shares = 0
        events = []
        series = []
        triggered_levels = {level: False for level, _ in self.levels}
        trigger_count_by_level = {level: 0 for level, _ in self.levels}
        max_drawdown_seen = 0
        last_cash_addition_month = None

        for current in filtered_history:
            if self.monthly_cash_addition > 0:
                current_month = current["date"][:7]
                if current_month != last_cash_addition_month:
                    remaining_cash += self.monthly_cash_addition
                    last_cash_addition_month = current_month

            history_until_date = [item for item in full_history if item["date"] <= current["date"]]
            recent = history_until_date[-self.window :]
            previous_peak = max(item["nav"] for item in recent[:-1]) if len(recent) > 1 else current["nav"]
            peak_nav = max(item["nav"] for item in recent)
            current_nav = current["nav"]

            if current_nav > previous_peak:
                triggered_levels = {level: False for level, _ in self.levels}

            drawdown = (current_nav - peak_nav) / peak_nav if peak_nav else 0
            max_drawdown_seen = min(max_drawdown_seen, drawdown)
            drawdown_percent = abs(drawdown * 100)

            for level, cash_ratio in self.levels:
                if drawdown_percent < int(level) or triggered_levels[level]:
                    continue

                amount = min(self._round_up(remaining_cash * cash_ratio), remaining_cash)
                triggered_levels[level] = True
                if amount <= 0:
                    continue

                remaining_cash -= amount
                total_invested += amount
                shares = amount / current_nav if current_nav else 0
                total_shares += shares
                trigger_count_by_level[level] += 1
                events.append(
                    {
                        "date": current["date"],
                        "nav": current_nav,
                        "peak_nav": peak_nav,
                        "drawdown": drawdown,
                        "level": level,
                        "amount": amount,
                        "shares": shares,
                        "cash_after": remaining_cash,
                    }
                )

            series.append(
                {
                    "date": current["date"],
                    "nav": current_nav,
                    "peak_nav": peak_nav,
                    "drawdown": drawdown,
                    "cash_after": remaining_cash,
                }
            )

        final_nav = filtered_history[-1]["nav"] if filtered_history else None
        final_market_value = total_shares * final_nav if final_nav is not None else 0
        total_profit = final_market_value - total_invested
        total_return_rate = total_profit / total_invested if total_invested > 0 else 0

        return {
            "fund_code": fund["code"],
            "fund_name": fund["name"],
            "start_date": self.start_date,
            "end_date": filtered_history[-1]["date"] if filtered_history else None,
            "initial_cash": self.initial_cash,
            "final_cash": remaining_cash,
            "total_invested": total_invested,
            "total_shares": total_shares,
            "final_nav": final_nav,
            "final_market_value": final_market_value,
            "total_profit": total_profit,
            "total_return_rate": total_return_rate,
            "trigger_count_total": len(events),
            "trigger_count_by_level": trigger_count_by_level,
            "max_drawdown_seen": max_drawdown_seen,
            "series": series,
            "events": events,
        }

    def _round_up(self, amount):
        return int(ceil(amount / self.round_to) * self.round_to)


class AssetBacktester(StrategyBacktester):
    def run(self, fund_histories):
        history_by_code = {
            fund["code"]: sorted(history, key=lambda item: item["date"])
            for fund, history in fund_histories
            if history
        }
        fund_by_code = {fund["code"]: fund for fund, history in fund_histories if history}
        return {
            "backtest": self.backtest_config,
            "asset_config": self.config.get("asset_config", {}),
            "asset_reports": [
                self.run_asset(asset, history_by_code, fund_by_code)
                for asset in self.config.get("asset_config", {}).get("assets", [])
                if self._asset_has_histories(asset, history_by_code)
            ],
        }

    def run_asset(self, asset, history_by_code, fund_by_code):
        asset_history = self._build_asset_history(asset, history_by_code)
        asset_fund = {
            "code": asset["code"],
            "name": asset.get("name", asset["code"]),
        }
        report = self.run_fund(asset_fund, asset_history)
        report["asset_code"] = report.pop("fund_code")
        report["asset_name"] = report.pop("fund_name")
        report["fund_codes"] = list(asset.get("fund_codes", []))
        report["funds"] = [
            {
                "fund_code": code,
                "fund_name": fund_by_code.get(code, {}).get("name", code),
            }
            for code in asset.get("fund_codes", [])
        ]
        for event in report["events"]:
            event["asset_code"] = report["asset_code"]
        return report

    def _asset_has_histories(self, asset, history_by_code):
        return all(code in history_by_code for code in asset.get("fund_codes", []))

    def _build_asset_history(self, asset, history_by_code):
        fund_codes = asset.get("fund_codes", [])
        if not fund_codes:
            return []

        date_sets = []
        nav_by_code = {}
        for code in fund_codes:
            nav_by_date = {
                item["date"]: item["nav"]
                for item in history_by_code.get(code, [])
                if item.get("nav") is not None
            }
            if not nav_by_date:
                return []
            nav_by_code[code] = nav_by_date
            date_sets.append(set(nav_by_date))

        common_dates = sorted(set.intersection(*date_sets))
        if not common_dates:
            return []

        base_date = common_dates[0]
        base_navs = {code: nav_by_code[code][base_date] for code in fund_codes}
        history = []
        for date_value in common_dates:
            normalized_values = [
                nav_by_code[code][date_value] / base_navs[code]
                for code in fund_codes
                if base_navs[code]
            ]
            if len(normalized_values) != len(fund_codes):
                continue
            history.append(
                {
                    "date": date_value,
                    "nav": sum(normalized_values) / len(normalized_values),
                }
            )
        return history


class PortfolioBacktester:
    def __init__(self, config):
        self.config = config
        self.portfolio_config = config.get("portfolio_backtest", {})
        self.window = int(config.get("peak_window_trading_days", 250))
        self.round_to = int(config.get("round_amount_to", 10))
        self.start_date = self.portfolio_config.get("start_date", "1900-01-01")
        self.end_date = self.portfolio_config.get("end_date")
        self.bullet_cash_initial = int(self.portfolio_config.get("bullet_cash_initial", 0))
        self.bullet_cash_monthly_addition = int(
            self.portfolio_config.get("bullet_cash_monthly_addition", 0)
        )
        self.dca_weekday = int(self.portfolio_config.get("dca_weekday", 0))

    def run(self, representative_histories):
        asset_states = [
            self._build_asset_state(asset, representative_histories)
            for asset in self.portfolio_config.get("assets", [])
        ]
        active_states = [state for state in asset_states if state["status"] == "active"]
        skipped_assets = [
            {
                "asset_id": state["asset_id"],
            "asset_name": state["asset_name"],
            "representative_fund": state["representative_fund"],
            "nav_mode": state["nav_mode"],
            "role": state.get("role"),
            "current_amount": state.get("current_amount", 0),
            "current_weight": state.get("current_weight", 0),
            "skip_reason": state["skip_reason"],
        }
            for state in asset_states
            if state["status"] == "skipped"
        ]

        bullet_cash = self.bullet_cash_initial
        last_bullet_addition_month = None
        all_dates = sorted({item["date"] for state in active_states for item in state["history"]})

        for current_date in all_dates:
            current_month = current_date[:7]
            if self.bullet_cash_monthly_addition > 0 and current_month != last_bullet_addition_month:
                bullet_cash += self.bullet_cash_monthly_addition
                last_bullet_addition_month = current_month

            for state in active_states:
                nav = state["nav_by_date"].get(current_date)
                if nav is None:
                    continue
                bullet_cash = self._process_asset_day(state, current_date, nav, bullet_cash)

        asset_reports = [self._finalize_asset(state) for state in asset_states]
        active_reports = [item for item in asset_reports if item["status"] == "active"]
        total_dca_invested = sum(item["dca_invested"] for item in active_reports)
        total_bullet_invested = sum(item["bullet_invested"] for item in active_reports)
        total_invested = total_dca_invested + total_bullet_invested
        final_market_value = sum(item["final_market_value"] for item in active_reports)
        total_profit = final_market_value - total_invested

        return {
            "portfolio_backtest": self.portfolio_config,
            "portfolio_summary": {
                "requested_start_date": self.start_date,
                "requested_end_date": self.end_date,
                "start_date": all_dates[0] if all_dates else None,
                "end_date": all_dates[-1] if all_dates else None,
                "total_dca_invested": total_dca_invested,
                "total_bullet_invested": total_bullet_invested,
                "total_invested": total_invested,
                "final_market_value": final_market_value,
                "total_profit": total_profit,
                "total_return_rate": total_profit / total_invested if total_invested > 0 else 0,
                "bullet_cash_initial": self.bullet_cash_initial,
                "bullet_cash_final": bullet_cash,
                "trigger_count_total": sum(item["trigger_count_total"] for item in active_reports),
                "skipped_assets": skipped_assets,
            },
            "assets": asset_reports,
            "warnings": [
                f"{item['asset_id']} skipped: {item['skip_reason']}" for item in skipped_assets
            ],
        }

    def _build_asset_state(self, asset, representative_histories):
        representative_fund = asset.get("representative_fund", "")
        base_state = {
            "asset_id": asset["asset_id"],
            "asset_name": asset["asset_name"],
            "representative_fund": representative_fund,
            "nav_mode": asset.get("nav_mode", "unit_nav"),
            "role": asset.get("role"),
            "current_amount": float(asset.get("current_amount", 0)),
            "current_weight": float(asset.get("current_weight", 0)),
            "strategy": asset.get("strategy", "dca_only"),
            "weekly_dca_amount": int(asset.get("weekly_dca_amount", 0)),
            "dca_schedules": self._build_dca_schedules(asset),
            "dca_schedule_states": [],
            "status": "active",
            "skip_reason": None,
            "history": [],
            "nav_by_date": {},
            "next_dca_date": _next_weekday(date.fromisoformat(self.start_date), self.dca_weekday),
            "triggered_levels": {},
            "trigger_count_by_level": {},
            "dca_invested": 0,
            "bullet_invested": 0,
            "total_shares": 0,
            "events": [],
            "series": [],
        }

        if not representative_fund or "请先" in representative_fund:
            return {**base_state, "status": "skipped", "skip_reason": "代表基金为配置占位。"}

        history = [
            item for item in representative_histories.get(representative_fund, [])
            if item["date"] >= self.start_date and (not self.end_date or item["date"] <= self.end_date)
        ]
        if not history:
            return {**base_state, "status": "skipped", "skip_reason": "代表基金净值数据缺失。"}

        levels = [
            (str(item["level"]), item["cash_ratio"])
            for item in sorted(asset.get("drawdown_levels", []), key=lambda item: item["level"])
        ]
        if not levels:
            levels = [
                (str(item["drawdown_percent"]), item["cash_ratio"])
                for item in sorted(
                    self.config.get("replenishment_levels", []),
                    key=lambda item: item["drawdown_percent"],
                )
            ]

        base_state["history"] = sorted(history, key=lambda item: item["date"])
        base_state["nav_by_date"] = {item["date"]: item["nav"] for item in base_state["history"]}
        base_state["next_dca_date"] = self._initial_dca_date(base_state["history"][0]["date"])
        base_state["dca_schedule_states"] = self._initialize_dca_schedule_states(
            base_state["dca_schedules"],
            base_state["history"][0]["date"],
        )
        base_state["levels"] = levels
        base_state["triggered_levels"] = {level: False for level, _ in levels}
        base_state["trigger_count_by_level"] = {level: 0 for level, _ in levels}
        return base_state

    def _process_asset_day(self, state, current_date, nav, bullet_cash):
        if state.get("dca_schedule_states"):
            self._process_scheduled_dca(state, current_date, nav, bullet_cash)
        else:
            self._process_legacy_weekly_dca(state, current_date, nav, bullet_cash)

        peak_nav, previous_peak = self._rolling_peaks(state, current_date, nav)
        if nav > previous_peak:
            state["triggered_levels"] = {level: False for level, _ in state["levels"]}

        drawdown = (nav - peak_nav) / peak_nav if peak_nav else 0
        if state["strategy"] == "drawdown_plus_dca":
            bullet_cash = self._process_drawdown_buy(state, current_date, nav, drawdown, peak_nav, bullet_cash)

        state["series"].append(
            {
                "date": current_date,
                "nav": nav,
                "peak_nav": peak_nav,
                "drawdown": drawdown,
                "bullet_cash_after": bullet_cash,
            }
        )
        return bullet_cash

    def _process_scheduled_dca(self, state, current_date, nav, bullet_cash):
        current_day = date.fromisoformat(current_date)
        for schedule_state in state["dca_schedule_states"]:
            if current_day < schedule_state["next_date"]:
                continue
            schedule = schedule_state["schedule"]
            amount = int(schedule.get("amount", 0))
            if amount > 0:
                shares = amount / nav if nav else 0
                state["dca_invested"] += amount
                state["total_shares"] += shares
                state["events"].append(
                    {
                        "date": current_date,
                        "type": "dca",
                        "nav": nav,
                        "amount": amount,
                        "shares": shares,
                        "level": None,
                        "drawdown": None,
                        "bullet_cash_after": bullet_cash,
                        "fund_code": schedule.get("fund_code", state["representative_fund"]),
                        "fund_name": schedule.get("fund_name", state["asset_name"]),
                        "frequency": schedule.get("frequency", "weekly"),
                    }
                )
            schedule_state["next_date"] = self._advance_schedule_date(
                schedule,
                schedule_state["next_date"],
            )
            while current_day >= schedule_state["next_date"]:
                schedule_state["next_date"] = self._advance_schedule_date(
                    schedule,
                    schedule_state["next_date"],
                )

    def _process_legacy_weekly_dca(self, state, current_date, nav, bullet_cash):
        if date.fromisoformat(current_date) >= state["next_dca_date"]:
            amount = state["weekly_dca_amount"]
            if amount > 0:
                shares = amount / nav if nav else 0
                state["dca_invested"] += amount
                state["total_shares"] += shares
                state["events"].append(
                    {
                        "date": current_date,
                        "type": "dca",
                        "nav": nav,
                        "amount": amount,
                        "shares": shares,
                        "level": None,
                        "drawdown": None,
                        "bullet_cash_after": bullet_cash,
                    }
                )
            state["next_dca_date"] += timedelta(days=7)
            while date.fromisoformat(current_date) >= state["next_dca_date"]:
                state["next_dca_date"] += timedelta(days=7)

    def _process_drawdown_buy(self, state, current_date, nav, drawdown, peak_nav, bullet_cash):
        drawdown_percent = abs(drawdown * 100)
        for level, cash_ratio in state["levels"]:
            if drawdown_percent < int(level) or state["triggered_levels"][level]:
                continue

            amount = min(self._round_up(bullet_cash * cash_ratio), bullet_cash)
            state["triggered_levels"][level] = True
            if amount <= 0:
                continue

            bullet_cash -= amount
            shares = amount / nav if nav else 0
            state["bullet_invested"] += amount
            state["total_shares"] += shares
            state["trigger_count_by_level"][level] += 1
            state["events"].append(
                {
                    "date": current_date,
                    "type": "drawdown_buy",
                    "nav": nav,
                    "amount": amount,
                    "shares": shares,
                    "level": level,
                    "drawdown": drawdown,
                    "peak_nav": peak_nav,
                    "bullet_cash_after": bullet_cash,
                }
            )
        return bullet_cash

    def _rolling_peaks(self, state, current_date, nav):
        history_until_date = [item for item in state["history"] if item["date"] <= current_date]
        recent = history_until_date[-self.window :]
        previous_peak = max(item["nav"] for item in recent[:-1]) if len(recent) > 1 else nav
        peak_nav = max(item["nav"] for item in recent) if recent else nav
        return peak_nav, previous_peak

    def _finalize_asset(self, state):
        if state["status"] == "skipped":
            return {
                "asset_id": state["asset_id"],
                "asset_name": state["asset_name"],
                "representative_fund": state["representative_fund"],
                "nav_mode": state["nav_mode"],
                "strategy": state["strategy"],
                "role": state.get("role"),
                "current_amount": state.get("current_amount", 0),
                "current_weight": state.get("current_weight", 0),
                "status": "skipped",
                "skip_reason": state["skip_reason"],
                "dca_invested": 0,
                "bullet_invested": 0,
                "total_invested": 0,
                "total_shares": 0,
                "final_nav": None,
                "final_market_value": 0,
                "total_profit": 0,
                "total_return_rate": 0,
                "trigger_count_total": 0,
                "trigger_count_by_level": {},
                "events": [],
            }

        final_nav = state["history"][-1]["nav"]
        total_invested = state["dca_invested"] + state["bullet_invested"]
        final_market_value = state["total_shares"] * final_nav
        total_profit = final_market_value - total_invested
        return {
            "asset_id": state["asset_id"],
            "asset_name": state["asset_name"],
            "representative_fund": state["representative_fund"],
            "nav_mode": state["nav_mode"],
            "strategy": state["strategy"],
            "role": state.get("role"),
            "current_amount": state.get("current_amount", 0),
            "current_weight": state.get("current_weight", 0),
            "status": "active",
            "skip_reason": None,
            "start_date": state["history"][0]["date"],
            "end_date": state["history"][-1]["date"],
            "dca_invested": state["dca_invested"],
            "bullet_invested": state["bullet_invested"],
            "total_invested": total_invested,
            "total_shares": state["total_shares"],
            "final_nav": final_nav,
            "final_market_value": final_market_value,
            "total_profit": total_profit,
            "total_return_rate": total_profit / total_invested if total_invested > 0 else 0,
            "trigger_count_total": sum(state["trigger_count_by_level"].values()),
            "trigger_count_by_level": state["trigger_count_by_level"],
            "events": state["events"],
            "series": state["series"],
        }

    def _round_up(self, amount):
        return int(ceil(amount / self.round_to) * self.round_to)

    def _initial_dca_date(self, first_history_date):
        requested_start = date.fromisoformat(self.start_date)
        first_available = date.fromisoformat(first_history_date)
        if (first_available - requested_start).days > 7:
            return first_available
        return _next_weekday(requested_start, self.dca_weekday)

    def _build_dca_schedules(self, asset):
        schedules = asset.get("dca_schedules") or []
        if schedules:
            return [dict(item) for item in schedules if item.get("status", "active") == "active"]
        weekly_amount = int(asset.get("weekly_dca_amount", 0))
        if weekly_amount <= 0:
            return []
        return [
            {
                "asset_id": asset.get("asset_id"),
                "fund_code": asset.get("representative_fund"),
                "fund_name": asset.get("asset_name"),
                "amount": weekly_amount,
                "frequency": "weekly",
                "weekday": self.dca_weekday,
            }
        ]

    def _initialize_dca_schedule_states(self, schedules, first_history_date):
        return [
            {
                "schedule": schedule,
                "next_date": self._initial_schedule_date(schedule, first_history_date),
            }
            for schedule in schedules
        ]

    def _initial_schedule_date(self, schedule, first_history_date):
        requested_start = date.fromisoformat(self.start_date)
        first_available = date.fromisoformat(first_history_date)
        if (first_available - requested_start).days > 31:
            return first_available
        if schedule.get("frequency") == "monthly":
            day = int(schedule.get("day", 1))
            next_date = _month_date(requested_start.year, requested_start.month, day)
            if next_date < requested_start:
                next_date = _add_month(next_date, day)
            return next_date
        weekday = int(schedule.get("weekday", self.dca_weekday))
        return _next_weekday(requested_start, weekday)

    def _advance_schedule_date(self, schedule, current_next_date):
        if schedule.get("frequency") == "monthly":
            return _add_month(current_next_date, int(schedule.get("day", 1)))
        return current_next_date + timedelta(days=7)


def summarize_backtest_report(report):
    fund_reports = report.get("fund_reports", [])
    total_triggers = sum(item.get("trigger_count_total", 0) for item in fund_reports)
    total_invested = sum(item.get("total_invested", 0) for item in fund_reports)
    lines = ["最近一次回测摘要"]
    lines.append(f"基金数量：{len(fund_reports)}")
    lines.append(f"总触发次数：{total_triggers}")
    lines.append(f"累计投入金额：{total_invested} 元")
    for item in fund_reports:
        lines.append(
            f"{item['fund_code']} | {item['fund_name']} | "
            f"触发 {item['trigger_count_total']} 次 | 投入 {item['total_invested']} 元 | "
            f"剩余现金 {item['final_cash']} 元 | 最大回撤 {item['max_drawdown_seen'] * 100:.2f}%"
        )
    return "\n".join(lines)


def summarize_asset_backtest_report(report):
    asset_reports = report.get("asset_reports", [])
    total_triggers = sum(item.get("trigger_count_total", 0) for item in asset_reports)
    total_invested = sum(item.get("total_invested", 0) for item in asset_reports)
    lines = ["资产级回测摘要"]
    lines.append(f"资产数量：{len(asset_reports)}")
    lines.append(f"资产级总触发次数：{total_triggers}")
    lines.append(f"资产级累计现金消耗：{total_invested} 元")
    for item in asset_reports:
        lines.append(
            f"{item['asset_code']} | {item['asset_name']} | "
            f"触发 {item['trigger_count_total']} 次 | 投入 {item['total_invested']} 元 | "
            f"剩余现金 {item['final_cash']} 元 | 总收益率 {_format_rate(item.get('total_return_rate', 0))}"
        )
    lines.append("说明：资产级 NAV 为资产内基金按首个共同日期归一化后的等权平均，仅用于策略对照回测。")
    return "\n".join(lines)


def summarize_portfolio_backtest_report(report):
    summary = report.get("portfolio_summary", {})
    lines = ["组合回测摘要"]
    if not summary:
        lines.append("暂无组合回测结果。")
        return "\n".join(lines)

    lines.append(f"回测区间：{summary.get('start_date')} 至 {summary.get('end_date')}")
    lines.append(f"组合总投入：{summary.get('total_invested', 0):.2f} 元")
    lines.append(f"定投投入：{summary.get('total_dca_invested', 0):.2f} 元")
    lines.append(f"补仓投入：{summary.get('total_bullet_invested', 0):.2f} 元")
    lines.append(f"组合估算市值：{summary.get('final_market_value', 0):.2f} 元")
    lines.append(f"浮盈亏：{summary.get('total_profit', 0):.2f} 元")
    lines.append(f"总收益率：{_format_rate(summary.get('total_return_rate', 0))}")
    lines.append(f"子弹仓剩余：{summary.get('bullet_cash_final', 0):.2f} 元")
    lines.append(f"补仓触发次数：{summary.get('trigger_count_total', 0)}")

    active_assets = [asset for asset in report.get("assets", []) if asset.get("status") == "active"]
    if active_assets:
        lines.append("资产明细：")
        for asset in active_assets:
            lines.append(
                f"- {asset['asset_id']} | {asset['asset_name']} | "
                f"净值口径 {asset.get('nav_mode', 'unit_nav')} | "
                f"投入 {asset['total_invested']:.2f} 元 | "
                f"定投 {asset['dca_invested']:.2f} 元 | "
                f"补仓 {asset['bullet_invested']:.2f} 元 | "
                f"市值 {asset['final_market_value']:.2f} 元 | "
                f"收益率 {_format_rate(asset['total_return_rate'])} | "
                f"触发 {asset['trigger_count_total']} 次"
            )

    skipped_assets = summary.get("skipped_assets", [])
    if skipped_assets:
        lines.append("跳过资产：")
        for asset in skipped_assets:
            lines.append(f"- {asset['asset_id']} | {asset['asset_name']} | {asset['skip_reason']}")

    lines.append("说明：组合收益为基于历史净值、定投和补仓事件的策略模拟收益，不代表真实账户收益。")
    return "\n".join(lines)


def summarize_scenarios_report(report):
    scenario_summaries = report.get("summary", {}).get("scenarios", [])
    lines = ["多参数回测场景摘要"]
    lines.append(f"场景数量：{len(report.get('scenarios', []))}")
    if not scenario_summaries:
        lines.append("暂无可比较的基金回测结果。")
        return "\n".join(lines)

    for item in scenario_summaries:
        lines.append(
            f"{item['scenario_id']} | 初始 {item['initial_cash']} 元 | "
            f"月追加 {item['monthly_cash_addition']} 元 | "
            f"触发 {item['trigger_count_total']} 次 | 投入 {item['total_invested']} 元 | "
            f"剩余现金合计 {item['final_cash_total']} 元"
        )

    return "\n".join(lines)


def summarize_backtest_returns(report):
    fund_reports = report.get("fund_reports", [])
    lines = ["最近一次回测收益估算"]
    if not fund_reports:
        lines.append("暂无基金回测结果。")
        return "\n".join(lines)

    for item in fund_reports:
        lines.append(_format_return_line(item))
    lines.append("说明：收益率为基于历史净值和补仓事件的策略模拟收益，不代表真实账户收益。")
    return "\n".join(lines)


def summarize_scenarios_returns(report):
    lines = ["多参数场景收益估算"]
    scenarios = report.get("scenarios", [])
    if not scenarios:
        lines.append("暂无场景回测结果。")
        return "\n".join(lines)

    for scenario in scenarios:
        funds = scenario.get("funds", [])
        total_invested = sum(fund.get("total_invested", 0) for fund in funds)
        market_value = sum(fund.get("final_market_value", 0) for fund in funds)
        total_profit = market_value - total_invested
        return_rate = total_profit / total_invested if total_invested > 0 else 0
        lines.append(
            f"{scenario['scenario_id']} | 初始 {scenario['initial_cash']} 元 | "
            f"月追加 {scenario['monthly_cash_addition']} 元 | "
            f"投入 {total_invested:.2f} 元 | 市值 {market_value:.2f} 元 | "
            f"浮盈 {total_profit:.2f} 元 | 总收益率 {_format_rate(return_rate)}"
        )
        for fund in funds:
            lines.append(f"  {_format_return_line(fund)}")
    lines.append("说明：收益率为基于历史净值和补仓事件的策略模拟收益，不代表真实账户收益。")
    return "\n".join(lines)


def run_backtest_scenarios(config, fund_histories, initial_cash_values=None, monthly_cash_values=None):
    initial_cash_values = initial_cash_values or [2000, 3000, 5000]
    monthly_cash_values = monthly_cash_values or [0, 200, 500]
    scenarios = []
    scenario_index = 1

    for initial_cash in initial_cash_values:
        for monthly_cash_addition in monthly_cash_values:
            scenario_config = {
                **config,
                "backtest": {
                    **config.get("backtest", {}),
                    "initial_cash": initial_cash,
                    "monthly_cash_addition": monthly_cash_addition,
                },
            }
            report = StrategyBacktester(scenario_config).run(fund_histories)
            scenarios.append(
                {
                    "scenario_id": f"S{scenario_index:03d}",
                    "initial_cash": initial_cash,
                    "monthly_cash_addition": monthly_cash_addition,
                    "funds": [_compact_fund_report(item) for item in report["fund_reports"]],
                }
            )
            scenario_index += 1

    return {"scenarios": scenarios, "summary": _build_scenarios_summary(scenarios)}


def _build_scenarios_summary(scenarios):
    scenario_summaries = []
    fund_comparisons = {}

    for scenario in scenarios:
        funds = scenario["funds"]
        scenario_summaries.append(
            {
                "scenario_id": scenario["scenario_id"],
                "initial_cash": scenario["initial_cash"],
                "monthly_cash_addition": scenario["monthly_cash_addition"],
                "fund_count": len(funds),
                "trigger_count_total": sum(fund["trigger_count_total"] for fund in funds),
                "total_invested": sum(fund["total_invested"] for fund in funds),
                "final_market_value_total": sum(fund["final_market_value"] for fund in funds),
                "total_profit": sum(fund["total_profit"] for fund in funds),
                "total_return_rate": _sum_return_rate(funds),
                "final_cash_total": sum(fund["final_cash"] for fund in funds),
            }
        )

        for fund in funds:
            fund_key = fund["fund_code"]
            fund_comparisons.setdefault(
                fund_key,
                {
                    "fund_code": fund["fund_code"],
                    "fund_name": fund["fund_name"],
                    "scenarios": [],
                },
            )
            fund_comparisons[fund_key]["scenarios"].append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "initial_cash": scenario["initial_cash"],
                    "monthly_cash_addition": scenario["monthly_cash_addition"],
                    "trigger_count_total": fund["trigger_count_total"],
                    "total_invested": fund["total_invested"],
                    "final_cash": fund["final_cash"],
                    "final_market_value": fund["final_market_value"],
                    "total_profit": fund["total_profit"],
                    "total_return_rate": fund["total_return_rate"],
                    "max_drawdown_seen": fund["max_drawdown_seen"],
                }
            )

    return {
        "scenarios": scenario_summaries,
        "fund_comparisons": list(fund_comparisons.values()),
    }


def _compact_fund_report(report):
    return {
        "fund_code": report["fund_code"],
        "fund_name": report["fund_name"],
        "start_date": report["start_date"],
        "end_date": report["end_date"],
        "initial_cash": report["initial_cash"],
        "trigger_count_total": report["trigger_count_total"],
        "trigger_count_by_level": report["trigger_count_by_level"],
        "total_invested": report["total_invested"],
        "total_shares": report["total_shares"],
        "final_nav": report["final_nav"],
        "final_market_value": report["final_market_value"],
        "total_profit": report["total_profit"],
        "total_return_rate": report["total_return_rate"],
        "final_cash": report["final_cash"],
        "max_drawdown_seen": report["max_drawdown_seen"],
        "series": report["series"],
        "events": report["events"],
    }


def _format_return_line(item):
    return (
        f"{item['fund_code']} | {item['fund_name']} | "
        f"投入 {item.get('total_invested', 0):.2f} 元 | "
        f"估算市值 {item.get('final_market_value', 0):.2f} 元 | "
        f"浮盈 {item.get('total_profit', 0):.2f} 元 | "
        f"总收益率 {_format_rate(item.get('total_return_rate', 0))}"
    )


def _format_rate(value):
    return f"{value * 100:.2f}%" if value is not None else "N/A"


def _sum_return_rate(funds):
    total_invested = sum(fund["total_invested"] for fund in funds)
    total_profit = sum(fund["total_profit"] for fund in funds)
    return total_profit / total_invested if total_invested > 0 else 0


def _next_weekday(value, weekday):
    days_until_weekday = (weekday - value.weekday()) % 7
    return value + timedelta(days=days_until_weekday)


def _month_date(year, month, day):
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(day, last_day))


def _add_month(value, day):
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    return _month_date(year, month, day)
