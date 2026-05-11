#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

ROOT = Path("/Users/huangyuxuan/Documents/New project")
LATEST_JSON = ROOT / "site" / "data" / "latest.json"
LOG_DIR = ROOT / "logs" / "tw-stock-morning-brief"
MOPS_API_BASE = "https://mops.twse.com.tw/mops/api"
OFFICIAL_CACHE_DIR = ROOT / "data" / "official_cache"
TZ = ZoneInfo("Asia/Taipei")


def now_local() -> datetime:
    return datetime.now(TZ)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def official_fetch_mode() -> str:
    raw = clean_text(os.getenv("OFFICIAL_FETCH_MODE") or "prefer-live").lower()
    return raw or "prefer-live"


def cache_path_for_request(method: str, url: str, request_payload: dict[str, Any] | None = None) -> Path:
    raw_key = json.dumps(
        {
            "method": method,
            "url": url,
            "requestPayload": request_payload or {},
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha1(raw_key).hexdigest()
    host = url.split("//", 1)[-1].split("/", 1)[0].lower()
    bucket = re.sub(r"[^a-z0-9]+", "-", host).strip("-") or "official"
    return OFFICIAL_CACHE_DIR / bucket / f"{digest}.json"


def load_cached_payload(path: Path) -> Any | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    if isinstance(payload, dict) and "payload" in payload:
        return payload["payload"]
    return payload


def save_cached_payload(path: Path, url: str, payload: Any, request_payload: dict[str, Any] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wrapped = {
        "savedAt": now_local().isoformat(),
        "url": url,
        "requestPayload": request_payload or {},
        "payload": payload,
    }
    path.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2) + "\n")


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    cache_path = cache_path_for_request("POST", url, payload)
    if official_fetch_mode() == "cache-only":
        cached = load_cached_payload(cache_path)
        if cached is None:
            raise RuntimeError(f"Cache miss for {url}")
        return cached
    try:
        resp = requests.post(
            url,
            json=payload,
            timeout=(5, 12),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
        )
        resp.raise_for_status()
        parsed = resp.json()
        save_cached_payload(cache_path, url, parsed, payload)
        return parsed
    except (requests.RequestException, TimeoutError, json.JSONDecodeError):
        cached = load_cached_payload(cache_path)
        if cached is not None:
            return cached
        raise


def roc_year(year: int) -> str:
    return str(year - 1911)


def roc_date_string(d: date) -> str:
    return f"{roc_year(d.year)}/{d.month:02d}/{d.day:02d}"


def iso_date_string(d: date) -> str:
    return d.isoformat()


def recent_calendar_dates(anchor: date, count: int = 3) -> list[date]:
    return [anchor - timedelta(days=i) for i in range(count)]


def recent_trading_dates(anchor: date, count: int = 3) -> list[date]:
    out: list[date] = []
    cursor = anchor
    while len(out) < count:
        if cursor.weekday() < 5:
            out.append(cursor)
        cursor -= timedelta(days=1)
    return out


def hybrid_window(anchor: date) -> list[date]:
    dates = {d for d in recent_calendar_dates(anchor, 3)}
    dates.update(recent_trading_dates(anchor, 3))
    return sorted(dates)


def group_window_by_month(window_dates: list[date]) -> list[tuple[str, str, str, str]]:
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for d in window_dates:
        buckets[(d.year, d.month)].append(d.day)
    segments: list[tuple[str, str, str, str]] = []
    for (year, month), days in sorted(buckets.items()):
        segments.append((roc_year(year), str(month), str(min(days)), str(max(days))))
    return segments


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\r", " ").replace("\n", " ")).strip()


def strip_mops_prefix(text: str) -> str:
    patterns = [
        r"^最近三日 MOPS[^。]*。\s*",
        r"^MOPS 三日[^。]*。\s*",
    ]
    out = text or ""
    for pat in patterns:
        out = re.sub(pat, "", out)
    return out.strip()


def clamp(value: float, low: int, high: int) -> int:
    return max(low, min(high, int(round(value))))


@dataclass
class MopsItem:
    date: str
    time: str
    title: str
    direction: str
    impact_tier: str
    api_name: str
    params: dict[str, Any]
    summary: str
    detail_text: str
    url: str


POSITIVE_HIGH_PATTERNS = [
    r"接獲",
    r"得標",
    r"量產",
    r"重大合作",
    r"聯合授信",
    r"現金增資.*子公司",
    r"新增投資.*子公司",
    r"資本支出",
    r"購置機器設備",
    r"訂購機器設備",
    r"擴廠",
]

POSITIVE_MEDIUM_PATTERNS = [
    r"法人說明會",
    r"法說會",
    r"董事會通過.*合併財務報告",
    r"財務報告董事會召開日期",
    r"合併營收",
    r"月營業收入",
    r"買回庫藏股",
    r"股利分派",
    r"現金增資",
    r"增加投資",
]

NEGATIVE_HIGH_PATTERNS = [
    r"停工",
    r"火災",
    r"爆炸",
    r"重大虧損",
    r"重大損失",
    r"訴訟",
    r"檢調",
    r"搜索",
    r"處分固定資產.*重大",
]

NEGATIVE_MEDIUM_PATTERNS = [
    r"注意交易資訊",
    r"背書保證",
    r"資金貸與",
    r"處分有價證券",
    r"配合檢調",
]

UNCLEAR_PATTERNS = [
    r"應主管機關要求說明媒體報導",
    r"澄清",
    r"公告相關訊息，以利投資人區別瞭解",
]

NEUTRAL_PATTERNS = [
    r"董事會重要決議事項",
    r"股東常會",
    r"公司治理主管異動",
    r"主管異動",
    r"召開日期",
]

DIRECTION_BASE = {
    "high_positive": 80,
    "medium_positive": 65,
    "neutral": 35,
    "unclear": 25,
    "medium_negative": 15,
    "high_negative": 0,
}

DIRECTION_RANK = {
    "high_positive": 5,
    "medium_positive": 4,
    "neutral": 3,
    "unclear": 2,
    "medium_negative": 1,
    "high_negative": 0,
}

MATERIAL_EVENT_PATTERNS = [
    r"重大合作",
    r"合作",
    r"獨家代理",
    r"授權",
    r"接獲",
    r"得標",
    r"訂購機器設備",
    r"購置機器設備",
    r"資本支出",
    r"擴廠",
    r"擴產",
    r"新增投資",
    r"現金增資.*子公司",
    r"增資.*子公司",
    r"取得.*設備",
    r"取得.*廠房",
    r"取得.*土地",
]

PROCEDURAL_MOPS_PATTERNS = [
    r"董事會召開日期",
    r"股東常會",
    r"股東會",
    r"法人說明會",
    r"法說會",
    r"受邀參加",
    r"注意交易資訊",
    r"公告相關訊息，以利投資人區別",
    r"背書保證",
    r"資金貸與",
    r"發言人",
    r"代理發言人",
    r"公司治理主管",
    r"現金股利",
    r"股利分派",
    r"庫藏股",
    r"董事異動",
    r"獨立董事",
    r"自然人董事",
    r"法人董事",
    r"經理人",
    r"總經理異動",
    r"辭任",
    r"改派",
    r"解任",
    r"新任",
    r"澄清",
    r"媒體報導",
    r"傳播媒體名稱",
]

FINANCIAL_STRONG_PATTERNS = [
    r"通過.*合併財務報告",
    r"合併財務報告",
    r"月營業收入",
    r"合併營收",
    r"營業收入",
    r"營業毛利",
    r"營業利益",
    r"稅前淨利",
    r"本期淨利",
    r"每股盈餘",
    r"EPS",
    r"創高",
    r"年增",
    r"季增",
    r"轉盈",
    r"毛利率",
]

FINANCIAL_WEAK_PATTERNS = [
    r"財務報告董事會召開日期",
    r"董事會召開日期",
    r"預計提報董事會",
]

FINANCIAL_NEGATIVE_PATTERNS = [
    r"虧損",
    r"轉虧",
    r"年減",
    r"季減",
    r"衰退",
    r"下滑",
]

ORDER_QUAL_PATTERNS = [
    r"接單",
    r"接獲",
    r"得標",
    r"客戶",
    r"認證",
    r"qualification",
    r"驗證",
    r"導入",
    r"量產",
    r"試產",
    r"ramp",
    r"供貨",
]

NEGATIVE_ORDER_PATTERNS = [
    r"終止",
    r"取消",
    r"遞延",
    r"延後",
    r"流失",
]

PRICE_SHORTAGE_PATTERNS = [
    r"漲價",
    r"調漲",
    r"報價",
    r"價格",
    r"缺貨",
    r"allocation",
    r"shortage",
    r"lead time",
    r"交期",
    r"瓶頸",
]

CAPEX_DEPLOYMENT_PATTERNS = [
    r"資本支出",
    r"capex",
    r"設備",
    r"擴產",
    r"擴廠",
    r"量產",
    r"deployment",
    r"導入",
    r"建廠",
    r"投資",
]

ATTENTION_PATTERNS = [
    r"外資評等",
    r"鉅亨外資評等",
    r"券商",
    r"法說會",
    r"法人說明會",
    r"受邀參加",
    r"目標價",
    r"roadshow",
]

EXCLUDE_MATERIAL_EVENT_PATTERNS = [
    r"董事異動",
    r"獨立董事",
    r"自然人董事",
    r"法人董事",
    r"經理人",
    r"總經理異動",
    r"辭任",
    r"改派",
    r"解任",
    r"新任",
    r"澄清",
    r"媒體報導",
    r"傳播媒體名稱",
    r"注意交易資訊",
    r"資金貸與",
    r"背書保證",
    r"股東常會",
    r"股東會",
    r"董事會召開日期",
    r"受邀參加.*法說",
    r"法人說明會",
    r"轉換公司債",
    r"贖回權",
    r"終止櫃檯買賣",
]


def classify_mops_item(title: str, detail_text: str) -> tuple[str, str]:
    blob = f"{title} {detail_text}"
    checks = [
        ("high_negative", NEGATIVE_HIGH_PATTERNS),
        ("high_positive", POSITIVE_HIGH_PATTERNS),
        ("medium_negative", NEGATIVE_MEDIUM_PATTERNS),
        ("medium_positive", POSITIVE_MEDIUM_PATTERNS),
        ("unclear", UNCLEAR_PATTERNS),
        ("neutral", NEUTRAL_PATTERNS),
    ]
    for direction, patterns in checks:
        if any(re.search(pat, blob) for pat in patterns):
            return direction, direction
    return "unclear", "unclear"


def parse_roc_date(text: str) -> date | None:
    raw = clean_text(text)
    if not raw:
        return None
    raw = raw.replace("-", "/")
    try:
        if "/" in raw:
            year_str, month_str, day_str = raw.split("/")
            return date(int(year_str) + 1911, int(month_str), int(day_str))
        if len(raw) == 7:
            return date(int(raw[:3]) + 1911, int(raw[3:5]), int(raw[5:7]))
    except ValueError:
        return None
    return None


def event_blob(title: str, detail_text: str) -> str:
    return clean_text(f"{title} {detail_text}")


def match_any(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def item_tags(item: MopsItem) -> set[str]:
    blob = event_blob(item.title, item.detail_text)
    tags: set[str] = set()
    if match_any(MATERIAL_EVENT_PATTERNS, blob):
        tags.add("material")
    if match_any(PROCEDURAL_MOPS_PATTERNS, blob):
        tags.add("procedural")
    if match_any(FINANCIAL_STRONG_PATTERNS + FINANCIAL_WEAK_PATTERNS, blob):
        tags.add("financial")
    if match_any(ORDER_QUAL_PATTERNS, blob):
        tags.add("order_qualification")
    if match_any(PRICE_SHORTAGE_PATTERNS, blob):
        tags.add("price_shortage")
    if match_any(CAPEX_DEPLOYMENT_PATTERNS, blob):
        tags.add("capex_deployment")
    if match_any(ATTENTION_PATTERNS, blob):
        tags.add("attention")
    return tags


def recent_days_bonus(item_date: str, anchor: date, within_days: int) -> bool:
    parsed = parse_roc_date(item_date)
    if not parsed:
        return False
    delta = (anchor - parsed).days
    return 0 <= delta <= within_days


def aggregate_stock_text(stock: dict[str, Any], items30: list[MopsItem]) -> str:
    parts: list[str] = [
        stock.get("coreReason", ""),
        stock.get("notPricedIn", ""),
        stock.get("targetLogic", ""),
        stock.get("role", ""),
        stock.get("mops3dSummary", ""),
    ]
    parts.extend(stock.get("catalysts") or [])
    parts.extend(stock.get("sourceRefs") or [])
    parts.extend(item.title for item in items30)
    parts.extend(item.detail_text for item in items30 if item.detail_text)
    return clean_text(" ".join(parts))


def scale_persistence(relative_strengths: list[float]) -> int:
    positives = [value for value in relative_strengths if value > 0]
    positive_count = len(positives)
    avg_positive = sum(positives) / positive_count if positive_count else 0.0
    return clamp(positive_count * 25 + avg_positive * 2.5, 0, 100)


def rank_primary(items: list[MopsItem]) -> MopsItem:
    return max(items, key=lambda item: (DIRECTION_RANK[item.direction], item.date, item.time, item.title))


def summarize_items(prefix: str, items: list[MopsItem], primary: MopsItem | None) -> str:
    if not items:
        return prefix
    if primary is None:
        primary = rank_primary(items)
    summary = f"{prefix} 最近 30 日共 {len(items)} 則；核心訊號為「{primary.title}」"
    if primary.summary:
        summary += f"，內文重點：{primary.summary}"
    return summary + "。"


def score_material_company_events_30d(items30: list[MopsItem], anchor: date) -> tuple[int, str, str]:
    material_items = [
        item
        for item in items30
        if (
            ("material" in item_tags(item) or "capex_deployment" in item_tags(item))
            and not match_any(EXCLUDE_MATERIAL_EVENT_PATTERNS, event_blob(item.title, item.detail_text))
        )
    ]
    if not material_items:
        return 20, "no_material_company_event_30d", "最近 30 日未查到可驗證的 material company event。"

    primary = rank_primary(material_items)
    base_map = {
        "high_positive": 85,
        "medium_positive": 70,
        "neutral": 45,
        "unclear": 35,
        "medium_negative": 15,
        "high_negative": 0,
    }
    score = base_map[primary.direction]
    positive_count = sum(item.direction in {"high_positive", "medium_positive"} for item in material_items)
    negative_count = sum(item.direction in {"medium_negative", "high_negative"} for item in material_items)
    if recent_days_bonus(primary.date, anchor, 7):
        score += 10
    if positive_count >= 2:
        score += 10
    if positive_count and negative_count:
        score -= 15
    return clamp(score, 0, 100), primary.direction, summarize_items("30 日公司事件", material_items, primary)


def score_procedural_mops_30d(items30: list[MopsItem], anchor: date) -> tuple[int, str, str]:
    procedural_items = [
        item
        for item in items30
        if "procedural" in item_tags(item) and "material" not in item_tags(item) and "capex_deployment" not in item_tags(item)
    ]
    if not procedural_items:
        return 20, "no_procedural_mops_30d", "最近 30 日沒有額外程序性 MOPS。"

    primary = rank_primary(procedural_items)
    base_map = {
        "high_positive": 55,
        "medium_positive": 45,
        "neutral": 35,
        "unclear": 25,
        "medium_negative": 15,
        "high_negative": 0,
    }
    score = base_map[primary.direction]
    if recent_days_bonus(primary.date, anchor, 7):
        score += 5
    positive_count = sum(item.direction in {"high_positive", "medium_positive"} for item in procedural_items)
    negative_count = sum(item.direction in {"medium_negative", "high_negative"} for item in procedural_items)
    if positive_count >= 2:
        score += 5
    if positive_count and negative_count:
        score -= 10
    return clamp(score, 0, 100), primary.direction, summarize_items("30 日程序性 MOPS", procedural_items, primary)


def score_revenue_earnings_acceleration(stock: dict[str, Any], items30: list[MopsItem], anchor: date) -> tuple[int, str]:
    text_blob = aggregate_stock_text(stock, items30)
    financial_items = [item for item in items30 if "financial" in item_tags(item)]
    strong_items = [item for item in financial_items if match_any(FINANCIAL_STRONG_PATTERNS, event_blob(item.title, item.detail_text))]
    weak_items = [item for item in financial_items if match_any(FINANCIAL_WEAK_PATTERNS, event_blob(item.title, item.detail_text))]
    negative_hits = len(re.findall("|".join(FINANCIAL_NEGATIVE_PATTERNS), text_blob)) if FINANCIAL_NEGATIVE_PATTERNS else 0
    positive_hits = len(re.findall("|".join(FINANCIAL_STRONG_PATTERNS), text_blob)) if FINANCIAL_STRONG_PATTERNS else 0

    if strong_items:
        primary = rank_primary(strong_items)
        score = 80
        if recent_days_bonus(primary.date, anchor, 10):
            score += 10
        if len(strong_items) >= 2 or positive_hits >= 2:
            score += 10
        if negative_hits:
            score -= 20
        summary = summarize_items("30 日營收 / 財報加速", strong_items, primary)
        return clamp(score, 0, 100), summary

    if weak_items or positive_hits:
        primary = rank_primary(weak_items) if weak_items else None
        score = 45 + min(20, positive_hits * 5)
        if primary and recent_days_bonus(primary.date, anchor, 10):
            score += 5
        if negative_hits:
            score -= 10
        summary = summarize_items("30 日營收 / 財報訊號偏弱", weak_items, primary) if weak_items else "最近 30 日有營收 / 財報相關文字訊號，但強度有限。"
        return clamp(score, 0, 100), summary

    if negative_hits:
        return 15, "最近 30 日營收 / 財報文字訊號偏弱或帶負面字樣。"
    return 20, "最近 30 日未查到足以支撐營收 / 財報加速分數的可驗證訊號。"


def score_order_qualification(stock: dict[str, Any], items30: list[MopsItem], anchor: date) -> tuple[int, str]:
    text_blob = aggregate_stock_text(stock, items30)
    order_items = [item for item in items30 if "order_qualification" in item_tags(item)]
    negative_hits = len(re.findall("|".join(NEGATIVE_ORDER_PATTERNS), text_blob)) if NEGATIVE_ORDER_PATTERNS else 0
    text_hits = len(re.findall("|".join(ORDER_QUAL_PATTERNS), text_blob, flags=re.IGNORECASE)) if ORDER_QUAL_PATTERNS else 0

    if order_items:
        primary = rank_primary(order_items)
        score = 75 if primary.direction in {"high_positive", "medium_positive"} else 50
        if recent_days_bonus(primary.date, anchor, 10):
            score += 10
        if len(order_items) >= 2 or text_hits >= 3:
            score += 10
        if negative_hits:
            score -= 20
        return clamp(score, 0, 100), summarize_items("30 日訂單 / 客戶 / 認證", order_items, primary)

    if text_hits >= 2:
        score = 55 + min(15, (text_hits - 2) * 5)
        if negative_hits:
            score -= 15
        return clamp(score, 0, 100), "最近 30 日文字訊號顯示有訂單 / 客戶 / 認證 / 量產節點，但官方公司層事件不夠集中。"

    if negative_hits:
        return 20, "最近 30 日訂單 / 客戶 / 認證訊號不足，且有延後或終止字樣。"
    return 20, "最近 30 日未查到足以支撐訂單 / 客戶 / 認證分數的集中訊號。"


def score_attention(stock: dict[str, Any], items30: list[MopsItem]) -> tuple[int, str]:
    text_blob = aggregate_stock_text(stock, items30)
    hits = len(re.findall("|".join(ATTENTION_PATTERNS), text_blob, flags=re.IGNORECASE)) if ATTENTION_PATTERNS else 0
    broker_hits = sum("外資評等" in ref or "鉅亨外資評等" in ref or "目標價" in ref for ref in stock.get("sourceRefs") or [])
    if broker_hits >= 2:
        return 80, "最近資料中可見多個券商 / 外資評等或目標價注意力來源。"
    if broker_hits == 1:
        return 70, "最近資料中可見至少一個券商 / 外資評等來源。"
    if hits >= 3:
        return 60, "最近文字訊號顯示市場注意力正在上升。"
    if hits:
        return 45, "最近有法說 / 媒體 / 關注度訊號，但不是核心驅動。"
    return 20, "最近沒有額外的券商或市場注意力加分。"


def derive_speculation_flag(stock: dict[str, Any], scores: dict[str, int]) -> str:
    if (
        scores["attentionScore"] >= 70
        and scores["materialCompanyEvent30dScore"] < 35
        and scores["revenueEarningsAccelerationScore"] < 35
        and scores["orderQualificationScore"] < 35
    ):
        return "attention_without_company_evidence"
    if (
        scores["shortImpulseScore"] >= 80
        and scores["monthContinuationScore"] < 70
        and scores["materialCompanyEvent30dScore"] < 35
        and scores["revenueEarningsAccelerationScore"] < 35
    ):
        return "short_impulse_without_continuation"
    return ""


def rescaled_stock_score(breakdown: dict[str, Any]) -> int:
    persistence_scaled = breakdown.get("persistenceScaledScore", 0)
    return clamp(
        (breakdown.get("materialCompanyEvent30dScore") or 0) * 0.32
        + (breakdown.get("revenueEarningsAccelerationScore") or 0) * 0.16
        + (breakdown.get("orderQualificationScore") or 0) * 0.20
        + (breakdown.get("monthContinuationScore") or 0) * 0.12
        + persistence_scaled * 0.10
        + (breakdown.get("shortImpulseScore") or 0) * 0.05
        + (breakdown.get("attentionScore") or 0) * 0.04
        + (breakdown.get("proceduralMopsScore") or 0) * 0.01,
        0,
        100,
    )


def theme_text_blob(theme: dict[str, Any], stocks: list[dict[str, Any]]) -> str:
    parts: list[str] = [
        theme.get("name", ""),
        theme.get("summary", ""),
        theme.get("pricingView", ""),
        theme.get("policyView", ""),
        theme.get("premiumSpace", ""),
        theme.get("mops3dSummary", ""),
    ]
    for item in theme.get("whyNow") or []:
        if isinstance(item, dict):
            parts.append(item.get("label", ""))
            parts.append(item.get("text", ""))
        else:
            parts.append(str(item))
    for stock in stocks:
        parts.append(stock.get("coreReason", ""))
        parts.extend(stock.get("catalysts") or [])
        parts.append(stock.get("mops3dSummary", ""))
        parts.append(stock.get("materialCompanyEvent30dSummary", ""))
    return clean_text(" ".join(parts))


def score_company_evidence_spread(stocks: list[dict[str, Any]]) -> int:
    strong_count = sum(
        1
        for stock in stocks
        if max(
            (stock.get("scoreBreakdown") or {}).get("materialCompanyEvent30dScore", 0),
            (stock.get("scoreBreakdown") or {}).get("revenueEarningsAccelerationScore", 0),
            (stock.get("scoreBreakdown") or {}).get("orderQualificationScore", 0),
        ) >= 65
    )
    negative_count = sum(
        1 for stock in stocks if (stock.get("scoreBreakdown") or {}).get("mops3dScore", 20) <= 15
    )
    if strong_count >= 3 and negative_count == 0:
        return 90
    if strong_count == 2 and negative_count <= 1:
        return 75
    if strong_count == 1 and negative_count == 0:
        return 55
    if negative_count >= 2:
        return 20
    return 35


def score_external_demand_deployment(theme: dict[str, Any], stocks: list[dict[str, Any]]) -> int:
    text_blob = theme_text_blob(theme, stocks)
    base_scores = sorted(
        max(
            (stock.get("scoreBreakdown") or {}).get("materialCompanyEvent30dScore", 0),
            (stock.get("scoreBreakdown") or {}).get("orderQualificationScore", 0),
        )
        for stock in stocks
    )
    top = base_scores[-3:] if base_scores else [20]
    core = sum(top) / len(top)
    keyword_hits = len(re.findall("|".join(CAPEX_DEPLOYMENT_PATTERNS + ORDER_QUAL_PATTERNS), text_blob, flags=re.IGNORECASE))
    breadth = sum(
        1
        for stock in stocks
        if max(
            (stock.get("scoreBreakdown") or {}).get("materialCompanyEvent30dScore", 0),
            (stock.get("scoreBreakdown") or {}).get("orderQualificationScore", 0),
        ) >= 65
    )
    tail = min(100, breadth * 20 + keyword_hits * 4)
    return clamp(core * 0.7 + tail * 0.3, 0, 100)


def score_price_shortage_leadtime(theme: dict[str, Any], stocks: list[dict[str, Any]]) -> int:
    text_blob = theme_text_blob(theme, stocks)
    keyword_hits = len(re.findall("|".join(PRICE_SHORTAGE_PATTERNS), text_blob, flags=re.IGNORECASE)) if PRICE_SHORTAGE_PATTERNS else 0
    stock_hits = sum(
        1
        for stock in stocks
        if match_any(PRICE_SHORTAGE_PATTERNS, aggregate_stock_text(stock, []))
        or "價格重估" in stock.get("coreReason", "")
    )
    if keyword_hits >= 4 or stock_hits >= 3:
        return 85
    if keyword_hits >= 2 or stock_hits >= 2:
        return 70
    if keyword_hits or stock_hits:
        return 50
    return 25


def scale_theme_calendar_second_leg(score_breakdown: dict[str, Any]) -> int:
    calendar_component = ((score_breakdown.get("calendarScore") or 0) / 25) * 55
    second_leg_component = ((score_breakdown.get("secondLegEvidenceScore") or 0) / 20) * 45
    return clamp(calendar_component + second_leg_component, 0, 100)


def scale_theme_persistence(theme: dict[str, Any]) -> int:
    raw = (theme.get("scoreBreakdown") or {}).get("persistenceScore", 0)
    return clamp(raw * (100 / 15), 0, 100)


def score_theme_attention(theme: dict[str, Any], stocks: list[dict[str, Any]]) -> int:
    avg_attention = sum((stock.get("scoreBreakdown") or {}).get("attentionScore", 20) for stock in stocks) / max(len(stocks), 1)
    heat_bonus = 10 if theme.get("heat") in {"偏熱", "中偏熱", "溫熱"} else 0
    return clamp(avg_attention * 0.8 + heat_bonus, 0, 100)


def build_mops_item(detail_json: dict[str, Any], row: list[Any], api_name: str, params: dict[str, Any]) -> MopsItem:
    result = detail_json.get("result") or {}
    titles = [clean_text((x or {}).get("main")) for x in result.get("titles") or []]
    values = (result.get("data") or [[]])[0]
    field_map: dict[str, str] = {}
    for idx, title in enumerate(titles):
        field_map[title] = clean_text(values[idx] if idx < len(values) else "")

    detail_text = field_map.get("說明", "")
    title = clean_text(field_map.get("主旨") or row[4] if len(row) > 4 else "")
    direction, impact_tier = classify_mops_item(title, detail_text)
    params_str = "&".join(f"{k}={v}" for k, v in params.items())
    return MopsItem(
        date=clean_text(row[2] if len(row) > 2 else field_map.get("發言日期")),
        time=clean_text(row[3] if len(row) > 3 else field_map.get("發言時間")),
        title=title,
        direction=direction,
        impact_tier=impact_tier,
        api_name=api_name,
        params=params,
        summary=clean_text(detail_text)[:240],
        detail_text=clean_text(detail_text),
        url=f"https://mops.twse.com.tw/mops/#/web/{api_name}?{params_str}",
    )


def fetch_stock_mops_items(ticker: str, window_dates: list[date]) -> list[MopsItem]:
    wanted_dates = {roc_date_string(d) for d in window_dates}
    items: list[MopsItem] = []
    for year, month, first_day, last_day in group_window_by_month(window_dates):
        try:
            resp = post_json(
                f"{MOPS_API_BASE}/t05st01",
                {
                    "companyId": ticker,
                    "year": year,
                    "month": month,
                    "firstDay": first_day,
                    "lastDay": last_day,
                },
            )
        except (requests.RequestException, TimeoutError, json.JSONDecodeError, RuntimeError):
            continue
        rows = ((resp.get("result") or {}).get("data") or [])
        for row in rows:
            if len(row) < 6:
                continue
            if clean_text(row[2]) not in wanted_dates:
                continue
            link_info = row[5] or {}
            api_name = link_info.get("apiName")
            params = link_info.get("parameters") or {}
            if not api_name or not params:
                continue
            try:
                detail = post_json(f"{MOPS_API_BASE}/{api_name}", params)
            except (requests.RequestException, TimeoutError, json.JSONDecodeError, RuntimeError):
                continue
            items.append(build_mops_item(detail, row, api_name, params))
    items.sort(key=lambda item: (item.date, item.time, item.title))
    return items


def stock_mops_score(items: list[MopsItem], window_dates: list[date]) -> tuple[int, str, str]:
    if not items:
        return 20, "no_recent_mops_material_info_verified", "最近三日未查到官方 MOPS 重大訊息。"

    latest_window_dates = {roc_date_string(window_dates[-1])}
    primary = max(items, key=lambda item: (DIRECTION_RANK[item.direction], item.date, item.time))
    score = DIRECTION_BASE[primary.direction]

    if primary.date in latest_window_dates:
        score += 10

    positive_count = sum(item.direction in {"high_positive", "medium_positive"} for item in items)
    has_negative = any(item.direction in {"medium_negative", "high_negative"} for item in items)
    if positive_count >= 2:
        score += 10
    if positive_count and has_negative:
        score -= 15

    sorted_items = sorted(items, key=lambda item: (item.date, item.time))
    if len(sorted_items) >= 2:
        if DIRECTION_RANK[sorted_items[-1].direction] < DIRECTION_RANK[sorted_items[-2].direction]:
            score -= 10

    summary = f"最近三日 MOPS {len(items)} 則；最高影響訊號為「{primary.title}」"
    if primary.summary:
        summary += f"，內文重點：{primary.summary}"
    return clamp(score, 0, 100), primary.direction, summary + "。"


def summarize_gate_mops(score: int, signal: str) -> str:
    if signal == "no_recent_mops_material_info_verified":
        return "最近三日未查到官方 MOPS 重大訊息；以 baseline 20 分處理。"
    if score <= 15:
        return f"最近三日 MOPS 為負面壓力（{signal}，{score} 分）。"
    if score >= 65:
        return f"最近三日 MOPS 提供正面佐證（{signal}，{score} 分）。"
    return f"最近三日 MOPS 有訊號但方向有限（{signal}，{score} 分）。"


def theme_mops_score(items_by_stock: list[dict[str, Any]], second_leg_status: str) -> tuple[int, dict[str, Any], str]:
    scores = sorted((stock["mops3dScore"] for stock in items_by_stock), reverse=True)
    top3 = scores[:3] or [20]
    theme_mops_core = sum(top3) / len(top3)
    positive_count = sum(stock["mops3dScore"] >= 65 for stock in items_by_stock)
    negative_count = sum(stock["mops3dScore"] <= 15 for stock in items_by_stock)

    if positive_count >= 3 and negative_count == 0:
        breadth_component = 90
    elif positive_count == 2 and negative_count <= 1:
        breadth_component = 75
    elif positive_count == 1 and negative_count == 0:
        breadth_component = 55
    elif negative_count >= 2:
        breadth_component = 10
    else:
        breadth_component = 30

    score = round(theme_mops_core * 0.70 + breadth_component * 0.30)
    if positive_count == 1 and second_leg_status != "通過":
        score = min(score, 60)

    breadth = {
        "positiveStockCount": positive_count,
        "negativeStockCount": negative_count,
    }
    summary = (
        f"最近三日官方 MOPS 在題材內有 {positive_count} 檔正向、{negative_count} 檔負向；"
        f"核心 MOPS 分數 {round(theme_mops_core)} 分。"
    )
    return score, breadth, summary


def recompute_stock_score(stock: dict[str, Any]) -> int:
    breakdown = stock.get("scoreBreakdown") or {}
    return rescaled_stock_score(breakdown)


def recompute_theme_score(theme: dict[str, Any]) -> int:
    breakdown = theme.get("scoreBreakdown") or {}
    return clamp(
        (breakdown.get("externalDemandDeployment30dScore") or 0) * 0.24
        + (breakdown.get("priceShortageLeadtime30dScore") or 0) * 0.18
        + (breakdown.get("companyEvidenceSpreadScore") or 0) * 0.18
        + (breakdown.get("calendarSecondLegCompositeScore") or 0) * 0.14
        + (breakdown.get("persistenceScaledScore") or 0) * 0.14
        + (breakdown.get("shortImpulseScore") or 0) * 0.07
        + (breakdown.get("attentionScore") or 0) * 0.05,
        0,
        100,
    )


def strip_model_prefixes(text: str) -> str:
    out = strip_mops_prefix(text)
    patterns = [
        r"^30 日公司事件[^。]*。\s*",
        r"^30 日營收 / 財報[^。]*。\s*",
        r"^最近三日 MOPS[^。]*。\s*",
        r"^這次排序已改成[^。]*。\s*",
    ]
    for pattern in patterns:
        out = re.sub(pattern, "", out)
    return out.strip()


def build_stock_texts(stock: dict[str, Any], info: dict[str, Any]) -> None:
    material_score = info["material_score"]
    revenue_score = info["revenue_score"]
    order_score = info["order_score"]
    speculation_flag = info["speculation_flag"]

    if material_score >= 70 and revenue_score >= 70:
        lead = "30 日公司事件與營收 / 財報加速同時成立，月內第二段行情不再只靠近三日 MOPS。"
        invalidation = "若 30 日公司事件後續沒有延伸、且下一個財報 / 營收節點無法接棒，這筆月內續航 setup 視為失效。"
    elif material_score >= 70:
        lead = "30 日 material company events 已成為主要支撐，月內排序現在更看公司層證據而不是近三日公告密度。"
        invalidation = "若 30 日公司事件無法延伸成訂單、量產或財務加速，這筆月內續航 setup 會轉弱。"
    elif revenue_score >= 70:
        lead = "30 日營收 / 財報加速是主要支撐，月內排序現在把基本面加速放在程序性公告之前。"
        invalidation = "若下一個營收 / 財報節點無法確認加速，這筆月內續航 setup 會失去優勢。"
    elif order_score >= 70:
        lead = "30 日訂單 / 客戶 / 認證訊號成立，月內排序現在把這類 company evidence 直接拉進核心分數。"
        invalidation = "若訂單 / 認證 / 客戶導入沒有進一步落地，這筆月內續航 setup 會回到觀察池。"
    else:
        lead = "這檔股票目前缺少高品質 30 日公司層證據，月內排序更多依賴既有續航與相對強弱。"
        invalidation = "若接下來沒有新的 material company event、營收 / 財報加速或訂單 / 認證節點，這筆月內續航 setup 視為失效。"

    if speculation_flag == "attention_without_company_evidence":
        lead += " 目前可見市場注意力，但公司層硬證據仍不足。"

    stock["coreReason"] = lead + " " + strip_model_prefixes(stock.get("coreReason", ""))
    stock["notPricedIn"] = lead + " " + strip_model_prefixes(stock.get("notPricedIn", ""))
    stock["targetLogic"] = (
        "這次排序已改成 30 日公司事件 / 營收財報加速 / 月內續航的研究校準版。 "
        + lead
        + " "
        + strip_model_prefixes(stock.get("targetLogic", ""))
    )
    stock["invalidationTrigger"] = invalidation


def update_stock_obj(stock: dict[str, Any], info: dict[str, Any], window_dates: list[date]) -> None:
    breakdown = stock.setdefault("scoreBreakdown", {})
    breakdown["mops3dScore"] = info["mops3d_score"]
    breakdown["materialCompanyEvent30dScore"] = info["material_score"]
    breakdown["revenueEarningsAccelerationScore"] = info["revenue_score"]
    breakdown["orderQualificationScore"] = info["order_score"]
    breakdown["proceduralMopsScore"] = info["procedural_score"]
    breakdown["attentionScore"] = info["attention_score"]
    breakdown["persistenceScaledScore"] = scale_persistence(
        [
            float(breakdown.get("relativeStrength5d") or 0),
            float(breakdown.get("relativeStrength10d") or 0),
            float(breakdown.get("relativeStrength20d") or 0),
        ]
    )
    stock["mops3dSignal"] = info["mops3d_signal"]
    stock["mops3dSummary"] = info["mops3d_summary"]
    stock["mops3dItems"] = info["mops3d_items"]
    stock["materialCompanyEvent30dSummary"] = info["material_summary"]
    stock["revenueEarnings30dSummary"] = info["revenue_summary"]
    stock["orderQualification30dSummary"] = info["order_summary"]
    stock["speculationFlag"] = info["speculation_flag"]
    gate_status = stock.setdefault("gateStatus", {})
    gate_status["mops3d"] = summarize_gate_mops(info["mops3d_score"], info["mops3d_signal"])
    gate_status["materialCompanyEvents30d"] = info["material_summary"]
    gate_status["revenueEarnings30d"] = info["revenue_summary"]
    gate_status["speculation"] = info["speculation_flag"] or "none"
    stock["stockScore"] = recompute_stock_score(stock)
    build_stock_texts(stock, info)


def update_theme_obj(theme: dict[str, Any], stocks: list[dict[str, Any]], window_dates: list[date]) -> None:
    stock_infos = [
        {
            "ticker": stock["ticker"],
            "mops3dScore": stock.get("scoreBreakdown", {}).get("mops3dScore", 20),
        }
        for stock in stocks
    ] or [{"ticker": "", "mops3dScore": 20}]
    score, breadth, summary = theme_mops_score(stock_infos, (theme.get("gateStatus") or {}).get("secondLegEvidence", ""))
    breakdown = theme.setdefault("scoreBreakdown", {})
    breakdown["mops3dScore"] = score
    breakdown["externalDemandDeployment30dScore"] = score_external_demand_deployment(theme, stocks)
    breakdown["priceShortageLeadtime30dScore"] = score_price_shortage_leadtime(theme, stocks)
    breakdown["companyEvidenceSpreadScore"] = score_company_evidence_spread(stocks)
    breakdown["calendarSecondLegCompositeScore"] = scale_theme_calendar_second_leg(breakdown)
    breakdown["persistenceScaledScore"] = scale_theme_persistence(theme)
    breakdown["attentionScore"] = score_theme_attention(theme, stocks)
    breadth["windowDates"] = [iso_date_string(d) for d in window_dates]
    theme["mops3dBreadth"] = breadth
    theme["mops3dSummary"] = summary
    theme.setdefault("gateStatus", {})["mops3d"] = summarize_gate_mops(score, "theme")
    theme["themeScore"] = recompute_theme_score(theme)


def make_top_pick(stock: dict[str, Any], theme_name: str, existing_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    prior = existing_map.get(stock["ticker"], {})
    reason = prior.get("reason") or stock.get("coreReason") or stock.get("notPricedIn") or ""
    alternative = prior.get("alternativeRejected") or ""
    return {
        "rank": 0,
        "ticker": stock["ticker"],
        "name": stock["name"],
        "theme": theme_name,
        "reason": reason,
        "state": stock.get("state", ""),
        "stockScore": stock.get("stockScore", 0),
        "gateStatus": deepcopy(stock.get("gateStatus", {})),
        "alternativeRejected": alternative,
        "scoreBreakdown": deepcopy(stock.get("scoreBreakdown", {})),
        "invalidationType": stock.get("invalidationType", ""),
        "mops3dSignal": stock.get("mops3dSignal", ""),
        "mops3dSummary": stock.get("mops3dSummary", ""),
        "mops3dItems": deepcopy(stock.get("mops3dItems", [])),
        "materialCompanyEvent30dSummary": stock.get("materialCompanyEvent30dSummary", ""),
        "revenueEarnings30dSummary": stock.get("revenueEarnings30dSummary", ""),
        "orderQualification30dSummary": stock.get("orderQualification30dSummary", ""),
        "speculationFlag": stock.get("speculationFlag", ""),
    }


def recalc_market_regime(report: dict[str, Any]) -> None:
    monthly = report.get("marketSnapshot", {}).get("marketRegime")
    if not monthly:
        return
    trade_themes = report.get("themes") or []
    avg_score = sum(theme.get("themeScore", 0) for theme in trade_themes) / max(len(trade_themes), 1)
    breakdown_count = sum(1 for theme in report.get("observationThemes") or [] if theme.get("state") == "breakdown")
    theme_health = 0
    if avg_score >= 80:
        theme_health += 10
    elif avg_score >= 70:
        theme_health += 5
    if breakdown_count <= 1:
        theme_health += 10
    elif breakdown_count <= 3:
        theme_health += 5
    monthly["scoreBreakdown"]["themeHealth"] = theme_health
    monthly["score"] = sum(monthly["scoreBreakdown"].values())
    monthly["stance"], monthly["mode"] = regime_band(monthly["score"])

    short_term = report.get("marketSnapshot", {}).get("shortTermRegime")
    if short_term:
        short_term_theme_health = 0
        avg_short = sum((theme.get("scoreBreakdown") or {}).get("shortImpulseScore", 0) for theme in trade_themes) / max(len(trade_themes), 1)
        if avg_short >= 80:
            short_term_theme_health += 10
        elif avg_short >= 70:
            short_term_theme_health += 5
        if breakdown_count <= 1:
            short_term_theme_health += 8
        elif breakdown_count <= 3:
            short_term_theme_health += 4
        short_term["scoreBreakdown"]["themeHealth"] = short_term_theme_health
        short_term["score"] = sum(short_term["scoreBreakdown"].values())
        short_term["stance"], short_term["mode"] = regime_band(short_term["score"])


def update_report_narrative(before_report: dict[str, Any], after_report: dict[str, Any]) -> None:
    monthly = after_report.get("marketSnapshot", {}).get("marketRegime", {})
    short_term = after_report.get("marketSnapshot", {}).get("shortTermRegime", {})
    before_themes = [theme["name"] for theme in before_report.get("themes") or []]
    after_themes = [theme["name"] for theme in after_report.get("themes") or []]
    before_picks = [stock["ticker"] for stock in before_report.get("topPicks") or []]
    after_picks = [stock["ticker"] for stock in after_report.get("topPicks") or []]
    theme_changed = before_themes != after_themes
    pick_changed = before_picks != after_picks
    report_date = str(after_report.get("reportDate") or "")
    if len(report_date) >= 10:
        short_date = f"{int(report_date[5:7])}/{int(report_date[8:10])}"
    else:
        short_date = report_date
    after_report["headline"] = (
        f"{short_date} 收盤 MOPS 驗證重算版：月內 Regime {monthly.get('score', 0)} 分 / {monthly.get('mode', '')}、"
        f"短線 Regime {short_term.get('score', 0)} 分 / {short_term.get('mode', '')}；"
        f"排序核心已改成 30 日公司事件與營收 / 財報加速，"
        f"{'前五主線與首頁主選股已重排' if (theme_changed or pick_changed) else '前五主線與首頁主選股不變'}。"
    )
    after_report["deck"] = (
        "這次不是新的價格日 rerun，而是把排序邏輯從 MOPS 三日高權重，改成研究校準後的 "
        "30 日 material company events / 營收財報加速 / 訂單認證 / 月內續航模型。"
        f" 重算後目前月內前五主線是：{'、'.join(after_themes)}。"
    )
    after_report["executiveSummary"] = [
        f"這版保留 {after_report.get('priceDate')} 的官方收盤與法人基準，但把核心排序邏輯改成 30 日公司事件與營收 / 財報加速研究校準版。",
        f"MOPS 內文重算後，月內 Regime 為 {monthly.get('score', 0)} / {monthly.get('mode', '')}，短線 Regime 為 {short_term.get('score', 0)} / {short_term.get('mode', '')}。",
        f"題材排序{'已改變' if theme_changed else '未改變'}；目前前五主線依序為：{'、'.join(after_themes)}。",
        f"首頁主選股{'已改變' if pick_changed else '未改變'}；目前六檔依序為：{'、'.join(after_picks)}。",
        "這次可見差異不再只來自最近三日 MOPS，而是 30 日公司層硬證據、營收 / 財報加速、訂單 / 認證與月內續航分數的重新定權。",
        "官方 U.S. macro 與 Hormuz 事件桶本輪沒有新增更晚輸入，所以這次改變主要來自排序引擎研究校準真正落地。",
    ]


def regime_band(score: int) -> tuple[str, str]:
    if score >= 75:
        return "強偏多", "risk_on"
    if score >= 60:
        return "偏多", "normal"
    if score >= 40:
        return "中性震盪", "selective"
    if score >= 25:
        return "偏空防守", "defensive"
    return "強偏空", "capital_preservation"


def build_new_discoveries(stock_info_map: dict[str, dict[str, Any]], ticker_name_map: dict[str, str], theme_lookup: dict[str, str]) -> list[dict[str, str]]:
    discoveries: list[dict[str, str]] = []
    priority = sorted(
        stock_info_map.items(),
        key=lambda kv: (
            kv[1]["material_score"],
            kv[1]["revenue_score"],
            sum(1 for item in kv[1]["raw_items_30d"] if item.direction in {"high_positive", "medium_positive"}),
        ),
        reverse=True,
    )
    for ticker, info in priority:
        items = [item for item in info["raw_items_30d"] if item.direction in {"high_positive", "medium_positive"}]
        if not items:
            continue
        item = items[0]
        discoveries.append(
            {
                "scope": theme_lookup.get(ticker, "MOPS"),
                "title": f"{ticker} {ticker_name_map.get(ticker, '')} {item.date} {item.title}",
                "detail": item.summary or item.title,
                "whyItMatters": "最近 30 日公司層事件已直接驗證並併入研究校準後的月內排序分數。",
            }
        )
        if len(discoveries) >= 3:
            break
    return discoveries


def write_log(
    before_report: dict[str, Any],
    after_report: dict[str, Any],
    window_dates: list[date],
    window_30d: list[date],
    stock_info_map: dict[str, dict[str, Any]],
) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = now_local().strftime("%Y-%m-%d_%H-%M-%S")
    path = LOG_DIR / f"{timestamp}.md"
    before_themes = [theme["name"] for theme in before_report.get("themes") or []]
    after_themes = [theme["name"] for theme in after_report.get("themes") or []]
    lines = [
        "# Research-Calibrated Scoring Migration Run",
        "",
        f"- Run timestamp: {now_local().isoformat()}",
        f"- Report date retained: {after_report.get('reportDate')}",
        f"- Price date retained: {after_report.get('priceDate')}",
        "- Scope: replace MOPS-3d-dominant scoring with research-calibrated 30-day company-event / revenue-earnings / order-qualification logic.",
        "",
        "## Window",
        "",
        "- MOPS 3-day window definition: recent 3 calendar days plus recent 3 Taiwan trading weekdays fallback.",
        f"- 3-day hybrid window dates used: {', '.join(iso_date_string(d) for d in window_dates)}",
        f"- 30-day company-event window used: {iso_date_string(window_30d[-1])} to {iso_date_string(window_30d[0])}",
        "- Official endpoints used:",
        "  - POST https://mops.twse.com.tw/mops/api/t05st01",
        "  - POST https://mops.twse.com.tw/mops/api/t05st01_detail",
        "",
        "## Theme Changes",
        "",
        f"- Before order: {' | '.join(before_themes)}",
        f"- After order: {' | '.join(after_themes)}",
        "",
        "## Major Stock Score Inputs",
        "",
    ]
    for ticker, info in sorted(stock_info_map.items(), key=lambda kv: kv[1]["score"], reverse=True)[:12]:
        lines.append(
            f"- {ticker}: mops3d {info['mops3d_score']}, material30d {info['material_score']}, revenue {info['revenue_score']}, order {info['order_score']}, attention {info['attention_score']}; {info['material_summary']}"
        )
    lines.extend(
        [
            "",
            "## Files Updated",
            "",
            f"- {LATEST_JSON}",
        ]
    )
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> None:
    report = load_json(LATEST_JSON)
    before = deepcopy(report)
    anchor = now_local().date()
    window_dates = hybrid_window(anchor)
    window_30d = recent_calendar_dates(anchor, 30)
    hybrid_set = {iso_date_string(d) for d in window_dates}

    ticker_name_map: dict[str, str] = {}
    theme_lookup: dict[str, str] = {}
    unique_stocks: dict[str, dict[str, Any]] = {}

    for theme in report.get("themes") or []:
        for stock in theme.get("stocks") or []:
            ticker_name_map[stock["ticker"]] = stock["name"]
            theme_lookup.setdefault(stock["ticker"], theme["name"])
            unique_stocks.setdefault(stock["ticker"], stock)
    for stock in report.get("observationStocks") or []:
        ticker_name_map[stock["ticker"]] = stock["name"]
        theme_lookup.setdefault(stock["ticker"], stock["theme"])
        unique_stocks.setdefault(stock["ticker"], stock)

    stock_info_map: dict[str, dict[str, Any]] = {}
    for ticker, stock_obj in unique_stocks.items():
        raw_items_30d = fetch_stock_mops_items(ticker, window_30d)
        raw_items_3d = [
            item for item in raw_items_30d if parse_roc_date(item.date) and iso_date_string(parse_roc_date(item.date)) in hybrid_set
        ]
        mops3d_score, mops3d_signal, mops3d_summary = stock_mops_score(raw_items_3d, window_dates)
        material_score, material_signal, material_summary = score_material_company_events_30d(raw_items_30d, anchor)
        procedural_score, procedural_signal, procedural_summary = score_procedural_mops_30d(raw_items_30d, anchor)
        revenue_score, revenue_summary = score_revenue_earnings_acceleration(stock_obj, raw_items_30d, anchor)
        order_score, order_summary = score_order_qualification(stock_obj, raw_items_30d, anchor)
        attention_score, attention_summary = score_attention(stock_obj, raw_items_30d)
        base_breakdown = stock_obj.get("scoreBreakdown") or {}
        draft_scores = {
            "materialCompanyEvent30dScore": material_score,
            "revenueEarningsAccelerationScore": revenue_score,
            "orderQualificationScore": order_score,
            "proceduralMopsScore": procedural_score,
            "attentionScore": attention_score,
            "shortImpulseScore": base_breakdown.get("shortImpulseScore", 0),
            "monthContinuationScore": base_breakdown.get("monthContinuationScore", 0),
        }
        speculation_flag = derive_speculation_flag(stock_obj, draft_scores)
        stock_info_map[ticker] = {
            "score": mops3d_score,
            "mops3d_score": mops3d_score,
            "mops3d_signal": mops3d_signal,
            "mops3d_summary": mops3d_summary,
            "mops3d_items": [
                {
                    "date": item.date,
                    "title": item.title,
                    "direction": item.direction,
                    "url": item.url,
                }
                for item in raw_items_3d
            ],
            "material_score": material_score,
            "material_signal": material_signal,
            "material_summary": material_summary,
            "procedural_score": procedural_score,
            "procedural_signal": procedural_signal,
            "procedural_summary": procedural_summary,
            "revenue_score": revenue_score,
            "revenue_summary": revenue_summary,
            "order_score": order_score,
            "order_summary": order_summary,
            "attention_score": attention_score,
            "attention_summary": attention_summary,
            "speculation_flag": speculation_flag,
            "raw_items": raw_items_3d,
            "raw_items_30d": raw_items_30d,
        }

    for theme in report.get("themes") or []:
        for stock in theme.get("stocks") or []:
            update_stock_obj(stock, stock_info_map[stock["ticker"]], window_dates)
        theme["stocks"].sort(key=lambda stock: (stock.get("stockScore", 0), stock["ticker"]), reverse=True)
        for idx, stock in enumerate(theme["stocks"], start=1):
            stock["rank"] = idx
        update_theme_obj(theme, theme["stocks"], window_dates)

    report["themes"].sort(key=lambda theme: (theme.get("themeScore", 0), theme["name"]), reverse=True)
    for idx, theme in enumerate(report["themes"], start=1):
        theme["rank"] = idx

    for stock in report.get("observationStocks") or []:
        update_stock_obj(stock, stock_info_map[stock["ticker"]], window_dates)
    report["observationStocks"].sort(key=lambda stock: (stock.get("stockScore", 0), stock["ticker"]), reverse=True)
    for idx, stock in enumerate(report["observationStocks"], start=1):
        stock["rank"] = idx
        if stock.get("speculationFlag") == "attention_without_company_evidence":
            stock["observationCategory"] = "speculation_only_watch"
        elif stock.get("scoreBreakdown", {}).get("materialCompanyEvent30dScore", 20) < 25 and stock.get("observationCategory") != "mops_negative_pressure":
            stock["observationCategory"] = "mops_insufficient_month_watch"
        elif stock.get("scoreBreakdown", {}).get("mops3dScore", 20) <= 15:
            stock["observationCategory"] = "mops_negative_pressure"

    obs_by_theme: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stock in report.get("observationStocks") or []:
        obs_by_theme[stock["theme"]].append(stock)
    for theme in report.get("observationThemes") or []:
        stocks = obs_by_theme.get(theme["name"], [])
        update_theme_obj(theme, stocks, window_dates)
    report["observationThemes"].sort(key=lambda theme: (theme.get("themeScore", 0), theme["name"]), reverse=True)
    for idx, theme in enumerate(report["observationThemes"], start=1):
        theme["rank"] = idx
        if theme.get("scoreBreakdown", {}).get("companyEvidenceSpreadScore", 20) < 35 and theme.get("scoreBreakdown", {}).get("shortImpulseScore", 0) >= 75:
            theme["observationCategory"] = "short_strong_month_insufficient"
        elif theme.get("scoreBreakdown", {}).get("externalDemandDeployment30dScore", 20) < 35 and theme.get("observationCategory") != "mops_negative_pressure":
            theme["observationCategory"] = "mops_insufficient_month_watch"
        elif theme.get("scoreBreakdown", {}).get("mops3dScore", 20) <= 15:
            theme["observationCategory"] = "mops_negative_pressure"

    existing_top_pick_map = {stock["ticker"]: stock for stock in report.get("topPicks") or []}
    top_pick_count = len(report.get("topPicks") or [])
    eligible_trade_stocks: list[tuple[str, dict[str, Any]]] = []
    for theme in report.get("themes") or []:
        for stock in theme.get("stocks") or []:
            signal = stock.get("mops3dSignal", "")
            if signal in {"high_negative", "medium_negative"} and stock.get("scoreBreakdown", {}).get("mops3dScore", 20) <= 15:
                continue
            if stock.get("speculationFlag") == "attention_without_company_evidence":
                continue
            eligible_trade_stocks.append((theme["name"], stock))
    eligible_trade_stocks.sort(key=lambda pair: (pair[1].get("stockScore", 0), pair[1]["ticker"]), reverse=True)
    report["topPicks"] = [make_top_pick(stock, theme_name, existing_top_pick_map) for theme_name, stock in eligible_trade_stocks[:top_pick_count]]
    for idx, stock in enumerate(report["topPicks"], start=1):
        stock["rank"] = idx

    recalc_market_regime(report)

    report["newDiscoveries"] = build_new_discoveries(stock_info_map, ticker_name_map, theme_lookup)

    sources = report.get("sources") or []
    sources = [src for src in sources if "MOPS" not in (src.get("label") or "")]
    sources.append(
        {
            "label": "MOPS 歷史重大訊息 / 明細 API（30日公司事件校準版）",
            "url": "https://mops.twse.com.tw/mops/#/web/t05st01",
            "note": "本版直接用官方 t05st01 / t05st01_detail 抽取近 30 日公司事件與近三日 MOPS，重算研究校準版分數。",
        }
    )
    report["sources"] = sources

    footnote = report.get("footnote", "")
    footnote = footnote.replace(
        "本版另外已把 MOPS 最近三日重大訊息納入題材與個股的最高權重分項；但官方近三日查詢頁在目前環境未能直接驗證，所以當前網站先用 provisional baseline 顯示，待下一次可驗證晨報覆蓋。",
        "",
    )
    footnote = footnote.replace("  ", " ").strip()
    footnote = re.sub(
        r"(本版已以官方 MOPS t05st01 / t05st01_detail 直接驗證最近三日重大訊息與內文，不再使用 provisional baseline。\s*)+",
        "",
        footnote,
    ).strip()
    report["footnote"] = (
        footnote
        + " 本版已把排序邏輯改成 30 日 material company events、營收 / 財報加速、訂單 / 認證與月內續航研究校準版；近三日 MOPS 只保留為輔助訊號。"
    ).strip()

    cp = report.get("changesComparedToPrevious") or {}
    cp["summary"] = "這次把題材與個股排序從 MOPS 三日高權重，改成研究校準後的 30 日公司事件 / 營收財報加速 / 月內續航模型。"
    cp_items = [
        {
            "title": "個股主排序改成 30 日公司事件與營收 / 財報加速",
            "reason": "最高權重不再是單一 mops3dScore，而是 30 日 material company events + 營收 / 財報加速，近三日 MOPS 改成輔助訊號。",
        },
        {
            "title": "題材主排序改成外需部署 / 產業價格 / 公司證據擴散",
            "reason": "題材層不再被單一 MOPS 分數主導，而是以 30 日外需部署證據、價格 / shortage 訊號與台股公司層證據擴散重算。",
        },
        {
            "title": "純注意力 / 程序性公告不再足以推進交易池",
            "reason": "研究校準後，純法說 / 券商 / 程序性 MOPS 只能做低權重加分；缺少公司層硬證據的名字會被壓回觀察池。",
        },
    ]
    cp["items"] = cp_items
    report["changesComparedToPrevious"] = cp

    update_report_narrative(before, report)

    save_json(LATEST_JSON, report)
    log_path = write_log(before, report, window_dates, window_30d, stock_info_map)
    print(str(log_path))


if __name__ == "__main__":
    main()
