import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from drawdownguard.data_provider import NavDataProvider
from drawdownguard.nav_cache import NavCache, cache_key
from main import _format_cache_status, clear_cache_command, show_cache_status


class NavCacheTest(unittest.TestCase):
    def test_real_success_writes_cache(self):
        with TemporaryDirectory() as temp_dir:
            provider = NavDataProvider(Path(temp_dir) / "nav_data.json", _config(), akshare_client=SuccessfulAkShare())

            result = provider.get_history("270042")

            self.assertEqual(result["source"], "real")
            cache_file = Path(temp_dir) / "data" / "nav_cache.json"
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            self.assertIn("270042:unit_nav", data)
            self.assertGreaterEqual(len(data["270042:unit_nav"]["history"]), 300)

    def test_real_failure_falls_back_to_cache(self):
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            cache = NavCache(base, _config())
            cache.save_history("270042", "广发纳指", "unit_nav", _history(300), source="real")
            provider = NavDataProvider(base / "nav_data.json", _config(), akshare_client=FailingAkShare())

            result = provider.get_history("270042")

            self.assertEqual(result["source"], "cache")
            self.assertTrue(result["cache_used"])
            self.assertEqual(len(result["history"]), 250)

    def test_stale_cache_adds_warning(self):
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            _write_cache(base, "270042", "unit_nav", _history(300), days_old=30)
            provider = NavDataProvider(base / "nav_data.json", _config(), akshare_client=FailingAkShare())

            result = provider.get_history("270042")

            self.assertEqual(result["source"], "cache")
            self.assertTrue(result["cache_stale"])
            self.assertTrue(any("缓存净值已过期" in warning for warning in result["warnings"]))

    def test_short_cache_adds_warning(self):
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            _write_cache(base, "270042", "unit_nav", _history(10), days_old=1)
            provider = NavDataProvider(base / "nav_data.json", _config(), akshare_client=FailingAkShare())

            result = provider.get_history("270042")

            self.assertEqual(result["source"], "cache")
            self.assertTrue(any("缓存净值不足 250 条" in warning for warning in result["warnings"]))

    def test_unit_and_accumulated_nav_cache_are_separate(self):
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            cache = NavCache(base, _config())
            cache.save_history("008163", "红利低波", "unit_nav", [{"date": "2026-01-01", "nav": 1.0}], source="real")
            cache.save_history("008163", "红利低波", "accumulated_nav", [{"date": "2026-01-01", "nav": 2.0}], source="real")

            self.assertIn(cache_key("008163", "unit_nav"), cache.data)
            self.assertIn(cache_key("008163", "accumulated_nav"), cache.data)
            unit, _, _ = cache.get_history("008163", "unit_nav")
            accumulated, _, _ = cache.get_history("008163", "accumulated_nav")
            self.assertEqual(unit[-1]["nav"], 1.0)
            self.assertEqual(accumulated[-1]["nav"], 2.0)

    def test_cache_status_output(self):
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            cache = NavCache(base, _config())
            cache.save_history("270042", "广发纳指", "unit_nav", _history(300), source="real")

            text = _format_cache_status(cache.status_report())

            self.assertIn("缓存基金数量：1", text)
            self.assertIn("270042", text)
            self.assertIn("unit_nav", text)

    def test_cache_clear_yes(self):
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            cache = NavCache(base, _config())
            cache.save_history("270042", "广发纳指", "unit_nav", _history(300), source="real")

            cache.clear()

            self.assertEqual(cache.status_report()["fund_count"], 0)

    def test_corrupt_cache_does_not_crash(self):
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            cache_file = base / "data" / "nav_cache.json"
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text("{bad json", encoding="utf-8")

            provider = NavDataProvider(base / "nav_data.json", _config(), akshare_client=FailingAkShare())
            result = provider.get_history("270042")

            self.assertTrue(any("缓存文件损坏" in warning for warning in result["warnings"]))


class SuccessfulAkShare:
    def fund_open_fund_info_em(self, symbol, indicator):
        return FakeDataFrame(
            [
                {"净值日期": row["date"], "单位净值": row["nav"], "累计净值": row["nav"] + 1}
                for row in _history(320)
            ]
        )


class FailingAkShare:
    def fund_open_fund_info_em(self, symbol, indicator):
        raise RuntimeError("network unavailable")


class FakeDataFrame:
    def __init__(self, records):
        self.records = records

    def to_dict(self, orient):
        return self.records


def _config():
    return {
        "data_source": "real",
        "peak_window_trading_days": 250,
        "nav_cache": {
            "enabled": True,
            "max_age_days_for_run": 7,
            "max_age_days_for_backtest": 90,
            "min_history_for_run": 250,
        },
        "funds": [{"code": "270042", "name": "广发纳指"}],
    }


def _history(count):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        {"date": (start + timedelta(days=index)).date().isoformat(), "nav": 1 + index / 1000}
        for index in range(count)
    ]


def _write_cache(base, fund_code, nav_mode, history, days_old):
    cache_file = base / "data" / "nav_cache.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    last_updated = (datetime.now(timezone.utc) - timedelta(days=days_old)).replace(microsecond=0).isoformat()
    cache_file.write_text(
        json.dumps(
            {
                f"{fund_code}:{nav_mode}": {
                    "fund_code": fund_code,
                    "fund_name": fund_code,
                    "nav_mode": nav_mode,
                    "last_updated": last_updated,
                    "source": "real",
                    "history": history,
                }
            }
        ),
        encoding="utf-8",
    )

