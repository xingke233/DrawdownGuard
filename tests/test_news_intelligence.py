import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from drawdownguard.committee_report import build_committee_report
from drawdownguard.news_intelligence import (
    add_news_source,
    analyze_news,
    ensure_news_sources,
    fetch_news_from_sources,
    import_news,
)
from drawdownguard.storage import Storage


class NewsIntelligenceTest(unittest.TestCase):
    def test_news_sources_auto_created(self):
        with TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir))

            sources, infos = ensure_news_sources(storage)

            self.assertEqual(sources, {"sources": []})
            self.assertTrue((Path(temp_dir) / "data" / "news_sources.json").exists())
            self.assertTrue(infos)

    def test_news_source_add(self):
        sources = add_news_source({"sources": []}, "mock", "rss", "https://example.com/rss", category="market")

        self.assertEqual(sources["sources"][0]["name"], "mock")
        self.assertTrue(sources["sources"][0]["enabled"])

    def test_news_fetch_parses_mock_rss(self):
        with TemporaryDirectory() as temp_dir:
            rss = Path(temp_dir) / "rss.xml"
            rss.write_text(_rss("美联储释放降息信号，科技股走强", "纳斯达克科技股上涨。"), encoding="utf-8")
            sources = {"sources": [{"name": "mock", "type": "rss", "url": rss.as_uri(), "enabled": True, "category": "market"}]}

            cache = fetch_news_from_sources(sources, {"items": []})

            self.assertEqual(cache["fetch_status"]["new_count"], 1)
            self.assertEqual(cache["items"][0]["title"], "美联储释放降息信号，科技股走强")

    def test_news_import_writes_cache(self):
        cache, item = import_news({"items": []}, "黄金因地缘冲突上涨", content="避险需求升温", source="manual")

        self.assertEqual(cache["items"][0]["news_id"], item["news_id"])
        self.assertEqual(cache["items"][0]["source"], "manual")

    def test_news_analyze_recognizes_nasdaq(self):
        cache, _ = import_news({"items": []}, "美联储释放降息信号，科技股走强", content="市场预期美联储可能降息，纳斯达克科技股上涨。")

        report = analyze_news(cache, _config(), {"funds": []})
        item = report["items"][0]

        self.assertIn("NASDAQ100", item["matched_assets"])
        self.assertEqual(item["news_category"], "monetary_policy")
        self.assertGreaterEqual(item["news_importance_score"], 50)

    def test_news_analyze_recognizes_gold(self):
        cache, _ = import_news({"items": []}, "地缘冲突升级推动黄金上涨", content="避险需求升温，金价上涨。")

        report = analyze_news(cache, _config(), {"funds": []})
        item = report["items"][0]

        self.assertIn("GOLD", item["matched_assets"])
        self.assertEqual(item["news_category"], "geopolitics")

    def test_news_analyze_recognizes_hstech_regulation(self):
        cache, _ = import_news({"items": []}, "平台经济监管收紧", content="互联网监管影响阿里腾讯等港股科技。")

        report = analyze_news(cache, _config(), {"funds": []})
        item = report["items"][0]

        self.assertIn("HSTECH", item["matched_assets"])
        self.assertEqual(item["news_category"], "regulation")
        self.assertLess(item["impact_score"], 0)

    def test_score_ranges(self):
        cache, _ = import_news({"items": []}, "AI 算力需求增长", content="英伟达、半导体、CPO 受关注。")

        report = analyze_news(cache, _config(), {"funds": [{"fund_name": "CPO基金", "reason": "关注CPO"}]})
        item = report["items"][0]

        self.assertGreaterEqual(item["impact_score"], -3)
        self.assertLessEqual(item["impact_score"], 3)
        self.assertGreaterEqual(item["news_importance_score"], 0)
        self.assertLessEqual(item["news_importance_score"], 100)

    def test_no_news_does_not_crash(self):
        report = analyze_news({"items": []}, _config(), {"funds": []})

        self.assertEqual(report["portfolio_news_summary"]["relevant_news_count"], 0)
        self.assertEqual(report["items"], [])

    def test_fetch_failure_is_warning_not_exception(self):
        sources = {"sources": [{"name": "bad", "type": "rss", "url": "http://127.0.0.1:1/rss", "enabled": True, "category": "market"}]}

        cache = fetch_news_from_sources(sources, {"items": []}, timeout=1)

        self.assertIn("bad", cache["fetch_status"]["failed_sources"])
        self.assertTrue(cache["fetch_status"]["warnings"])

    def test_committee_report_shows_news(self):
        cache, _ = import_news({"items": []}, "美联储释放降息信号，科技股走强", content="纳斯达克科技股上涨。")
        news_report = analyze_news(cache, _config(), {"funds": []})

        report = build_committee_report(_config(), news_report=news_report)

        self.assertIn("每日新闻分析", report["markdown"])
        self.assertIn("美联储释放降息信号", report["markdown"])

    def test_news_does_not_modify_real_configs(self):
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            storage = Storage(base)
            (base / "data").mkdir(parents=True, exist_ok=True)
            for name, payload in {
                "current_holdings.json": {"holdings": []},
                "dca_plan.json": {"plans": []},
                "policy_config.json": {"drawdown_buy_policy": {}},
            }.items():
                (base / "data" / name).write_text(json.dumps(payload), encoding="utf-8")

            cache, _ = import_news(storage.load_news_cache(), "AI 算力需求增长", content="英伟达上涨。")
            storage.save_news_cache(cache)

            for name, payload in {
                "current_holdings.json": {"holdings": []},
                "dca_plan.json": {"plans": []},
                "policy_config.json": {"drawdown_buy_policy": {}},
            }.items():
                self.assertEqual(json.loads((base / "data" / name).read_text(encoding="utf-8")), payload)


def _rss(title, description):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Mock</title>
    <item>
      <title>{title}</title>
      <description>{description}</description>
      <link>https://example.com/news/1</link>
      <pubDate>Thu, 18 Jun 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def _config():
    return {
        "bullet_account": {"name": "余额宝", "balance": 1883},
        "holdings": [
            {"asset_id": "NASDAQ100", "asset_name": "纳斯达克100", "funds": [{"code": "270042"}]},
            {"asset_id": "HSTECH", "asset_name": "恒生科技", "funds": [{"code": "012349"}]},
            {"asset_id": "GOLD", "asset_name": "黄金", "funds": [{"code": "000216"}]},
            {"asset_id": "BONDS", "asset_name": "债券", "funds": [{"code": "110017"}]},
        ],
        "drawdown_buy_policy": {"allowed_fund_codes": ["270042", "012752", "012349"]},
        "dca_plan": {"plans": []},
    }


if __name__ == "__main__":
    unittest.main()
