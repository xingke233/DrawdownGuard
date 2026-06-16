import json

from .real_config import apply_real_profile, load_real_profile_files


class Storage:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.data_dir = self.base_dir / "data"

    def load_config(self, filename="config.yaml"):
        path = self.base_dir / filename
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
        config = apply_real_profile(config, load_real_profile_files(self))
        bullet_balance = int(config["bullet_account"]["balance"])
        for fund in config["funds"]:
            fund["bullet_balance"] = bullet_balance
        return config

    def save_config(self, config, filename="config.yaml"):
        if config.get("real_config_version"):
            profile = self._load_json("user_profile.json", {})
            if profile.get("bullet_cash") is not None:
                profile["bullet_cash"]["amount"] = int(config.get("bullet_account", {}).get("balance", 0))
                self._save_json("user_profile.json", profile)
            return
        path = self.base_dir / filename
        clean_config = dict(config)
        clean_funds = []
        for fund in clean_config["funds"]:
            item = dict(fund)
            item.pop("bullet_balance", None)
            clean_funds.append(item)
        clean_config["funds"] = clean_funds
        with path.open("w", encoding="utf-8") as file:
            json.dump(clean_config, file, ensure_ascii=False, indent=2)
            file.write("\n")

    def load_records(self):
        records = self._load_json("records.json", {})
        return self._migrate_historical_records(records)

    def save_records(self, records):
        self._save_json("records.json", records)

    def load_transactions(self):
        return self._load_json("transactions.json", [])

    def save_transactions(self, transactions):
        self._save_json("transactions.json", transactions)

    def load_daily_logs(self):
        return self._load_json("daily_log.json", [])

    def save_daily_logs(self, logs):
        self._save_json("daily_log.json", logs)

    def upsert_daily_logs(self, entries):
        logs = self.load_daily_logs()
        index = {(item.get("date"), item.get("fund_code")): item for item in logs}

        for entry in entries:
            key = (entry["date"], entry["fund_code"])
            index[key] = entry

        ordered = sorted(index.values(), key=lambda item: (item["date"], item["fund_code"]))
        self.save_daily_logs(ordered)
        return ordered

    def save_backtest_report(self, report):
        self._save_json("backtest_report.json", report)

    def load_backtest_report(self):
        return self._load_json("backtest_report.json", {})

    def save_asset_backtest_report(self, report):
        self._save_json("asset_backtest_report.json", report)

    def load_asset_backtest_report(self):
        return self._load_json("asset_backtest_report.json", {})

    def save_portfolio_backtest_report(self, report):
        self._save_json("portfolio_backtest_report.json", report)

    def load_portfolio_backtest_report(self):
        return self._load_json("portfolio_backtest_report.json", {})

    def save_contribution_report(self, report):
        self._save_json("contribution_report.json", report)

    def load_contribution_report(self):
        return self._load_json("contribution_report.json", {})

    def save_fund_check_report(self, report):
        self._save_json("fund_check_report.json", report)

    def load_fund_check_report(self):
        return self._load_json("fund_check_report.json", {})

    def save_asset_dca_audit_report(self, asset_id, report):
        self._save_json(f"asset_dca_audit_{asset_id}.json", report)

    def load_asset_dca_audit_report(self, asset_id):
        return self._load_json(f"asset_dca_audit_{asset_id}.json", {})

    def save_weekly_dca_analysis(self, report):
        self._save_json("weekly_dca_analysis.json", report)

    def load_weekly_dca_analysis(self):
        return self._load_json("weekly_dca_analysis.json", {})

    def save_dca_strategy_report(self, report):
        self._save_json("dca_strategy_report.json", report)

    def load_dca_strategy_report(self):
        return self._load_json("dca_strategy_report.json", {})

    def save_portfolio_strategy_report(self, report):
        self._save_json("portfolio_strategy_report.json", report)

    def load_portfolio_strategy_report(self):
        return self._load_json("portfolio_strategy_report.json", {})

    def save_portfolio_optimize_report(self, report):
        self._save_json("portfolio_optimize_report.json", report)

    def load_portfolio_optimize_report(self):
        return self._load_json("portfolio_optimize_report.json", {})

    def save_portfolio_optimize_continuous_report(self, report):
        self._save_json("portfolio_optimize_continuous_report.json", report)

    def load_portfolio_optimize_continuous_report(self):
        return self._load_json("portfolio_optimize_continuous_report.json", {})

    def save_strategy_lab_report(self, report):
        self._save_json("strategy_lab_report.json", report)

    def load_strategy_lab_report(self):
        return self._load_json("strategy_lab_report.json", {})

    def save_take_profit_report(self, report):
        self._save_json("take_profit_report.json", report)

    def load_take_profit_report(self):
        return self._load_json("take_profit_report.json", {})

    def save_risk_compare_report(self, report):
        self._save_json("risk_compare_report.json", report)

    def load_risk_compare_report(self):
        return self._load_json("risk_compare_report.json", {})

    def save_take_profit_optimizer_report(self, report):
        self._save_json("take_profit_optimizer_report.json", report)

    def load_take_profit_optimizer_report(self):
        return self._load_json("take_profit_optimizer_report.json", {})

    def save_scenarios_report(self, report):
        self._save_json("scenarios_report.json", report)

    def load_scenarios_report(self):
        return self._load_json("scenarios_report.json", {})

    def find_fund(self, config, query):
        return next(
            (
                fund
                for fund in config["funds"]
                if fund["code"] == query or fund["name"] == query or query in fund["name"]
            ),
            None,
        )

    def _load_json(self, filename, default):
        path = self.data_dir / filename
        legacy_path = self.base_dir / filename
        if not path.exists() and legacy_path.exists():
            path = legacy_path
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _save_json(self, filename, data):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.data_dir / filename
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")

    def _migrate_historical_records(self, records):
        for record in records.values():
            historical_levels = record.get("historical_levels", {})
            triggered_levels = record.setdefault("triggered_levels", {})
            pending_levels = record.setdefault("pending_levels", {})
            for level, is_historical in historical_levels.items():
                if not is_historical:
                    continue
                triggered_levels[level] = False
                pending_levels[level] = False
        return records
