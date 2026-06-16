from datetime import date, timedelta
from math import ceil, floor


DEFAULT_TAKE_PROFIT_RULES = [
    {"level": 15, "base_sell_percent": 15, "step_sell_percent": 1, "next_level": 25},
    {"level": 25, "base_sell_percent": 20, "step_sell_percent": 2, "next_level": 35},
    {"level": 35, "base_sell_percent": 25, "step_sell_percent": 0, "next_level": None},
]
EPSILON = 1e-9


class TakeProfitBacktester:
    def __init__(self, config):
        self.config = config
        self.portfolio_config = config.get("portfolio_backtest", {})
        self.take_profit_config = config.get("take_profit_backtest", {})
        self.window = int(config.get("peak_window_trading_days", 250))
        self.round_to = int(config.get("round_amount_to", 10))
        self.start_date = self.take_profit_config.get(
            "start_date", self.portfolio_config.get("start_date", "1900-01-01")
        )
        self.end_date = self.take_profit_config.get("end_date")
        self.asset = self._find_nasdaq_asset()
        self.fund_code = self.asset.get("representative_fund", "270042")
        self.weekly_dca_amount = int(self.asset.get("weekly_dca_amount", 0))
        self.dca_weekday = int(self.portfolio_config.get("dca_weekday", 0))
        self.bullet_cash_initial = int(self.portfolio_config.get("bullet_cash_initial", 0))
        self.bullet_cash_monthly_addition = int(
            self.portfolio_config.get("bullet_cash_monthly_addition", 0)
        )
        self.drawdown_levels = self._drawdown_levels()
        self.take_profit_rules = _normalize_take_profit_rules(
            self.take_profit_config.get("rules", DEFAULT_TAKE_PROFIT_RULES)
        )

    def run(self, history):
        return self._run(history, enable_take_profit=True)

    def run_without_take_profit(self, history):
        return self._run(history, enable_take_profit=False)

    def run_compact(self, history):
        return self._run(history, enable_take_profit=True, compact=True)

    def _run(self, history, enable_take_profit, compact=False):
        full_history = sorted(history, key=lambda item: item["date"])
        filtered_history = [
            item
            for item in full_history
            if item["date"] >= self.start_date and (not self.end_date or item["date"] <= self.end_date)
        ]
        if not filtered_history:
            return self._empty_report()

        bullet_cash = self.bullet_cash_initial
        last_bullet_addition_month = None
        next_dca_date = _next_weekday(date.fromisoformat(filtered_history[0]["date"]), self.dca_weekday)
        triggered_levels = {level: False for level, _ in self.drawdown_levels}

        total_dca_invested = 0
        total_buy_amount = 0
        total_sell_amount = 0
        total_shares = 0
        cost_basis = 0
        buy_events = []
        sell_events = []
        events = []
        series = []
        drawdown_buy_count = 0
        sell_count_by_level = {}
        take_profit_base_value = None
        sold_percent_by_level = {str(rule["level"]): 0 for rule in self.take_profit_rules}

        for current in filtered_history:
            current_date = current["date"]
            nav = current["nav"]
            current_month = current_date[:7]
            if self.bullet_cash_monthly_addition > 0 and current_month != last_bullet_addition_month:
                bullet_cash += self.bullet_cash_monthly_addition
                last_bullet_addition_month = current_month

            if date.fromisoformat(current_date) >= next_dca_date:
                if self.weekly_dca_amount > 0:
                    shares = self.weekly_dca_amount / nav if nav else 0
                    total_dca_invested += self.weekly_dca_amount
                    total_shares += shares
                    cost_basis += self.weekly_dca_amount
                    event = self._event(
                        current_date, "dca", nav, self.weekly_dca_amount, shares, bullet_cash,
                        total_shares, cost_basis, None
                    )
                    if not compact:
                        buy_events.append(event)
                        events.append(event)
                next_dca_date += timedelta(days=7)
                while date.fromisoformat(current_date) >= next_dca_date:
                    next_dca_date += timedelta(days=7)

            peak_nav, previous_peak = self._rolling_peaks(filtered_history, current_date, nav)
            if nav > previous_peak:
                triggered_levels = {level: False for level, _ in self.drawdown_levels}

            drawdown = (nav - peak_nav) / peak_nav if peak_nav else 0
            drawdown_percent = abs(drawdown * 100)
            for level, cash_ratio in self.drawdown_levels:
                if drawdown_percent < int(level) or triggered_levels[level]:
                    continue
                amount = min(self._round_up(bullet_cash * cash_ratio), bullet_cash)
                triggered_levels[level] = True
                if amount <= 0:
                    continue
                bullet_cash -= amount
                shares = amount / nav if nav else 0
                total_buy_amount += amount
                total_shares += shares
                cost_basis += amount
                drawdown_buy_count += 1
                event = self._event(
                    current_date, "drawdown_buy", nav, amount, shares, bullet_cash,
                    total_shares, cost_basis, level
                )
                event["drawdown"] = drawdown
                if not compact:
                    buy_events.append(event)
                    events.append(event)

            position_market_value = total_shares * nav
            position_return_rate = _return_rate(position_market_value, cost_basis)
            if cost_basis > 0 and position_return_rate <= 0:
                take_profit_base_value = None
                sold_percent_by_level = {str(rule["level"]): 0 for rule in self.take_profit_rules}
            first_take_profit_level = self.take_profit_rules[0]["level"] / 100
            if enable_take_profit and cost_basis > 0 and position_return_rate + EPSILON >= first_take_profit_level:
                if take_profit_base_value is None:
                    take_profit_base_value = position_market_value
                sell_candidates = self._take_profit_sells(
                    current_date,
                    nav,
                    position_return_rate,
                    take_profit_base_value,
                    sold_percent_by_level,
                    total_shares,
                    cost_basis,
                    bullet_cash,
                )
                for sell_event in sell_candidates:
                    position_market_value = total_shares * nav
                    sell_amount = min(sell_event["amount"], position_market_value)
                    sell_shares = sell_amount / nav if nav else 0
                    cost_reduction = cost_basis * (sell_shares / total_shares) if total_shares else 0
                    total_shares -= sell_shares
                    cost_basis -= cost_reduction
                    bullet_cash += sell_amount
                    total_sell_amount += sell_amount
                    sell_count_by_level[str(sell_event["level"])] = (
                        sell_count_by_level.get(str(sell_event["level"]), 0) + 1
                    )
                    sell_event.update(
                        {
                            "amount": sell_amount,
                            "shares": sell_shares,
                            "cash_after": bullet_cash,
                            "position_market_value": total_shares * nav,
                            "position_return_rate": _return_rate(total_shares * nav, cost_basis),
                        }
                    )
                    if sell_amount > 0 and not compact:
                        sell_events.append(sell_event)
                        events.append(sell_event)

            series.append(
                {
                    "date": current_date,
                    "nav": nav,
                    "position_market_value": total_shares * nav,
                    "position_return_rate": _return_rate(total_shares * nav, cost_basis),
                    "total_asset_value": total_shares * nav + bullet_cash,
                    "cash_after": bullet_cash,
                }
            )

        final_nav = filtered_history[-1]["nav"]
        final_market_value = total_shares * final_nav
        total_asset_value = final_market_value + bullet_cash
        capital_base = self.bullet_cash_initial + total_dca_invested
        total_profit = total_asset_value - capital_base
        return {
            "fund_code": self.fund_code,
            "asset_id": "NASDAQ100",
            "start_date": filtered_history[0]["date"],
            "end_date": filtered_history[-1]["date"],
            "total_dca_invested": total_dca_invested,
            "total_buy_amount": total_buy_amount,
            "total_sell_amount": total_sell_amount,
            "final_market_value": final_market_value,
            "final_cash": bullet_cash,
            "total_asset_value": total_asset_value,
            "total_profit": total_profit,
            "total_return_rate": total_profit / capital_base if capital_base > 0 else 0,
            "total_shares": total_shares,
            "buy_events": buy_events,
            "sell_events": sell_events,
            "events": events,
            "series": series,
            "trigger_count_buy": drawdown_buy_count,
            "trigger_count_sell": sum(sell_count_by_level.values()) if compact else len(sell_events),
            "sell_count_by_level": sell_count_by_level,
        }

    def _take_profit_sells(
        self,
        current_date,
        nav,
        position_return_rate,
        base_value,
        sold_percent_by_level,
        total_shares,
        cost_basis,
        bullet_cash,
    ):
        return_percent = position_return_rate * 100
        sell_events = []
        for rule in self.take_profit_rules:
            if return_percent + EPSILON < rule["level"]:
                continue
            level_key = str(rule["level"])
            target_percent = self._target_sold_percent(rule, return_percent)
            incremental_percent = target_percent - sold_percent_by_level[level_key]
            if incremental_percent <= 0:
                continue
            sold_percent_by_level[level_key] = target_percent
            amount = base_value * incremental_percent / 100
            sell_events.append(
                {
                    "date": current_date,
                    "type": "take_profit_sell",
                    "nav": nav,
                    "amount": amount,
                    "shares": 0,
                    "cash_after": bullet_cash,
                    "position_market_value": total_shares * nav,
                    "position_return_rate": _return_rate(total_shares * nav, cost_basis),
                    "level": str(rule["level"]),
                }
            )
        return sell_events

    def _target_sold_percent(self, rule, return_percent):
        if rule["next_level"] is None:
            return rule["base_sell_percent"]
        extra_steps = max(0, floor(return_percent + EPSILON) - rule["level"])
        extra_steps = min(extra_steps, rule["next_level"] - rule["level"] - 1)
        return rule["base_sell_percent"] + extra_steps * rule["step_sell_percent"]

    def _event(self, current_date, event_type, nav, amount, shares, cash_after, total_shares, cost_basis, level):
        position_market_value = total_shares * nav
        return {
            "date": current_date,
            "type": event_type,
            "nav": nav,
            "amount": amount,
            "shares": shares,
            "cash_after": cash_after,
            "position_market_value": position_market_value,
            "position_return_rate": _return_rate(position_market_value, cost_basis),
            "level": str(level) if level is not None else None,
        }

    def _rolling_peaks(self, history, current_date, nav):
        history_until_date = [item for item in history if item["date"] <= current_date]
        recent = history_until_date[-self.window :]
        previous_peak = max(item["nav"] for item in recent[:-1]) if len(recent) > 1 else nav
        peak_nav = max(item["nav"] for item in recent) if recent else nav
        return peak_nav, previous_peak

    def _drawdown_levels(self):
        levels = self.asset.get("drawdown_levels") or [
            {"level": item["drawdown_percent"], "cash_ratio": item["cash_ratio"]}
            for item in self.config.get("replenishment_levels", [])
        ]
        return [
            (str(item["level"]), item["cash_ratio"])
            for item in sorted(levels, key=lambda item: item["level"])
        ]

    def _find_nasdaq_asset(self):
        for asset in self.portfolio_config.get("assets", []):
            if asset.get("asset_id") == "NASDAQ100":
                return asset
        return {
            "asset_id": "NASDAQ100",
            "asset_name": "纳斯达克100",
            "representative_fund": "270042",
            "strategy": "drawdown_plus_dca",
            "weekly_dca_amount": 50,
        }

    def _round_up(self, amount):
        return int(ceil(amount / self.round_to) * self.round_to)

    def _empty_report(self):
        return {
            "fund_code": self.fund_code,
            "asset_id": "NASDAQ100",
            "start_date": None,
            "end_date": None,
            "total_dca_invested": 0,
            "total_buy_amount": 0,
            "total_sell_amount": 0,
            "final_market_value": 0,
            "final_cash": self.bullet_cash_initial,
            "total_asset_value": self.bullet_cash_initial,
            "total_profit": 0,
            "total_return_rate": 0,
            "buy_events": [],
            "sell_events": [],
            "events": [],
            "series": [],
            "trigger_count_buy": 0,
            "trigger_count_sell": 0,
        }


def summarize_take_profit_report(report):
    lines = ["保守阶梯止盈回测摘要"]
    if not report:
        lines.append("暂无止盈回测结果。")
        return "\n".join(lines)
    lines.append(f"回测区间：{report.get('start_date')} 至 {report.get('end_date')}")
    lines.append(f"总定投投入：{report.get('total_dca_invested', 0):.2f} 元")
    lines.append(f"补仓投入：{report.get('total_buy_amount', 0):.2f} 元")
    lines.append(f"止盈卖出金额：{report.get('total_sell_amount', 0):.2f} 元")
    lines.append(f"剩余现金：{report.get('final_cash', 0):.2f} 元")
    lines.append(f"剩余持仓市值：{report.get('final_market_value', 0):.2f} 元")
    lines.append(f"总资产：{report.get('total_asset_value', 0):.2f} 元")
    lines.append(f"总收益率：{report.get('total_return_rate', 0) * 100:.2f}%")
    lines.append(f"补仓次数：{report.get('trigger_count_buy', 0)}")
    lines.append(f"止盈次数：{report.get('trigger_count_sell', 0)}")
    lines.append("说明：止盈回测为基于历史净值、定投、补仓和卖出事件的策略模拟，不代表真实账户收益。")
    return "\n".join(lines)


def _next_weekday(value, weekday):
    days_until_weekday = (weekday - value.weekday()) % 7
    return value + timedelta(days=days_until_weekday)


def _return_rate(position_market_value, cost_basis):
    return position_market_value / cost_basis - 1 if cost_basis > 0 else 0


def _normalize_take_profit_rules(rules):
    normalized = []
    sorted_rules = sorted(rules, key=lambda item: item["level"])
    for index, rule in enumerate(sorted_rules):
        next_level = sorted_rules[index + 1]["level"] if index + 1 < len(sorted_rules) else None
        normalized.append(
            {
                "level": int(rule["level"]),
                "base_sell_percent": int(rule["base_sell_percent"]),
                "step_sell_percent": int(rule.get("step_sell_percent", 0)),
                "next_level": next_level,
            }
        )
    return normalized
