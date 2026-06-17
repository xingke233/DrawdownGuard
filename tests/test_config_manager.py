import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from drawdownguard.config_manager import ConfigManager


class ConfigManagerTest(unittest.TestCase):
    def test_cash_update_changes_bullet_cash(self):
        with TemporaryDirectory() as temp_dir:
            base = _write_config(Path(temp_dir))
            manager = ConfigManager(base)

            manager.update_cash(2000)
            profile = _load(base, "user_profile.json")

        self.assertEqual(profile["bullet_cash"]["amount"], 2000)

    def test_holding_update_changes_fund_amount(self):
        with TemporaryDirectory() as temp_dir:
            base = _write_config(Path(temp_dir))
            manager = ConfigManager(base)

            manager.update_holding("270042", 2200)
            holdings = _load(base, "current_holdings.json")
            fund = holdings["holdings"][0]["funds"][0]

        self.assertEqual(fund["amount"], 2200)
        self.assertEqual(holdings["holdings"][0]["amount"], 2200)

    def test_dca_update_changes_amount(self):
        with TemporaryDirectory() as temp_dir:
            base = _write_config(Path(temp_dir))
            ConfigManager(base).update_dca("270042", 30)
            dca = _load(base, "dca_plan.json")

        self.assertEqual(dca["weekly"][0]["amount"], 30)

    def test_dca_pause_and_resume(self):
        with TemporaryDirectory() as temp_dir:
            base = _write_config(Path(temp_dir))
            manager = ConfigManager(base)

            manager.set_dca_status("270042", "paused")
            self.assertEqual(_load(base, "dca_plan.json")["weekly"][0]["status"], "paused")
            manager.set_dca_status("270042", "active")
            self.assertEqual(_load(base, "dca_plan.json")["weekly"][0]["status"], "active")

    def test_modification_creates_backup(self):
        with TemporaryDirectory() as temp_dir:
            base = _write_config(Path(temp_dir))
            result = ConfigManager(base).update_cash(2000)

            backup = Path(result["backup_path"])
            self.assertTrue(backup.exists())
            self.assertTrue((backup / "user_profile.json").exists())

    def test_rollback_latest_restores_previous_config(self):
        with TemporaryDirectory() as temp_dir:
            base = _write_config(Path(temp_dir))
            manager = ConfigManager(base)
            manager.update_cash(2000)
            manager.rollback_latest()
            profile = _load(base, "user_profile.json")

        self.assertEqual(profile["bullet_cash"]["amount"], 1883)

    def test_dry_run_does_not_write_files(self):
        with TemporaryDirectory() as temp_dir:
            base = _write_config(Path(temp_dir))
            result = ConfigManager(base).update_cash(2000, dry_run=True)
            profile = _load(base, "user_profile.json")

        self.assertTrue(result["dry_run"])
        self.assertEqual(profile["bullet_cash"]["amount"], 1883)

    def test_change_log_records_operation(self):
        with TemporaryDirectory() as temp_dir:
            base = _write_config(Path(temp_dir))
            manager = ConfigManager(base)
            result = manager.update_cash(2000)
            manager.log_change("cash-update", "cash", result["before"], result["after"], result["backup_path"], {"passed": True})
            logs = manager.recent_logs()

        self.assertEqual(logs[-1]["operation"], "cash-update")
        self.assertTrue(logs[-1]["policy_check_result"]["passed"])


def _write_config(base):
    data = base / "data"
    data.mkdir(parents=True, exist_ok=True)
    _save(base, "user_profile.json", {"bullet_cash": {"amount": 1883}})
    _save(
        base,
        "current_holdings.json",
        {
            "holdings": [
                {
                    "asset_id": "NASDAQ100",
                    "asset_name": "纳斯达克100",
                    "amount": 2038,
                    "weight": 1,
                    "role": "core_growth",
                    "funds": [{"code": "270042", "name": "广发纳指", "amount": 2038, "weight": 1}],
                }
            ]
        },
    )
    _save(base, "dca_plan.json", {"weekly": [{"asset_id": "NASDAQ100", "fund_code": "270042", "fund_name": "广发纳指", "amount": 10}], "monthly": []})
    _save(base, "policy_config.json", {"drawdown_buy_policy": {"allowed_fund_codes": [], "blocked_fund_codes": [], "levels": []}})
    _save(base, "watchlist_funds.json", {"funds": []})
    return base


def _save(base, filename, data):
    (base / "data" / filename).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _load(base, filename):
    return json.loads((base / "data" / filename).read_text(encoding="utf-8"))
