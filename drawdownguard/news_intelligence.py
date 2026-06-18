from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
import html
import re
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree


DEFAULT_NEWS_SOURCES = {"sources": []}
DEFAULT_NEWS_CACHE = {"items": [], "fetch_status": {}}

ASSET_KEYWORDS = {
    "NASDAQ100": ["纳斯达克", "美股", "科技股", "ai", "openai", "英伟达", "nvidia", "微软", "microsoft", "苹果", "apple", "半导体", "芯片", "算力", "利率", "美联储", "降息", "加息"],
    "HSTECH": ["恒生科技", "港股科技", "阿里", "腾讯", "美团", "快手", "京东", "中概", "平台经济", "互联网监管"],
    "CASHFLOW": ["自由现金流", "现金流", "质量因子", "roe", "盈利质量"],
    "DIVIDEND_LOW_VOL": ["红利", "低波", "高股息", "银行", "煤炭", "公用事业", "价值股", "防御资产"],
    "GOLD": ["黄金", "金价", "避险", "美元", "实际利率", "地缘冲突", "通胀"],
    "BONDS": ["债券", "债市", "国债", "利率", "央行", "货币政策", "信用风险", "收益率"],
    "ACTIVE_ADVANCED_MANUFACTURING": ["先进制造", "高端制造", "机器人", "工业母机", "半导体设备", "新能源"],
    "NONFERROUS_METALS": ["有色金属", "铜", "铝", "锂", "稀土", "白银", "商品周期"],
}

MAJOR_EVENT_WORDS = [
    "降息",
    "加息",
    "通胀",
    "美联储",
    "ai",
    "英伟达",
    "半导体",
    "cpo",
    "监管",
    "地缘冲突",
    "黄金",
    "债券",
    "信用风险",
    "大宗商品",
    "财报",
    "业绩",
    "政策支持",
    "估值过高",
    "泡沫",
    "暴跌",
    "大涨",
]


def ensure_news_sources(storage):
    path = storage.data_dir / "news_sources.json"
    if not path.exists():
        storage.save_news_sources(DEFAULT_NEWS_SOURCES)
        return DEFAULT_NEWS_SOURCES, ["news_sources.json 不存在，已自动创建默认空新闻源文件。"]
    return storage.load_news_sources(), []


def add_news_source(sources, name, source_type, url, category="market", enabled=True):
    items = list(sources.get("sources", []))
    if any(item.get("name") == name for item in items):
        raise ValueError(f"新闻源已存在：{name}")
    items.append(
        {
            "name": name,
            "type": source_type,
            "url": url,
            "enabled": bool(enabled),
            "category": category,
        }
    )
    return {"sources": items}


def set_news_source_enabled(sources, name, enabled):
    changed = False
    items = []
    for item in sources.get("sources", []):
        updated = dict(item)
        if updated.get("name") == name:
            updated["enabled"] = bool(enabled)
            changed = True
        items.append(updated)
    if not changed:
        raise ValueError(f"新闻源不存在：{name}")
    return {"sources": items}


def summarize_news_sources(sources):
    lines = ["新闻源列表", ""]
    items = sources.get("sources", [])
    if not items:
        lines.append("当前没有新闻源。可使用 news-source-add 添加 RSS 新闻源。")
        return "\n".join(lines)
    for item in items:
        lines.append(
            f"- {item.get('name')} | {item.get('type')} | enabled {item.get('enabled')} | "
            f"category {item.get('category')} | {item.get('url')}"
        )
    return "\n".join(lines)


def fetch_news_from_sources(sources, cache, timeout=8, per_source_limit=50, max_cache_items=1000):
    existing = {item.get("news_id"): item for item in cache.get("items", []) if item.get("news_id")}
    enabled_sources = [item for item in sources.get("sources", []) if item.get("enabled")]
    status = {
        "generated_at": now_iso(),
        "success_sources": [],
        "failed_sources": [],
        "fetched_count": 0,
        "new_count": 0,
        "warnings": [],
    }
    if not enabled_sources:
        status["infos"] = ["当前没有 enabled=true 的新闻源，可使用 news-source-add 添加或启用新闻源。"]
        return {"items": trim_cache(existing.values(), max_cache_items), "fetch_status": status}

    for source in enabled_sources:
        try:
            if source.get("type") == "rss":
                items = fetch_rss(source, timeout=timeout, limit=per_source_limit)
            elif source.get("type") == "web":
                items = fetch_web(source, timeout=timeout)
            else:
                raise ValueError(f"不支持的新闻源类型：{source.get('type')}")
            status["success_sources"].append(source.get("name"))
            status["fetched_count"] += len(items)
            for item in items:
                news_id = make_news_id(item)
                if news_id in existing:
                    continue
                item["news_id"] = news_id
                item["fetched_at"] = now_iso()
                existing[news_id] = item
                status["new_count"] += 1
        except Exception as exc:
            status["failed_sources"].append(source.get("name"))
            status["warnings"].append(f"{source.get('name')}: {exc}")
    return {"items": trim_cache(existing.values(), max_cache_items), "fetch_status": status}


def fetch_rss(source, timeout=8, limit=50):
    body = read_url(source.get("url"), timeout)
    root = ElementTree.fromstring(body)
    channel_items = root.findall(".//item")
    entries = channel_items if channel_items else root.findall(".//{http://www.w3.org/2005/Atom}entry")
    news = []
    for entry in entries[:limit]:
        title = first_text(entry, ["title", "{http://www.w3.org/2005/Atom}title"])
        summary = first_text(entry, ["description", "summary", "{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content"])
        link = first_text(entry, ["link"])
        if not link:
            atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
            link = atom_link.get("href") if atom_link is not None else ""
        published_at = first_text(entry, ["pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"])
        if not title:
            continue
        news.append(build_news_item(title, summary, link, published_at, source))
    return news


def fetch_web(source, timeout=8):
    body = read_url(source.get("url"), timeout).decode("utf-8", errors="ignore")
    titles = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", body, flags=re.IGNORECASE | re.DOTALL)
    if not titles:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
        titles = [title_match.group(1)] if title_match else []
    news = []
    for title in titles[:20]:
        clean_title = clean_html(title)
        if clean_title:
            news.append(build_news_item(clean_title, "", source.get("url", ""), now_iso(), source))
    return news


def read_url(url, timeout):
    if not url:
        raise ValueError("新闻源 URL 为空。")
    request = Request(url, headers={"User-Agent": "DrawdownGuard/5.3"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def import_news(cache, title, content="", source="manual", url="", published_at=None):
    item = build_news_item(title, content, url, published_at or now_iso(), {"name": source, "category": "manual"})
    item["news_id"] = make_news_id(item)
    item["fetched_at"] = now_iso()
    items = [existing for existing in cache.get("items", []) if existing.get("news_id") != item["news_id"]]
    items.append(item)
    return {"items": trim_cache(items, 1000), "fetch_status": cache.get("fetch_status", {})}, item


def analyze_news(cache, config, watchlist=None, days=1):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items = []
    warnings = []
    for item in cache.get("items", []):
        if parse_datetime(item.get("published_at") or item.get("fetched_at")) < cutoff:
            continue
        analysis = analyze_news_item(item, config, watchlist or {})
        if is_relevant_news(analysis):
            items.append(analysis)
    items = sorted(items, key=lambda item: (item.get("news_importance_score", 0), abs(item.get("impact_score", 0))), reverse=True)
    summary = build_portfolio_news_summary(items, len(cache.get("items", [])))
    return {
        "generated_at": now_iso(),
        "analysis_days": days,
        "portfolio_news_summary": summary,
        "items": items,
        "warnings": warnings,
        "fetch_status": cache.get("fetch_status", {}),
        "disclaimer": "新闻信号只作为投委会辅助判断，不自动交易，不修改补仓策略。",
    }


def analyze_news_item(item, config, watchlist):
    text = normalize_text(f"{item.get('title', '')} {item.get('summary', '')}")
    keyword_map = build_keyword_map(watchlist)
    matched_assets = []
    matched_keywords = []
    for asset_id, keywords in keyword_map.items():
        matched = [keyword for keyword in keywords if keyword and normalize_text(keyword) in text]
        if matched:
            matched_assets.append(asset_id)
            matched_keywords.extend(matched)

    category, sentiment, impact_score, horizon, explanation = classify_news(text, matched_assets)
    importance = score_importance(text, matched_assets, matched_keywords, category, impact_score)
    confidence = "high" if len(matched_keywords) >= 3 else "medium" if matched_keywords else "low"
    return {
        "news_id": item.get("news_id"),
        "title": item.get("title"),
        "source": item.get("source"),
        "published_at": item.get("published_at"),
        "url": item.get("url"),
        "matched_assets": matched_assets,
        "matched_keywords": sorted(set(matched_keywords)),
        "news_category": category,
        "sentiment": sentiment,
        "impact_horizon": horizon,
        "impact_score": max(-3, min(3, impact_score)),
        "news_importance_score": max(0, min(100, importance)),
        "confidence": confidence,
        "summary": explanation,
        "suggested_follow_up": suggest_follow_up(matched_assets, category, sentiment),
    }


def build_keyword_map(watchlist):
    keyword_map = {asset: list(keywords) for asset, keywords in ASSET_KEYWORDS.items()}
    watch_keywords = []
    for item in watchlist.get("funds", []):
        for field in ("fund_name", "reason", "candidate_role", "notes"):
            value = item.get(field)
            if not value:
                continue
            watch_keywords.extend(extract_keywords(str(value)))
    if watch_keywords:
        keyword_map["WATCHLIST"] = sorted(set(watch_keywords))
    return keyword_map


def classify_news(text, matched_assets):
    if any(word in text for word in ["监管收紧", "互联网监管", "处罚"]):
        return "regulation", "negative", -2, "medium_term", "监管收紧可能压制平台经济和港股科技估值。"
    if any(word in text for word in ["政策支持", "支持平台经济", "鼓励"]):
        return "regulation", "positive", 2, "medium_term", "政策支持可能改善相关资产风险偏好。"
    if any(word in text for word in ["降息", "利率下行", "宽松"]):
        return "monetary_policy", "positive", 2, "medium_term", "利率下行通常利好成长资产和债券，黄金可能受实际利率变化影响。"
    if any(word in text for word in ["加息", "利率上行", "收紧"]):
        return "monetary_policy", "negative", -2, "medium_term", "利率上行通常压制成长资产和债券估值。"
    if any(word in text for word in ["美联储", "央行", "货币政策"]):
        return "monetary_policy", "mixed", 1, "medium_term", "货币政策新闻会同时影响成长资产、债券和黄金。"
    if any(word in text for word in ["地缘冲突", "战争", "冲突升级"]):
        return "geopolitics", "mixed", 2 if "GOLD" in matched_assets else -1, "short_term", "地缘风险通常提高避险需求，同时增加权益资产波动。"
    if any(word in text for word in ["估值过高", "泡沫", "拥挤交易"]):
        return "valuation", "negative", -2, "short_term", "估值和交易拥挤风险上升，适合观察而不是追高。"
    if any(word in text for word in ["信用风险", "违约", "债务风险"]):
        return "risk_event", "negative", -2, "short_term", "信用风险事件会影响债券和风险资产情绪。"
    if any(word in text for word in ["黄金", "金价", "大宗商品", "有色金属", "铜", "铝", "锂", "白银"]):
        return "commodity", "mixed", 1, "short_term", "商品新闻主要影响黄金、有色金属和周期资产。"
    if any(word in text for word in ["ai", "算力", "英伟达", "半导体", "cpo", "芯片"]):
        return "industry", "positive", 2, "medium_term", "AI、算力和半导体新闻主要影响科技成长和先进制造资产。"
    if any(word in text for word in ["财报", "业绩"]):
        return "earnings", "mixed", 1, "short_term", "财报和业绩新闻需要结合估值和预期判断。"
    if matched_assets:
        return "industry", "neutral", 1, "unknown", "新闻与组合资产关键词相关，纳入观察。"
    return "unknown", "neutral", 0, "unknown", "未发现明确组合影响。"


def score_importance(text, matched_assets, matched_keywords, category, impact_score):
    score = 10
    score += min(35, len(set(matched_keywords)) * 8)
    if any(asset in matched_assets for asset in ("NASDAQ100", "GOLD", "HSTECH", "BONDS")):
        score += 25
    if category in ("macro", "monetary_policy", "geopolitics", "risk_event", "valuation", "commodity", "regulation"):
        score += 15
    if any(word in text for word in MAJOR_EVENT_WORDS):
        score += 20
    score += abs(impact_score) * 5
    return int(score)


def is_relevant_news(analysis):
    return (
        analysis.get("news_importance_score", 0) >= 50
        or abs(analysis.get("impact_score", 0)) >= 2
        or any(asset in analysis.get("matched_assets", []) for asset in ("NASDAQ100", "GOLD", "HSTECH", "BONDS"))
    )


def build_portfolio_news_summary(items, total_news_count):
    affected = {}
    tones = []
    high_impact = 0
    key_watch_items = []
    for item in items:
        if abs(item.get("impact_score", 0)) >= 2 or item.get("news_importance_score", 0) >= 75:
            high_impact += 1
        tones.append(item.get("sentiment"))
        for asset in item.get("matched_assets", []):
            affected[asset] = affected.get(asset, 0) + 1
    most_affected = [asset for asset, _ in sorted(affected.items(), key=lambda pair: pair[1], reverse=True)[:5]]
    overall_tone = aggregate_tone(tones)
    risk_alert = "high" if any(item.get("sentiment") == "negative" and item.get("news_importance_score", 0) >= 75 for item in items) else "medium" if high_impact else "low"
    for item in items[:3]:
        key_watch_items.append(item.get("summary"))
    return {
        "total_news_count": total_news_count,
        "relevant_news_count": len(items),
        "high_impact_news_count": high_impact,
        "most_affected_assets": most_affected,
        "overall_news_tone": overall_tone,
        "risk_alert_level": risk_alert,
        "key_watch_items": key_watch_items,
    }


def summarize_news_report(report):
    summary = report.get("portfolio_news_summary", {})
    fetch = report.get("fetch_status", {})
    lines = [
        "每日新闻分析报告",
        "",
        "新闻源状态：",
        f"- 成功来源：{', '.join(fetch.get('success_sources', [])) or '无'}",
        f"- 失败来源：{', '.join(fetch.get('failed_sources', [])) or '无'}",
        f"- 抓取新闻数量：{fetch.get('fetched_count', 0)}",
        f"- 相关新闻数量：{summary.get('relevant_news_count', 0)}",
        "",
        "组合新闻状态：",
        f"- overall_news_tone：{summary.get('overall_news_tone')}",
        f"- risk_alert_level：{summary.get('risk_alert_level')}",
        f"- most_affected_assets：{', '.join(summary.get('most_affected_assets', [])) or '无'}",
        "",
        "重要新闻：",
    ]
    if not report.get("items"):
        lines.append("- 暂无相关重要新闻。")
    for index, item in enumerate(report.get("items", [])[:10], start=1):
        lines.extend(
            [
                f"{index}. {item.get('title')}",
                f"   - 来源：{item.get('source')}",
                f"   - 影响资产：{', '.join(item.get('matched_assets', [])) or '无'}",
                f"   - 匹配关键词：{', '.join(item.get('matched_keywords', [])) or '无'}",
                f"   - 情绪：{item.get('sentiment')} | 影响分数：{item.get('impact_score')} | 重要性：{item.get('news_importance_score')}",
                f"   - 解释：{item.get('summary')}",
                f"   - 后续关注：{item.get('suggested_follow_up')}",
            ]
        )
    return "\n".join(lines)


def suggest_follow_up(matched_assets, category, sentiment):
    if not matched_assets:
        return "继续观察，不调整策略。"
    if sentiment == "negative":
        return "纳入观察清单，确认是否影响风险预算；不作为自动卖出指令。"
    if category in ("monetary_policy", "industry", "commodity"):
        return "结合量化信号和既定定投计划观察，不追逐短期新闻。"
    return "保持观察，新闻不改变补仓规则。"


def aggregate_tone(tones):
    positives = tones.count("positive")
    negatives = tones.count("negative")
    mixed = tones.count("mixed")
    if positives and negatives or mixed:
        return "mixed"
    if positives > negatives:
        return "positive"
    if negatives > positives:
        return "negative"
    return "neutral"


def build_news_item(title, summary, link, published_at, source):
    return {
        "title": clean_html(title),
        "summary": clean_html(summary or ""),
        "url": link or "",
        "published_at": normalize_datetime(published_at),
        "source": source.get("name", "unknown"),
        "source_category": source.get("category", "market"),
    }


def make_news_id(item):
    raw = f"{item.get('title', '')}|{item.get('source', '')}|{item.get('url', '')}"
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def trim_cache(items, limit):
    return sorted(items, key=lambda item: item.get("published_at") or item.get("fetched_at") or "", reverse=True)[:limit]


def first_text(entry, names):
    for name in names:
        node = entry.find(name)
        if node is not None and node.text:
            return node.text.strip()
    return ""


def clean_html(value):
    text = re.sub(r"<[^>]+>", "", value or "")
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def extract_keywords(value):
    parts = re.split(r"[\s,，/、|]+", value)
    return [part.strip() for part in parts if len(part.strip()) >= 2]


def normalize_text(value):
    return (value or "").lower()


def normalize_datetime(value):
    parsed = parse_datetime(value)
    return parsed.astimezone(timezone.utc).isoformat()


def parse_datetime(value):
    if not value:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        try:
            parsed = parsedate_to_datetime(text)
        except Exception:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except Exception:
                parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def now_iso():
    return datetime.now(timezone.utc).isoformat()
