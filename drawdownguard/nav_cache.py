import json
from datetime import datetime, timezone


DEFAULT_NAV_CACHE_CONFIG = {
    "enabled": True,
    "max_age_days_for_run": 7,
    "max_age_days_for_backtest": 90,
    "min_history_for_run": 250,
}


class NavCache:
    def __init__(self, base_dir, config=None):
        self.base_dir = base_dir
        self.path = self.base_dir / "data" / "nav_cache.json"
        self.config = {**DEFAULT_NAV_CACHE_CONFIG, **((config or {}).get("nav_cache") or {})}
        self.warnings = []
        self.data = self._load()

    def enabled(self):
        return bool(self.config.get("enabled", True))

    def save_history(self, fund_code, fund_name, nav_mode, history, source="real", min_keep=300):
        if not self.enabled() or not history:
            return
        key = cache_key(fund_code, nav_mode)
        self.data[key] = {
            "fund_code": fund_code,
            "fund_name": fund_name or fund_code,
            "nav_mode": nav_mode,
            "last_updated": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "source": source,
            "history": list(history)[-min_keep:] if min_keep else list(history),
        }
        self._save()

    def get_history(self, fund_code, nav_mode, for_backtest=False):
        if not self.enabled():
            return [], ["本地净值缓存未启用。"], {}
        base_warnings = list(self.warnings)
        item = self.data.get(cache_key(fund_code, nav_mode))
        if not item and nav_mode == "accumulated_nav":
            return [], [*base_warnings, "缓存累计净值数据缺失。"], {}
        if not item:
            return [], [*base_warnings, "缓存净值数据缺失。"], {}

        history = _normalize_rows(item.get("history", []))
        meta = {
            "cache_last_updated": item.get("last_updated"),
            "cache_status": cache_status(item.get("last_updated"), self.config, for_backtest),
            "cache_key": cache_key(fund_code, nav_mode),
        }
        warnings = base_warnings
        if meta["cache_status"] == "stale":
            warnings.append("缓存净值已过期，仅供参考。")
        if not for_backtest and len(history) < int(self.config.get("min_history_for_run", 250)):
            warnings.append("缓存净值不足 250 条，阶段高点可能不准确。")
        if not history:
            warnings.append("缓存净值数据缺失。")
        return history, warnings, meta

    def status_report(self):
        items = []
        for key, item in sorted(self.data.items()):
            history = _normalize_rows(item.get("history", []))
            nav_mode = item.get("nav_mode", "unit_nav")
            items.append(
                {
                    "cache_key": key,
                    "fund_code": item.get("fund_code"),
                    "fund_name": item.get("fund_name"),
                    "nav_mode": nav_mode,
                    "last_updated": item.get("last_updated"),
                    "history_count": len(history),
                    "latest_nav_date": history[-1]["date"] if history else None,
                    "cache_status_for_run": cache_status(item.get("last_updated"), self.config, False),
                    "cache_status_for_backtest": cache_status(item.get("last_updated"), self.config, True),
                    "meets_min_history_for_run": len(history) >= int(self.config.get("min_history_for_run", 250)),
                }
            )
        return {
            "exists": self.path.exists(),
            "path": str(self.path),
            "enabled": self.enabled(),
            "fund_count": len(items),
            "items": items,
            "warnings": list(self.warnings),
        }

    def clear(self):
        self.data = {}
        self._save()

    def _load(self):
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            self.warnings.append(f"缓存文件损坏，已重建：{exc}")
            self._save_data({})
            return {}

    def _save(self):
        self._save_data(self.data)

    def _save_data(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")


def cache_key(fund_code, nav_mode):
    return f"{fund_code}:{nav_mode}"


def cache_status(last_updated, config, for_backtest=False):
    age = cache_age_days(last_updated)
    if age is None:
        return "stale"
    max_age = int(
        config.get(
            "max_age_days_for_backtest" if for_backtest else "max_age_days_for_run",
            90 if for_backtest else 7,
        )
    )
    return "fresh" if age <= max_age else "stale"


def cache_age_days(last_updated):
    if not last_updated:
        return None
    try:
        value = datetime.fromisoformat(str(last_updated).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - value).days
    except Exception:
        return None


def _normalize_rows(rows):
    normalized = []
    for item in rows or []:
        if "date" not in item or "nav" not in item:
            continue
        normalized.append({"date": str(item["date"])[:10], "nav": float(item["nav"])})
    return sorted(normalized, key=lambda item: item["date"])
