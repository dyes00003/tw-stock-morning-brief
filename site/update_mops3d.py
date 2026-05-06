#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path("/Users/huangyuxuan/Documents/New project")
LATEST_JSON = ROOT / "site" / "data" / "latest.json"
LOG_DIR = ROOT / "logs" / "tw-stock-morning-brief"
MOPS_API_BASE = "https://mops.twse.com.tw/mops/api"
TZ = ZoneInfo("Asia/Taipei")


def now_local() -> datetime:
    return datetime.now(TZ)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
            detail = post_json(f"{MOPS_API_BASE}/{api_name}", params)
            items.append(build_mops_item(detail, row, api_name, params))
    items.sort(key=lambda item: (item.date, item.time, item.title))
    return items


def stock_mops_score(items: list[MopsItem], window_dates: list[date]) -> tuple[int, str, str]:
    if not items:
        return 20, "no_recent_mops_material_info_verified", "最近三日未查到官方 MOPS 重大訊息。"

    latest_window_dates = {roc_date_string(window_dates[0])}
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
    return round(
        (breakdown.get("mops3dScore") or 0) * 0.40
        + (breakdown.get("monthContinuationScore") or 0) * 0.35
        + (breakdown.get("shortImpulseScore") or 0) * 0.25
    )


def recompute_theme_score(theme: dict[str, Any]) -> int:
    breakdown = theme.get("scoreBreakdown") or {}
    return round(
        (breakdown.get("mops3dScore") or 0) * 0.40
        + (breakdown.get("monthContinuationScore") or 0) * 0.35
        + (breakdown.get("shortImpulseScore") or 0) * 0.25
    )


def build_stock_texts(stock: dict[str, Any], signal: str, summary: str) -> None:
    if signal == "no_recent_mops_material_info_verified":
        lead = "最近三日 MOPS 沒有新增重大訊息，月內第二段行情仍主要仰賴既有催化與量價續航。"
        invalidation = "若接下來月內沒有新的 MOPS / 法說 / 財報節點承接，這筆月內續航 setup 會先失效。"
    elif signal in {"high_positive", "medium_positive"}:
        lead = f"最近三日 MOPS 顯示 {summary.rstrip('。')}，支持月內第二段行情延續。"
        invalidation = "若後續 MOPS / 法說進度無法延續，或最新重訊只剩程序性公告，這筆月內續航 setup 會轉弱。"
    elif signal in {"medium_negative", "high_negative"}:
        lead = f"最近三日 MOPS 出現負面壓力：{summary.rstrip('。')}，月內第二段行情需要重新驗證。"
        invalidation = "若後續沒有新的正面 MOPS 抵消這個負面訊號，這筆月內續航 setup 視為失效。"
    else:
        lead = f"最近三日 MOPS 有訊號但方向有限：{summary.rstrip('。')}，仍需後續事件確認。"
        invalidation = "若後續 MOPS 仍無法明確偏向正面，這筆月內續航 setup 會失去優勢。"

    stock["notPricedIn"] = lead + " " + strip_mops_prefix(stock.get("notPricedIn", ""))
    stock["targetLogic"] = lead + " " + strip_mops_prefix(stock.get("targetLogic", ""))
    stock["invalidationTrigger"] = invalidation


def update_stock_obj(stock: dict[str, Any], info: dict[str, Any], window_dates: list[date]) -> None:
    breakdown = stock.setdefault("scoreBreakdown", {})
    breakdown["mops3dScore"] = info["score"]
    stock["mops3dSignal"] = info["signal"]
    stock["mops3dSummary"] = info["summary"]
    stock["mops3dItems"] = info["items"]
    stock.setdefault("gateStatus", {})["mops3d"] = summarize_gate_mops(info["score"], info["signal"])
    stock["stockScore"] = recompute_stock_score(stock)
    build_stock_texts(stock, info["signal"], info["summary"])


def update_theme_obj(theme: dict[str, Any], stock_infos: list[dict[str, Any]], window_dates: list[date]) -> None:
    score, breadth, summary = theme_mops_score(stock_infos, (theme.get("gateStatus") or {}).get("secondLegEvidence", ""))
    theme.setdefault("scoreBreakdown", {})["mops3dScore"] = score
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
        f"官方 MOPS 近三日內文已納入最高權重分項，"
        f"{'前五主線與首頁主選股已重排' if (theme_changed or pick_changed) else '前五主線與首頁主選股不變'}。"
    )
    after_report["deck"] = (
        "這次不是新的價格日 rerun，而是把最近三日官方 MOPS 重大訊息從 provisional baseline 改成直接抓取 "
        "t05st01 / t05st01_detail 內文後重算。"
        f" 重算後目前月內前五主線是：{'、'.join(after_themes)}。"
    )
    after_report["executiveSummary"] = [
        f"這版保留 {after_report.get('priceDate')} 的官方收盤與法人基準，但把最近三日官方 MOPS 重大訊息改成直接抓內文驗證。",
        f"MOPS 內文重算後，月內 Regime 為 {monthly.get('score', 0)} / {monthly.get('mode', '')}，短線 Regime 為 {short_term.get('score', 0)} / {short_term.get('mode', '')}。",
        f"題材排序{'已改變' if theme_changed else '未改變'}；目前前五主線依序為：{'、'.join(after_themes)}。",
        f"首頁主選股{'已改變' if pick_changed else '未改變'}；目前六檔依序為：{'、'.join(after_picks)}。",
        "這次可見差異不再來自 provisional baseline，而是每檔股票最近三日官方 MOPS 重大訊息本身的方向、廣度與內文內容。",
        "官方 U.S. macro 與 Hormuz 事件桶本輪沒有新增更晚輸入，所以這次改變主要來自 MOPS 三日權重真正落地。",
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
            kv[1]["score"],
            sum(1 for item in kv[1]["raw_items"] if item.direction in {"high_positive", "medium_positive"}),
        ),
        reverse=True,
    )
    for ticker, info in priority:
        items = [item for item in info["raw_items"] if item.direction in {"high_positive", "medium_positive"}]
        if not items:
            continue
        item = items[0]
        discoveries.append(
            {
                "scope": theme_lookup.get(ticker, "MOPS"),
                "title": f"{ticker} {ticker_name_map.get(ticker, '')} {item.date} {item.title}",
                "detail": item.summary or item.title,
                "whyItMatters": "最近三日官方 MOPS 重大訊息已直接驗證並併入月內排序分數。",
            }
        )
        if len(discoveries) >= 3:
            break
    return discoveries


def write_log(
    before_report: dict[str, Any],
    after_report: dict[str, Any],
    window_dates: list[date],
    stock_info_map: dict[str, dict[str, Any]],
) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = now_local().strftime("%Y-%m-%d_%H-%M-%S")
    path = LOG_DIR / f"{timestamp}.md"
    before_themes = [theme["name"] for theme in before_report.get("themes") or []]
    after_themes = [theme["name"] for theme in after_report.get("themes") or []]
    lines = [
        "# MOPS 3-Day Official Verification Run",
        "",
        f"- Run timestamp: {now_local().isoformat()}",
        f"- Report date retained: {after_report.get('reportDate')}",
        f"- Price date retained: {after_report.get('priceDate')}",
        "- Scope: replace provisional MOPS baseline with verified official MOPS history + detail content.",
        "",
        "## Window",
        "",
        "- MOPS 3-day window definition: recent 3 calendar days plus recent 3 Taiwan trading weekdays fallback.",
        f"- Window dates used: {', '.join(iso_date_string(d) for d in window_dates)}",
        "- Official endpoints verified:",
        "  - POST https://mops.twse.com.tw/mops/api/t05st01",
        "  - POST https://mops.twse.com.tw/mops/api/t05st01_detail",
        "",
        "## Theme Changes",
        "",
        f"- Before order: {' | '.join(before_themes)}",
        f"- After order: {' | '.join(after_themes)}",
        "",
        "## Major Stock MOPS Scores",
        "",
    ]
    for ticker, info in sorted(stock_info_map.items(), key=lambda kv: kv[1]["score"], reverse=True)[:12]:
        lines.append(
            f"- {ticker}: mops3dScore {info['score']}, signal {info['signal']}, items {len(info['raw_items'])}; {info['summary']}"
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
    for ticker in unique_stocks:
        raw_items = fetch_stock_mops_items(ticker, window_dates)
        score, signal, summary = stock_mops_score(raw_items, window_dates)
        stock_info_map[ticker] = {
            "score": score,
            "signal": signal,
            "summary": summary,
            "items": [
                {
                    "date": item.date,
                    "title": item.title,
                    "direction": item.direction,
                    "url": item.url,
                }
                for item in raw_items
            ],
            "raw_items": raw_items,
        }

    for theme in report.get("themes") or []:
        for stock in theme.get("stocks") or []:
            update_stock_obj(stock, stock_info_map[stock["ticker"]], window_dates)
        theme["stocks"].sort(key=lambda stock: (stock.get("stockScore", 0), stock["ticker"]), reverse=True)
        for idx, stock in enumerate(theme["stocks"], start=1):
            stock["rank"] = idx
        theme_stock_infos = [
            {
                "ticker": stock["ticker"],
                "mops3dScore": stock.get("scoreBreakdown", {}).get("mops3dScore", 20),
            }
            for stock in theme["stocks"]
        ]
        update_theme_obj(theme, theme_stock_infos, window_dates)

    report["themes"].sort(key=lambda theme: (theme.get("themeScore", 0), theme["name"]), reverse=True)
    for idx, theme in enumerate(report["themes"], start=1):
        theme["rank"] = idx

    for stock in report.get("observationStocks") or []:
        update_stock_obj(stock, stock_info_map[stock["ticker"]], window_dates)
    report["observationStocks"].sort(key=lambda stock: (stock.get("stockScore", 0), stock["ticker"]), reverse=True)
    for idx, stock in enumerate(report["observationStocks"], start=1):
        stock["rank"] = idx
        if stock.get("scoreBreakdown", {}).get("mops3dScore", 20) < 25 and stock.get("observationCategory") != "mops_negative_pressure":
            stock["observationCategory"] = "mops_insufficient_month_watch"
        elif stock.get("scoreBreakdown", {}).get("mops3dScore", 20) <= 15:
            stock["observationCategory"] = "mops_negative_pressure"

    obs_by_theme: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stock in report.get("observationStocks") or []:
        obs_by_theme[stock["theme"]].append(stock)
    for theme in report.get("observationThemes") or []:
        stocks = obs_by_theme.get(theme["name"], [])
        theme_stock_infos = [
            {
                "ticker": stock["ticker"],
                "mops3dScore": stock.get("scoreBreakdown", {}).get("mops3dScore", 20),
            }
            for stock in stocks
        ] or [{"ticker": "", "mops3dScore": 20}]
        update_theme_obj(theme, theme_stock_infos, window_dates)
    report["observationThemes"].sort(key=lambda theme: (theme.get("themeScore", 0), theme["name"]), reverse=True)
    for idx, theme in enumerate(report["observationThemes"], start=1):
        theme["rank"] = idx
        if theme.get("scoreBreakdown", {}).get("mops3dScore", 20) < 25 and theme.get("observationCategory") != "mops_negative_pressure":
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
            "label": "MOPS 歷史重大訊息 / 明細 API（2026-05-06 驗證）",
            "url": "https://mops.twse.com.tw/mops/#/web/t05st01",
            "note": "本版已直接用官方 t05st01 / t05st01_detail 近三日重大訊息與內文重算 mops3dScore。",
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
        footnote + " 本版已以官方 MOPS t05st01 / t05st01_detail 直接驗證最近三日重大訊息與內文，不再使用 provisional baseline。"
    ).strip()

    cp = report.get("changesComparedToPrevious") or {}
    cp["summary"] = "這次把 MOPS 最近三日重大訊息從 provisional baseline 改成官方內文驗證，並依新分數重算目前網站上的題材與個股排序。"
    cp_items = [
        {
            "title": "MOPS 三日重大訊息已改用官方內文驗證",
            "reason": "現在直接用 MOPS t05st01 / t05st01_detail 抓公司近三日重大訊息與內文，不再只顯示 provisional baseline。",
        },
        {
            "title": "題材與個股 mops3dScore 已改成真實分數",
            "reason": "每檔股票都以最近三日官方重大訊息重算 mops3dScore，題材則依 constituent breadth 重新計算。",
        },
        {
            "title": "首頁主選股與題材排序已按真實 MOPS 權重重排",
            "reason": "這次不是新的價格日 rerun，但可見排序已按真實 MOPS 權重重算，而不是沿用 baseline 20 / 23 分。",
        },
    ]
    cp["items"] = cp_items
    report["changesComparedToPrevious"] = cp

    update_report_narrative(before, report)

    save_json(LATEST_JSON, report)
    log_path = write_log(before, report, window_dates, stock_info_map)
    print(str(log_path))


if __name__ == "__main__":
    main()
