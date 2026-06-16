import json


class NavDataProvider:
    def __init__(self, nav_file, config, akshare_client=None):
        self.nav_file = nav_file
        self.config = config
        self.akshare_client = akshare_client
        self.window = int(config.get("peak_window_trading_days", 250))
        self.local_warnings = []
        self.local_data = self._load_local_data()

    def get_history(self, fund_code, nav_mode="unit_nav"):
        return self._get_history(fund_code, limit=True, nav_mode=nav_mode)

    def get_full_history(self, fund_code, nav_mode="unit_nav"):
        return self._get_history(fund_code, limit=False, nav_mode=nav_mode)

    def _get_history(self, fund_code, limit, nav_mode="unit_nav"):
        data_source = self.config.get("data_source", "real")
        warnings = []

        if data_source == "real":
            try:
                history = self._get_real_history(fund_code, nav_mode=nav_mode)
                limited = self._limit_history(history) if limit else history
                return self._result(limited, "real", warnings, nav_mode)
            except Exception as exc:
                if nav_mode == "accumulated_nav":
                    warnings.append(f"累计净值获取失败，已回退到单位净值：{exc}")
                    try:
                        history = self._get_real_history(fund_code, nav_mode="unit_nav")
                        limited = self._limit_history(history) if limit else history
                        return self._result(limited, "real", warnings, "unit_nav")
                    except Exception as unit_exc:
                        warnings.append(f"单位净值获取失败，已切换到本地数据：{unit_exc}")
                else:
                    warnings.append(f"真实净值获取失败，已切换到本地数据：{exc}")
                history, local_warnings = self._get_local_history(fund_code, nav_mode=nav_mode)
                warnings.extend(local_warnings)
                limited = self._limit_history(history) if limit else history
                return self._result(limited, "local", warnings, nav_mode)

        if data_source == "local":
            history, local_warnings = self._get_local_history(fund_code, nav_mode=nav_mode)
            warnings.extend(local_warnings)
            limited = self._limit_history(history) if limit else history
            return self._result(limited, "local", warnings, nav_mode)

        raise ValueError(f"不支持的数据源：{data_source}")

    def _get_real_history(self, fund_code, nav_mode="unit_nav"):
        akshare = self.akshare_client
        if akshare is None:
            import akshare

        if nav_mode == "accumulated_nav":
            data_frame = akshare.fund_open_fund_info_em(symbol=fund_code, indicator="累计净值走势")
            return self._normalize_akshare_rows(data_frame, ["累计净值", "accumulated_nav", "nav"])
        if nav_mode != "unit_nav":
            raise ValueError(f"不支持的净值口径：{nav_mode}")
        data_frame = akshare.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
        return self._normalize_akshare_rows(data_frame, ["单位净值", "nav"])

    def _get_local_history(self, fund_code, nav_mode="unit_nav"):
        warnings = list(self.local_warnings)
        history = self.local_data.get(f"{fund_code}:{nav_mode}") or self.local_data.get(fund_code, [])
        if nav_mode == "accumulated_nav" and f"{fund_code}:{nav_mode}" not in self.local_data:
            warnings.append("本地累计净值数据缺失，已尝试使用本地单位净值数据。")
        if not history:
            warnings.append("本地净值数据缺失。")
        return history, warnings

    def _load_local_data(self):
        if not self.nav_file.exists():
            self.local_warnings.append(f"本地净值文件不存在：{self.nav_file}")
            return {}
        try:
            with self.nav_file.open("r", encoding="utf-8") as file:
                data = json.load(file)
            return {
                code: self._normalize_rows(values)
                for code, values in data.items()
                if isinstance(values, list)
            }
        except Exception as exc:
            self.local_warnings.append(f"本地净值文件读取失败：{exc}")
            return {}

    def _normalize_akshare_rows(self, data_frame, nav_keys):
        rows = []
        records = data_frame.to_dict("records")
        for item in records:
            date_value = self._first_present(item, ["净值日期", "日期", "date"])
            nav_value = self._first_present(item, nav_keys)
            if date_value is None or nav_value is None:
                continue
            rows.append({"date": str(date_value)[:10], "nav": float(nav_value)})
        return self._normalize_rows(rows)

    def _normalize_rows(self, rows):
        normalized = []
        for item in rows:
            if "date" not in item or "nav" not in item:
                continue
            normalized.append({"date": str(item["date"])[:10], "nav": float(item["nav"])})
        return sorted(normalized, key=lambda item: item["date"])

    def _limit_history(self, history):
        return history[-self.window :]

    def _result(self, history, source, warnings, nav_mode="unit_nav"):
        if not history:
            warnings = [*warnings, "净值数据缺失，已跳过。"]
        elif len(history) < self.window:
            warnings = [
                *warnings,
                f"净值数据不足{self.window}条，当前仅{len(history)}条，仍按现有数据计算。",
            ]
        return {"history": history, "source": source, "warnings": warnings, "nav_mode": nav_mode}

    @staticmethod
    def _first_present(item, keys):
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return value
        return None


LocalNavProvider = NavDataProvider
