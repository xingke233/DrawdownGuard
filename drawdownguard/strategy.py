from math import ceil


class DrawdownStrategy:
    def __init__(self, config):
        self.window = int(config.get("peak_window_trading_days", 250))
        self.activation_date = config.get("strategy_activation_date")
        self.levels = {
            str(item["drawdown_percent"]): item
            for item in sorted(config["replenishment_levels"], key=lambda x: x["drawdown_percent"])
        }
        self.round_to = int(config.get("round_amount_to", 10))

    def evaluate_fund(self, fund, nav_history, records):
        if not nav_history:
            raise ValueError(f"{fund['code']} 缺少净值数据")

        history = sorted(nav_history, key=lambda item: item["date"])
        recent = history[-self.window :]
        current = recent[-1]
        previous_peak = max(item["nav"] for item in recent[:-1]) if len(recent) > 1 else current["nav"]
        peak_nav = max(item["nav"] for item in recent)
        current_nav = current["nav"]

        fund_record = records.setdefault(fund["code"], self._empty_record())
        self._ensure_record_shape(fund_record)
        if current_nav > previous_peak:
            fund_record["triggered_levels"] = self._empty_levels(False)
            fund_record["pending_levels"] = self._empty_levels(False)
            fund_record["executed_levels"] = self._empty_levels(False)
            fund_record["historical_levels"] = self._empty_levels(False)
            fund_record["activation_baseline_cleared"] = True
            fund_record["last_reset_date"] = current["date"]

        drawdown = (current_nav - peak_nav) / peak_nav if peak_nav else 0
        drawdown_percent = abs(drawdown * 100)
        historical_drawdown = None
        if not fund_record.get("activation_baseline_cleared", False):
            historical_drawdown = self._apply_activation_baseline(recent, fund_record)
            self._migrate_historical_levels(fund_record)
        triggered_now = []

        for level_key, level in self.levels.items():
            threshold = int(level_key)
            if (
                drawdown_percent >= threshold
                and not fund_record["historical_levels"].get(level_key, False)
                and not fund_record["triggered_levels"].get(level_key, False)
            ):
                fund_record["triggered_levels"][level_key] = True
                fund_record["pending_levels"][level_key] = True
                triggered_now.append(level_key)

        suggested_amounts = self._calculate_suggested_amounts(fund_record, fund["bullet_balance"])

        status = self._status(drawdown_percent, fund_record)
        advice = self._advice(status)

        fund_record["last_checked_date"] = current["date"]
        fund_record["last_nav"] = current_nav
        fund_record["last_drawdown"] = drawdown

        return {
            "fund_code": fund["code"],
            "fund_name": fund["name"],
            "current_date": current["date"],
            "current_nav": current_nav,
            "peak_nav": peak_nav,
            "drawdown": drawdown,
            "status": status,
            "advice": advice,
            "historical_drawdown": historical_drawdown if historical_drawdown is not None else drawdown,
            "historical_levels": dict(fund_record["historical_levels"]),
            "triggered_now": triggered_now,
            "triggered_levels": dict(fund_record["triggered_levels"]),
            "pending_levels": dict(fund_record["pending_levels"]),
            "executed_levels": dict(fund_record["executed_levels"]),
            "suggested_amounts": suggested_amounts,
        }

    def _status(self, drawdown_percent, record):
        active_historical = [
            int(level)
            for level, historical in record["historical_levels"].items()
            if historical and drawdown_percent >= int(level)
        ]
        active = [
            int(level)
            for level, triggered in record["triggered_levels"].items()
            if (
                triggered
                and not record["historical_levels"].get(level, False)
                and drawdown_percent >= int(level)
            )
        ]
        if active:
            level = max(active)
            if record["executed_levels"].get(str(level), False):
                return f"第{self._level_name(level)}档已执行"
            return f"第{self._level_name(level)}档已触发"
        if active_historical:
            if max(active_historical) >= max(int(level) for level in self.levels):
                return "深度回撤中"
            return "历史回撤"
        return "观察中"

    def _advice(self, status):
        if status == "深度回撤中":
            return "不追补历史档位，继续观察"
        if status == "历史回撤":
            return "不追补历史档位。"
        return None

    def _apply_activation_baseline(self, history, record):
        if not self.activation_date:
            return None

        activation_history = [item for item in history if item["date"] <= self.activation_date]
        if not activation_history:
            return None

        activation_peak = max(item["nav"] for item in activation_history)
        activation_current = activation_history[-1]["nav"]
        activation_drawdown = (
            (activation_current - activation_peak) / activation_peak if activation_peak else 0
        )
        activation_drawdown_percent = abs(activation_drawdown * 100)

        for level_key in self.levels:
            if activation_drawdown_percent >= int(level_key):
                record["historical_levels"][level_key] = True

        return activation_drawdown

    def _migrate_historical_levels(self, record):
        for level_key, is_historical in record["historical_levels"].items():
            if not is_historical:
                continue
            record["triggered_levels"][level_key] = False
            record["pending_levels"][level_key] = False

    def _round_up(self, amount):
        return int(ceil(amount / self.round_to) * self.round_to)

    def _calculate_suggested_amounts(self, record, initial_cash):
        suggested_amounts = {}
        remaining_cash = initial_cash

        for level_key, level in self.levels.items():
            if not record["pending_levels"].get(level_key, False):
                continue
            amount = min(self._round_up(remaining_cash * level["cash_ratio"]), remaining_cash)
            suggested_amounts[level_key] = amount
            remaining_cash -= amount

        return suggested_amounts

    def _empty_record(self):
        return {
            "triggered_levels": self._empty_levels(False),
            "pending_levels": self._empty_levels(False),
            "executed_levels": self._empty_levels(False),
            "historical_levels": self._empty_levels(False),
            "activation_baseline_cleared": False,
            "last_reset_date": None,
            "last_checked_date": None,
            "last_nav": None,
            "last_drawdown": None,
        }

    def _ensure_record_shape(self, record):
        record.setdefault("triggered_levels", self._empty_levels(False))
        record.setdefault("pending_levels", self._empty_levels(False))
        record.setdefault("executed_levels", self._empty_levels(False))
        record.setdefault("historical_levels", self._empty_levels(False))
        record.setdefault("activation_baseline_cleared", False)
        for key in ("triggered_levels", "pending_levels", "executed_levels", "historical_levels"):
            for level in self.levels:
                record[key].setdefault(level, False)

    def _empty_levels(self, value):
        return {level: value for level in self.levels}

    @staticmethod
    def _level_name(level):
        return {10: "一", 15: "二", 20: "三"}.get(level, str(level))
