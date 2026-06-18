import json
import shutil
from datetime import datetime
from pathlib import Path


CONFIG_FILES = [
    "user_profile.json",
    "current_holdings.json",
    "dca_plan.json",
    "policy_config.json",
    "watchlist_funds.json",
]


class ConfigManager:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.backup_dir = self.data_dir / "backups"

    def update_cash(self, amount, dry_run=False):
        profile = self._load("user_profile.json", {})
        before = profile.get("bullet_cash", {}).get("amount")
        after_data = json.loads(json.dumps(profile))
        after_data.setdefault("bullet_cash", {})["amount"] = float(amount)
        return self._commit(
            "cash-update",
            "user_profile.json:bullet_cash.amount",
            {"amount": before},
            {"amount": float(amount)},
            {"user_profile.json": after_data},
            dry_run=dry_run,
        )

    def update_holding(self, fund_code, amount, dry_run=False):
        holdings = self._load("current_holdings.json", {"holdings": []})
        updated = json.loads(json.dumps(holdings))
        fund = self._find_fund(updated, fund_code)
        if not fund:
            raise ValueError(f"未找到持仓基金：{fund_code}")
        before = fund.get("amount")
        fund["amount"] = float(amount)
        self._refresh_asset_amounts_and_weights(updated)
        return self._commit(
            "holding-update",
            fund_code,
            {"amount": before},
            {"amount": float(amount)},
            {"current_holdings.json": updated},
            dry_run=dry_run,
        )

    def add_holding(self, fund_code, name, asset_id, role, amount, nav_mode="unit_nav", dry_run=False):
        holdings = self._load("current_holdings.json", {"holdings": []})
        updated = json.loads(json.dumps(holdings))
        if self._find_fund(updated, fund_code):
            raise ValueError(f"持仓中已存在基金：{fund_code}")
        asset = next((item for item in updated.get("holdings", []) if item.get("asset_id") == asset_id), None)
        fund = {
            "code": fund_code,
            "name": name,
            "amount": float(amount),
            "weight": 0,
            "role": role,
            "nav_mode": nav_mode,
        }
        if asset:
            asset.setdefault("funds", []).append(fund)
            asset["role"] = asset.get("role") or role
            asset["nav_mode"] = asset.get("nav_mode", nav_mode)
        else:
            updated.setdefault("holdings", []).append(
                {
                    "asset_id": asset_id,
                    "asset_name": asset_id,
                    "amount": float(amount),
                    "weight": 0,
                    "role": role,
                    "nav_mode": nav_mode,
                    "funds": [fund],
                }
            )
        self._refresh_asset_amounts_and_weights(updated)
        return self._commit(
            "holding-add",
            fund_code,
            None,
            {"fund_code": fund_code, "amount": float(amount), "asset_id": asset_id},
            {"current_holdings.json": updated},
            dry_run=dry_run,
        )

    def remove_holding(self, fund_code, dry_run=False):
        holdings = self._load("current_holdings.json", {"holdings": []})
        updated = json.loads(json.dumps(holdings))
        before = self._find_fund(updated, fund_code)
        if not before:
            raise ValueError(f"未找到持仓基金：{fund_code}")
        for asset in updated.get("holdings", []):
            for fund in asset.get("funds", []):
                if fund.get("code") == fund_code:
                    fund["status"] = "removed"
                    fund["archived"] = True
            active_funds = [fund for fund in asset.get("funds", []) if self._is_active(fund)]
            if asset.get("asset_id") != "CASH" and not active_funds:
                asset["status"] = "removed"
                asset["archived"] = True
        self._refresh_asset_amounts_and_weights(updated)
        return self._commit(
            "holding-remove",
            fund_code,
            {"status": before.get("status", "active"), "archived": before.get("archived", False), "amount": before.get("amount")},
            {"status": "removed", "archived": True},
            {"current_holdings.json": updated},
            dry_run=dry_run,
        )

    def add_dca(self, fund_code, amount, frequency, weekday=None, dry_run=False):
        dca = self._load("dca_plan.json", {"weekly": [], "monthly": []})
        updated = json.loads(json.dumps(dca))
        if self._find_dca(updated, fund_code):
            raise ValueError(f"定投计划已存在：{fund_code}")
        holding = self._holding_for_fund(fund_code)
        item = {
            "asset_id": holding.get("asset_id", "UNKNOWN"),
            "fund_code": fund_code,
            "fund_name": holding.get("fund_name", fund_code),
            "amount": float(amount),
            "status": "active",
        }
        if frequency == "weekly":
            if weekday:
                item["weekday"] = weekday
            updated.setdefault("weekly", []).append(item)
        elif frequency == "monthly":
            item["day"] = 1
            updated.setdefault("monthly", []).append(item)
        else:
            raise ValueError("frequency 仅支持 weekly 或 monthly")
        return self._commit(
            "dca-add",
            fund_code,
            None,
            item,
            {"dca_plan.json": updated},
            dry_run=dry_run,
        )

    def update_dca(self, fund_code, amount, dry_run=False):
        dca = self._load("dca_plan.json", {"weekly": [], "monthly": []})
        updated = json.loads(json.dumps(dca))
        item = self._find_dca(updated, fund_code)
        if not item:
            raise ValueError(f"未找到定投计划：{fund_code}")
        before = item.get("amount")
        item["amount"] = float(amount)
        return self._commit(
            "dca-update",
            fund_code,
            {"amount": before},
            {"amount": float(amount)},
            {"dca_plan.json": updated},
            dry_run=dry_run,
        )

    def set_dca_status(self, fund_code, status, dry_run=False):
        dca = self._load("dca_plan.json", {"weekly": [], "monthly": []})
        updated = json.loads(json.dumps(dca))
        item = self._find_dca(updated, fund_code)
        if not item:
            raise ValueError(f"未找到定投计划：{fund_code}")
        before = item.get("status", "active")
        item["status"] = status
        operation = "dca-pause" if status == "paused" else "dca-resume"
        return self._commit(
            operation,
            fund_code,
            {"status": before},
            {"status": status},
            {"dca_plan.json": updated},
            dry_run=dry_run,
        )

    def backup(self):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = self.backup_dir / timestamp
        path.mkdir(parents=True, exist_ok=True)
        for filename in CONFIG_FILES:
            source = self.data_dir / filename
            if source.exists():
                shutil.copy2(source, path / filename)
        return path

    def list_backups(self):
        if not self.backup_dir.exists():
            return []
        return sorted([path for path in self.backup_dir.iterdir() if path.is_dir()])

    def rollback_latest(self):
        backups = self.list_backups()
        if not backups:
            raise ValueError("没有可回滚的备份。")
        latest = backups[-1]
        for path in latest.iterdir():
            if path.name in CONFIG_FILES:
                shutil.copy2(path, self.data_dir / path.name)
        return latest

    def log_change(self, operation, target, before, after, backup_path, policy_check_result, dry_run=False):
        log = self._load("config_change_log.json", [])
        log.append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "operation": operation,
                "target": target,
                "before": before,
                "after": after,
                "backup_path": str(backup_path) if backup_path else None,
                "policy_check_result": policy_check_result,
                "dry_run": dry_run,
            }
        )
        self._save("config_change_log.json", log)

    def recent_logs(self, limit=20):
        return self._load("config_change_log.json", [])[-limit:]

    def _commit(self, operation, target, before, after, file_updates, dry_run=False):
        if dry_run:
            return {
                "operation": operation,
                "target": target,
                "before": before,
                "after": after,
                "backup_path": None,
                "dry_run": True,
                "file_updates": file_updates,
            }
        backup_path = self.backup()
        for filename, data in file_updates.items():
            self._save(filename, data)
        return {
            "operation": operation,
            "target": target,
            "before": before,
            "after": after,
            "backup_path": str(backup_path),
            "dry_run": False,
        }

    def _load(self, filename, default):
        path = self.data_dir / filename
        if not path.exists():
            return json.loads(json.dumps(default))
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _save(self, filename, data):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.data_dir / filename
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")

    def _find_fund(self, holdings, fund_code):
        for asset in holdings.get("holdings", []):
            for fund in asset.get("funds", []):
                if fund.get("code") == fund_code:
                    return fund
        return None

    def _find_dca(self, dca, fund_code):
        for section in ("weekly", "monthly"):
            for item in dca.get(section, []):
                if item.get("fund_code") == fund_code:
                    return item
        return None

    def _holding_for_fund(self, fund_code):
        holdings = self._load("current_holdings.json", {"holdings": []})
        for asset in holdings.get("holdings", []):
            for fund in asset.get("funds", []):
                if fund.get("code") == fund_code:
                    return {"asset_id": asset.get("asset_id"), "fund_name": fund.get("name", fund_code)}
        return {"asset_id": "UNKNOWN", "fund_name": fund_code}

    def _refresh_asset_amounts_and_weights(self, holdings):
        for asset in holdings.get("holdings", []):
            if asset.get("funds"):
                asset["amount"] = round(sum(float(fund.get("amount", 0)) for fund in asset.get("funds", []) if self._is_active(fund)), 2)
        total = sum(float(asset.get("amount", 0)) for asset in holdings.get("holdings", []) if self._is_active(asset))
        if total <= 0:
            return
        for asset in holdings.get("holdings", []):
            asset["weight"] = round(float(asset.get("amount", 0)) / total, 6) if self._is_active(asset) else 0
            for fund in asset.get("funds", []):
                fund["weight"] = round(float(fund.get("amount", 0)) / total, 6) if self._is_active(fund) else 0

    @staticmethod
    def _is_active(item):
        return item.get("status", "active") != "removed" and not item.get("archived", False)
