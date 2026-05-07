#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path("/Users/huangyuxuan/Documents/New project")
SITE_DIR = ROOT / "site"
LATEST_JSON = SITE_DIR / "data" / "latest.json"
SUPPLY_CHAIN_JSON = SITE_DIR / "data" / "tw_stock_supply_chain_tags.json"
LOG_DIR = ROOT / "logs" / "tw-stock-morning-brief"
TZ = ZoneInfo("Asia/Taipei")


def now_local() -> datetime:
    return datetime.now(TZ)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text).replace("\r", " ").replace("\n", " ")).strip()


def num(value: Any) -> float:
    raw = clean_text(str(value))
    if raw in {"", "--", "---", "----", "除權息", "X", "不適用"}:
        return 0.0
    raw = raw.replace(",", "")
    raw = raw.replace("元", "")
    raw = raw.replace("%", "")
    raw = raw.replace("＋", "+").replace("－", "-")
    if raw.startswith("<p"):
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def signed_change(sign_html: str, change_value: Any) -> float:
    change = num(change_value)
    sign = clean_text(sign_html)
    if "green" in sign or "-" in sign:
        return -abs(change)
    if "red" in sign or "+" in sign:
        return abs(change)
    return change


def safe_pct_change(close_value: float, delta_value: float) -> float:
    prev = close_value - delta_value
    if prev <= 0:
        return 0.0
    return delta_value / prev * 100


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clamp_int(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))


def parse_roc_date(value: str) -> date | None:
    raw = clean_text(value).replace("-", "/")
    if not raw:
        return None
    try:
        if "/" in raw:
            y, m, d = raw.split("/")
            return date(int(y) + 1911, int(m), int(d))
        if len(raw) == 7:
            return date(int(raw[:3]) + 1911, int(raw[3:5]), int(raw[5:7]))
    except Exception:
        return None
    return None


def iso(d: date) -> str:
    return d.isoformat()


def request_json(url: str) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def try_request_json(url: str) -> dict[str, Any] | None:
    try:
        return request_json(url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None


def load_update_helpers() -> dict[str, Any]:
    module_path = SITE_DIR / "update_mops3d.py"
    spec = importlib.util.spec_from_file_location("update_mops3d_helpers", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load helper module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.__dict__


HELPERS = load_update_helpers()


THEME_DEFS = [
    {
        "name": "記憶體 / DRAM / NAND 價格重估",
        "family": "半導體製造",
        "comparable": "HBM4 / AI ASIC IP / 台積電 3DFabric 生態系",
        "separateReason": "主驅動是記憶體報價、供需與庫存重估，不是先進封裝或 ASIC 估值擴張。",
        "keywords": ["記憶體", "DRAM", "NAND", "NOR", "SSD控制器", "NAND控制IC"],
        "policy": "台灣政策直接支持有限；但 AI 伺服器與企業儲存需求變化會直接反映在本題材。",
    },
    {
        "name": "HBM4 / AI ASIC IP / 台積電 3DFabric 生態系",
        "family": "半導體製造",
        "comparable": "CoWoS / 先進封裝設備",
        "separateReason": "主驅動來自 ASIC / IP / HBM4 與 3DFabric 的設計與封裝價值，不等同設備交期交易。",
        "keywords": ["ASIC", "矽智財IP", "LPU", "HBM", "3DIC聯盟", "CoWoS", "先進封裝", "IC 設計", "IC設計服務"],
        "policy": "台灣高階製程與封裝供應鏈具結構優勢，政策面偏正向但真正催化仍是客戶平台與產品週期。",
    },
    {
        "name": "高階 CCL / AI PCB / 高層數板",
        "family": "電子材料與板材",
        "comparable": "AI 高速互連線 / 大電流電源線",
        "separateReason": "核心在高速材料、板材層數與損耗規格升級，不等同線材或連接器本體。",
        "keywords": ["CCL", "高速CCL", "Low Dk", "Low Loss", "PCB", "銅箔基板", "網通板", "伺服器板", "高階 PCB", "高層數"],
        "policy": "政策直接影響有限；主要還是 AI 資料中心升級對板材規格的需求推動。",
    },
    {
        "name": "AI 高速互連線 / 大電流電源線",
        "family": "AI 基建",
        "comparable": "伺服器電源 / BBU",
        "separateReason": "主交易點是高速互連、電流提升與線材/連接器規格升級，不等同電源模組本體。",
        "keywords": ["連接器", "線材", "電子連接相關", "高速介面", "軸承 / 滑軌", "折疊機 / 伺服器機構", "PCB / 電源 / 被動元件 / 連接器"],
        "policy": "政策支援有限；外部驅動主要來自資料中心架構升級與機櫃內配線規格提升。",
    },
    {
        "name": "光模組 / 矽光子",
        "family": "AI 基建",
        "comparable": "AI 交換器 / 資料中心網通設備",
        "separateReason": "主交易點是 800G/1.6T、矽光子與資料中心互連，不等同整機交換器出貨。",
        "keywords": ["光通訊", "光模組", "矽光子", "800G / 1.6T", "資料中心互連", "高速傳輸"],
        "policy": "政策面中性；真正主驅動來自 hyperscaler 與資料中心光互連升級節奏。",
    },
    {
        "name": "伺服器電源 / BBU",
        "family": "AI 基建",
        "comparable": "AI 高速互連線 / 大電流電源線",
        "separateReason": "主交易點是 BBU / UPS / 備援電源與資料中心供電，與線材/互連升級不同。",
        "keywords": ["電源", "BBU", "UPS", "備援電源", "資料中心電力", "工業電源", "電源供應器"],
        "policy": "若資料中心電力基建與企業資本支出延續，本題材可維持月內交易性。",
    },
    {
        "name": "AI 交換器 / 資料中心網通設備",
        "family": "AI 基建",
        "comparable": "光模組 / 矽光子",
        "separateReason": "主交易點是交換器整機 / 網通設備出貨，而不是單純光模組規格升級。",
        "keywords": ["交換器", "路由器", "資料中心網路", "網通", "企業網路", "交換器 / CPE / 網通設備"],
        "policy": "政策面中性；主要依賴 hyperscaler 內網升級與資料中心建置。",
    },
    {
        "name": "CoWoS / 先進封裝設備",
        "family": "半導體製造",
        "comparable": "HBM4 / AI ASIC IP / 台積電 3DFabric 生態系",
        "separateReason": "主交易點在設備交期與擴產節點，不等於 ASIC / IP 的設計價值重估。",
        "keywords": ["先進封裝", "CoWoS", "半導體設備", "檢測", "測試"],
        "policy": "台灣半導體設備與封裝擴產具政策與產業雙支持，但節奏通常比設計股慢。",
    },
    {
        "name": "重電 / 電網 / 配電",
        "family": "電力基建",
        "comparable": "伺服器電源 / BBU",
        "separateReason": "主交易點是電網、重電與配電設備，不等同資料中心內部 BBU / UPS。",
        "keywords": ["變壓器", "配電", "儲能", "重電", "電網", "switchgear", "資料中心電力"],
        "policy": "政策與公用事業投資可能是核心支撐，但若沒有公司層新證據，短線容易落回觀察。",
    },
    {
        "name": "AI 伺服器 ODM / 機櫃 / 機殼",
        "family": "AI 基建",
        "comparable": "伺服器電源 / BBU",
        "separateReason": "主交易點是整機、機構件與機櫃受惠，不等同單一電源模組或線材零件。",
        "keywords": ["伺服器", "機櫃", "機殼", "ODM", "AI 伺服器", "AWS", "GB200", "GB300"],
        "policy": "政策面中性；月內是否能交易主要看客戶平台切換與出貨節奏。",
    },
]


@dataclass
class PriceRow:
    ticker: str
    name: str
    market: str
    close: float
    open: float
    high: float
    low: float
    change: float
    change_pct: float
    volume: float
    amount: float
    pe: str
    institution_net: float
    foreign_net: float


@dataclass
class HistoryPoint:
    date: date
    close: float
    volume: float
    amount: float


def weekday_report_date(today: date) -> tuple[date, date]:
    report_date = today
    anchor = today - timedelta(days=1)
    return report_date, anchor


def fetch_latest_twse_bundle(anchor: date) -> tuple[date, dict[str, Any]]:
    cursor = anchor
    for _ in range(14):
        day = cursor.strftime("%Y%m%d")
        payload = try_request_json(f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={day}&type=ALLBUT0999")
        if payload and payload.get("stat") == "OK" and payload.get("tables"):
            return cursor, payload
        cursor -= timedelta(days=1)
    raise RuntimeError("Unable to find latest official TWSE trading date")


def fetch_tpex_bundle(price_date: date) -> dict[str, Any]:
    return request_json(
        f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={price_date:%Y/%m/%d}&response=json"
    )


def fetch_twse_t86(price_date: date) -> dict[str, Any]:
    return request_json(
        f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={price_date:%Y%m%d}&selectType=ALLBUT0999"
    )


def fetch_twse_bfi82u(price_date: date) -> dict[str, Any]:
    return request_json(
        f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json&dayDate={price_date:%Y%m%d}&type=day"
    )


def fetch_tpex_insti(price_date: date) -> dict[str, Any]:
    return request_json(
        f"https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?date={price_date:%Y/%m/%d}&type=Daily&response=json"
    )


def parse_twse_market(bundle: dict[str, Any]) -> tuple[dict[str, PriceRow], dict[str, Any]]:
    market: dict[str, PriceRow] = {}
    tables = bundle["tables"]
    quote_table = tables[8]
    fields = quote_table["fields"]
    idx = {field: i for i, field in enumerate(fields)}
    for row in quote_table["data"]:
        code = clean_text(row[idx["證券代號"]])
        if not (code.isdigit() and len(code) == 4 and not code.startswith("0")):
            continue
        close = num(row[idx["收盤價"]])
        change = signed_change(row[idx["漲跌(+/-)"]], row[idx["漲跌價差"]])
        market[code] = PriceRow(
            ticker=code,
            name=clean_text(row[idx["證券名稱"]]),
            market="TWSE",
            close=close,
            open=num(row[idx["開盤價"]]),
            high=num(row[idx["最高價"]]),
            low=num(row[idx["最低價"]]),
            change=change,
            change_pct=safe_pct_change(close, change),
            volume=num(row[idx["成交股數"]]),
            amount=num(row[idx["成交金額"]]),
            pe=clean_text(row[idx["本益比"]]),
            institution_net=0.0,
            foreign_net=0.0,
        )

    weighted_row = next(
        row for row in tables[0]["data"] if clean_text(row[0]) == "發行量加權股價指數"
    )
    index_close = num(weighted_row[1])
    index_delta = signed_change(weighted_row[2], weighted_row[3])
    return market, {
        "indexClose": index_close,
        "indexChangePct": num(weighted_row[4]),
        "indexDelta": index_delta,
    }


def parse_tpex_market(bundle: dict[str, Any]) -> dict[str, PriceRow]:
    market: dict[str, PriceRow] = {}
    quote_table = bundle["tables"][0]
    fields = quote_table["fields"]
    idx = {field: i for i, field in enumerate(fields)}
    for row in quote_table["data"]:
        code = clean_text(row[idx["代號"]])
        if not (code.isdigit() and len(code) == 4 and not code.startswith("0")):
            continue
        close = num(row[idx["收盤"]])
        change = num(row[idx["漲跌"]])
        market[code] = PriceRow(
            ticker=code,
            name=clean_text(row[idx["名稱"]]),
            market="TPEX",
            close=close,
            open=num(row[idx["開盤"]]),
            high=num(row[idx["最高"]]),
            low=num(row[idx["最低"]]),
            change=change,
            change_pct=safe_pct_change(close, change),
            volume=num(row[idx["成交股數"]]),
            amount=num(row[idx["成交金額(元)"]]),
            pe="無法驗證",
            institution_net=0.0,
            foreign_net=0.0,
        )
    return market


def parse_twse_t86_flows(bundle: dict[str, Any]) -> dict[str, tuple[float, float]]:
    fields = bundle["fields"]
    idx = {field: i for i, field in enumerate(fields)}
    out: dict[str, tuple[float, float]] = {}
    for row in bundle["data"]:
        code = clean_text(row[idx["證券代號"]])
        if not (code.isdigit() and len(code) == 4):
            continue
        foreign_net = num(row[idx["外陸資買賣超股數(不含外資自營商)"]])
        inst_net = num(row[idx["三大法人買賣超股數"]])
        out[code] = (foreign_net, inst_net)
    return out


def parse_tpex_insti_flows(bundle: dict[str, Any]) -> dict[str, tuple[float, float]]:
    table = bundle["tables"][0]
    out: dict[str, tuple[float, float]] = {}
    for row in table["data"]:
        code = clean_text(row[0])
        if not (code.isdigit() and len(code) == 4):
            continue
        inst_net = num(row[-1])
        foreign_net = num(row[4]) if len(row) > 4 else 0.0
        out[code] = (foreign_net, inst_net)
    return out


def parse_foreign_flow_twd_bn(bundle: dict[str, Any]) -> float:
    for row in bundle["data"]:
        if clean_text(row[0]) == "外資及陸資(不含外資自營商)":
            return round(num(row[3]) / 1_000_000_000, 2)
    return 0.0


def month_starts(end_date: date, months_back: int = 3) -> list[date]:
    starts = []
    cursor = end_date.replace(day=1)
    for _ in range(months_back):
        starts.append(cursor)
        if cursor.month == 1:
            cursor = cursor.replace(year=cursor.year - 1, month=12)
        else:
            cursor = cursor.replace(month=cursor.month - 1)
    return starts


def fetch_twse_history(ticker: str, end_date: date, max_points: int = 25) -> list[HistoryPoint]:
    points: list[HistoryPoint] = []
    for month_start in month_starts(end_date, 3):
        bundle = try_request_json(
            f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={month_start:%Y%m01}&stockNo={ticker}"
        )
        if not bundle or bundle.get("stat") != "OK":
            continue
        fields = bundle["fields"]
        idx = {field: i for i, field in enumerate(fields)}
        for row in bundle["data"]:
            d = parse_roc_date(row[idx["日期"]])
            if not d or d > end_date:
                continue
            points.append(
                HistoryPoint(
                    date=d,
                    close=num(row[idx["收盤價"]]),
                    volume=num(row[idx["成交股數"]]),
                    amount=num(row[idx["成交金額"]]),
                )
            )
    dedup = {point.date: point for point in points}
    ordered = sorted(dedup.values(), key=lambda x: x.date)
    return ordered[-max_points:]


def fetch_tpex_history(ticker: str, end_date: date, max_points: int = 25) -> list[HistoryPoint]:
    points: list[HistoryPoint] = []
    for month_start in month_starts(end_date, 3):
        bundle = try_request_json(
            f"https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?code={ticker}&date={month_start:%Y/%m/01}&response=json"
        )
        if not bundle or bundle.get("stat") != "ok":
            continue
        tables = bundle.get("tables") or []
        if not tables:
            continue
        fields = tables[0]["fields"]
        idx = {field: i for i, field in enumerate(fields)}
        for row in tables[0]["data"]:
            d = parse_roc_date(row[idx["日 期"]])
            if not d or d > end_date:
                continue
            points.append(
                HistoryPoint(
                    date=d,
                    close=num(row[idx["收盤"]]),
                    volume=num(row[idx["成交張數"]]) * 1000,
                    amount=num(row[idx["成交仟元"]]) * 1000,
                )
            )
    dedup = {point.date: point for point in points}
    ordered = sorted(dedup.values(), key=lambda x: x.date)
    return ordered[-max_points:]


def recent_trading_dates(end_date: date, count: int = 20) -> list[date]:
    dates: list[date] = []
    cursor = end_date
    while len(dates) < count:
        bundle = try_request_json(
            f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={cursor:%Y%m%d}&type=ALLBUT0999"
        )
        if bundle and bundle.get("stat") == "OK" and bundle.get("tables"):
            dates.append(cursor)
        cursor -= timedelta(days=1)
    return sorted(dates)


def fetch_index_history(trading_dates: list[date]) -> list[tuple[date, float]]:
    out: list[tuple[date, float]] = []
    for d in trading_dates:
        bundle = try_request_json(
            f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={d:%Y%m%d}&type=ALLBUT0999"
        )
        if not bundle or bundle.get("stat") != "OK" or not bundle.get("tables"):
            continue
        row = next(row for row in bundle["tables"][0]["data"] if clean_text(row[0]) == "發行量加權股價指數")
        out.append((d, num(row[1])))
    if not out:
        raise RuntimeError("Unable to rebuild TAIEX history from official MI_INDEX data")
    return out


def lookup_return(points: list[HistoryPoint], window: int) -> float:
    if len(points) <= window:
        return 0.0
    latest = points[-1].close
    base = points[-(window + 1)].close
    if base <= 0:
        return 0.0
    return (latest / base - 1) * 100


def volume_ratio(points: list[HistoryPoint]) -> float:
    if len(points) < 6:
        return 1.0
    latest = points[-1].amount
    trailing = sorted(point.amount for point in points[:-1])
    median = trailing[len(trailing) // 2] if trailing else latest
    if median <= 0:
        return 1.0
    return latest / median


def amount_median(points: list[HistoryPoint]) -> float:
    values = sorted(point.amount for point in points)
    if not values:
        return 0.0
    return values[len(values) // 2]


def relative_strength(stock_return: float, index_return: float) -> float:
    return round(stock_return - index_return, 2)


def combined_text(meta: dict[str, Any]) -> str:
    parts: list[str] = [
        meta.get("theme", ""),
        meta.get("supplyChainRole", ""),
        meta.get("chainPosition", ""),
        " ".join(meta.get("tags") or []),
        " ".join(meta.get("verifiedThemes") or []),
        " ".join(meta.get("endMarkets") or []),
        " ".join(meta.get("upstream") or []),
        " ".join(meta.get("downstream") or []),
    ]
    return clean_text(" ".join(parts))


def match_theme(meta: dict[str, Any], theme_def: dict[str, Any]) -> bool:
    blob = combined_text(meta)
    return any(keyword.lower() in blob.lower() for keyword in theme_def["keywords"])


def liquidity_bucket(amount_value: float) -> int:
    if amount_value >= 3_000_000_000:
        return 100
    if amount_value >= 1_500_000_000:
        return 85
    if amount_value >= 800_000_000:
        return 70
    if amount_value >= 300_000_000:
        return 55
    if amount_value >= 100_000_000:
        return 40
    return 20


def score_calendar(material: int, revenue: int, order: int) -> int:
    strong = sum(score >= 70 for score in (material, revenue, order))
    medium = sum(score >= 55 for score in (material, revenue, order))
    if strong >= 2:
        return 25
    if strong == 1 and medium >= 2:
        return 18
    if strong == 1:
        return 10
    if medium >= 2:
        return 8
    return 0


def score_second_leg(material: int, revenue: int, order: int, mops3d: int, rs20: float) -> int:
    strong = sum(score >= 70 for score in (material, revenue, order))
    medium = sum(score >= 55 for score in (material, revenue, order))
    score = 0
    if strong >= 2:
        score = 18
    elif strong == 1 and medium >= 2:
        score = 14
    elif strong == 1:
        score = 10
    elif medium >= 2:
        score = 8
    else:
        score = 4
    if mops3d >= 65:
        score += 2
    if rs20 > 0:
        score += 2
    return clamp_int(score, 0, 20)


def score_short_impulse(rs1: float, rs3: float, rs5: float, vol_ratio: float, inst_net: float, mops3d: int) -> int:
    score = 0.0
    score += clamp(rs1, -5, 8) * 3
    score += clamp(rs3, -8, 12) * 2
    score += clamp(rs5, -10, 15) * 1.5
    score += min(max((vol_ratio - 1.0) * 20, 0), 20)
    if inst_net > 0:
        score += 10
    if mops3d >= 65:
        score += 10
    return clamp_int(score, 0, 100)


def score_month_continuation(
    calendar_score: int,
    second_leg_score: int,
    rs5: float,
    rs10: float,
    rs20: float,
    material: int,
    revenue: int,
    order: int,
    liquidity: int,
) -> int:
    persistence_component = clamp(max(rs5, 0) * 1.2 + max(rs10, 0) * 1.0 + max(rs20, 0) * 0.8, 0, 25)
    evidence_component = max(material, revenue, order) * 0.2
    blended = (
        calendar_score * 2.0
        + second_leg_score * 1.8
        + persistence_component
        + evidence_component
        + liquidity * 0.12
    )
    return clamp_int(blended, 0, 100)


def stock_state(short_score: int, month_score: int, mops3d: int, rs5: float, rs20: float) -> str:
    if month_score >= 80 and short_score >= 70 and mops3d >= 65:
        return "expansion"
    if month_score >= 70:
        return "confirmation"
    if month_score >= 55:
        return "seed"
    if short_score >= 70 and month_score < 55:
        return "late"
    if rs5 < 0 and rs20 < 0:
        return "breakdown"
    return "seed"


def theme_state(theme_score: int, strong_count: int, short_avg: float, month_avg: float) -> str:
    if theme_score >= 80 and strong_count >= 3:
        return "expansion"
    if theme_score >= 70 and strong_count >= 2:
        return "confirmation"
    if theme_score >= 55:
        return "seed"
    if short_avg >= 70 and month_avg < 55:
        return "late"
    return "breakdown"


def observation_reason(stock: dict[str, Any]) -> str:
    if stock.get("speculationFlag") == "attention_without_company_evidence":
        return "speculation_only_watch"
    if stock["scoreBreakdown"]["monthContinuationScore"] >= 70 and stock["scoreBreakdown"]["shortImpulseScore"] < 55:
        return "month_viable_short_crowded"
    if stock["scoreBreakdown"]["monthContinuationScore"] < 55 and stock["scoreBreakdown"]["shortImpulseScore"] >= 70:
        return "short_strong_month_insufficient"
    if stock["scoreBreakdown"]["mops3dScore"] <= 15:
        return "mops_negative_pressure"
    return "mops_insufficient_month_watch"


def format_price(value: float) -> str:
    if value >= 1000:
        return f"{round(value):.0f}"
    if value >= 100:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{value:.2f}".rstrip("0").rstrip(".")


def build_price_model(close_value: float, month_score: int, short_score: int, calendar_score: int, second_leg: int, rs20: float) -> tuple[str, str, str, dict[str, Any]]:
    pullback_pct = clamp(6.0 - month_score * 0.02 - max(rs20, 0) * 0.03, 2.5, 6.5)
    target_pct = clamp(12 + month_score * 0.10 + calendar_score * 0.20 + second_leg * 0.25, 12, 30)
    stop_pct = clamp(8.0 - month_score * 0.02 - short_score * 0.01, 4.5, 8.0)
    low = close_value * (1 - pullback_pct / 100)
    high = close_value * (1 - pullback_pct * 0.4 / 100)
    target = close_value * (1 + target_pct / 100)
    stop = close_value * (1 - stop_pct / 100)
    return (
        f"{format_price(low)}-{format_price(high)}",
        format_price(target),
        format_price(stop),
        {
            "basis": "20_trading_day_model_v2",
            "pullbackPct": round(pullback_pct, 2),
            "targetPct": round(target_pct, 2),
            "stopPct": round(stop_pct, 2),
        },
    )


def trading_week_range(report_date: date) -> dict[str, str]:
    monday = report_date - timedelta(days=report_date.weekday())
    friday = monday + timedelta(days=4)
    return {"start": iso(monday), "end": iso(friday)}


def merge_supply_chain_meta() -> dict[str, dict[str, Any]]:
    payload = load_json(SUPPLY_CHAIN_JSON)
    out: dict[str, dict[str, Any]] = {}
    for stock in payload["stocks"]:
        ticker = clean_text(stock.get("ticker"))
        if ticker:
            out[ticker] = stock
    return out


def compute_preliminary_score(row: PriceRow, meta: dict[str, Any]) -> float:
    verified_bonus = 8 if meta.get("verifiedThemes") else 0
    flow_bonus = 12 if row.institution_net > 0 else 0
    foreign_bonus = 8 if row.foreign_net > 0 else 0
    return (
        row.change_pct * 3.0
        + math.log10(max(row.amount, 1)) * 4.0
        + flow_bonus
        + foreign_bonus
        + verified_bonus
    )


def fetch_candidate_histories(rows: dict[str, PriceRow], end_date: date) -> dict[str, list[HistoryPoint]]:
    histories: dict[str, list[HistoryPoint]] = {}
    for ticker, row in rows.items():
        if row.market == "TWSE":
            points = fetch_twse_history(ticker, end_date)
        else:
            points = fetch_tpex_history(ticker, end_date)
        if len(points) >= 5:
            histories[ticker] = points
    return histories


def safe_get(mapping: dict[str, Any], key: str, default: Any = "") -> Any:
    value = mapping.get(key)
    return default if value is None else value


def build_stock_card(
    row: PriceRow,
    meta: dict[str, Any],
    theme_def: dict[str, Any],
    stock_info: dict[str, Any],
    index_returns: dict[int, float],
) -> dict[str, Any]:
    histories = stock_info["history"]
    r1 = lookup_return(histories, 1)
    r3 = lookup_return(histories, 3)
    r5 = lookup_return(histories, 5)
    r10 = lookup_return(histories, 10)
    r20 = lookup_return(histories, 20)
    rs5 = relative_strength(r5, index_returns.get(5, 0.0))
    rs10 = relative_strength(r10, index_returns.get(10, 0.0))
    rs20 = relative_strength(r20, index_returns.get(20, 0.0))
    rs1 = relative_strength(r1, index_returns.get(1, 0.0))
    rs3 = relative_strength(r3, index_returns.get(3, 0.0))
    vol_ratio = volume_ratio(histories)
    liq_score = liquidity_bucket(amount_median(histories))

    material_score = stock_info["material_score"]
    revenue_score = stock_info["revenue_score"]
    order_score = stock_info["order_score"]
    procedural_score = stock_info["procedural_score"]
    attention_score = stock_info["attention_score"]
    mops3d_score = stock_info["mops3d_score"]
    mops3d_signal = stock_info["mops3d_signal"]

    calendar_score = score_calendar(material_score, revenue_score, order_score)
    second_leg = score_second_leg(material_score, revenue_score, order_score, mops3d_score, rs20)
    short_score = score_short_impulse(rs1, rs3, rs5, vol_ratio, row.institution_net, mops3d_score)
    month_score = score_month_continuation(
        calendar_score,
        second_leg,
        rs5,
        rs10,
        rs20,
        material_score,
        revenue_score,
        order_score,
        liq_score,
    )
    persistence_score = clamp_int(max(rs5, 0) * 0.3 + max(rs10, 0) * 0.25 + max(rs20, 0) * 0.2, 0, 100)
    breakdown = {
        "mops3dScore": mops3d_score,
        "materialCompanyEvent30dScore": material_score,
        "revenueEarningsAccelerationScore": revenue_score,
        "orderQualificationScore": order_score,
        "proceduralMopsScore": procedural_score,
        "attentionScore": attention_score,
        "calendarScore": calendar_score,
        "secondLegEvidenceScore": second_leg,
        "shortImpulseScore": short_score,
        "monthContinuationScore": month_score,
        "relativeStrength5d": rs5,
        "relativeStrength10d": rs10,
        "relativeStrength20d": rs20,
        "persistenceScaledScore": persistence_score,
    }
    speculation_flag = HELPERS["derive_speculation_flag"]({}, {
        "attentionScore": attention_score,
        "materialCompanyEvent30dScore": material_score,
        "revenueEarningsAccelerationScore": revenue_score,
        "orderQualificationScore": order_score,
        "shortImpulseScore": short_score,
        "monthContinuationScore": month_score,
    })
    stock_score = HELPERS["rescaled_stock_score"](breakdown)
    state = stock_state(short_score, month_score, mops3d_score, rs5, rs20)
    entry, target, stop, price_model = build_price_model(row.close, month_score, short_score, calendar_score, second_leg, rs20)

    material_summary = stock_info["material_summary"]
    revenue_summary = stock_info["revenue_summary"]
    order_summary = stock_info["order_summary"]
    mops_summary = stock_info["mops3d_summary"]
    mops_items = [
        {
            "date": item["date"],
            "title": item["title"],
            "direction": item["direction"],
            "url": item["url"],
        }
        for item in stock_info["mops3d_items"]
    ]

    if material_score >= 70 and revenue_score >= 70:
        core = "30 日公司事件與營收 / 財報加速同步成立，月內第二段行情證據完整。"
    elif material_score >= 70:
        core = "30 日公司事件是主要支撐，短線強勢不是單純靠注意力。"
    elif revenue_score >= 70:
        core = "營收 / 財報加速是主要支撐，基本面延續性比單日題材更完整。"
    elif order_score >= 70:
        core = "訂單 / 客戶 / 認證節點是主要支撐，後續看量產或出貨接棒。"
    else:
        core = "證據偏向月內續航與相對強弱，硬公司事件仍需要進一步補強。"

    not_priced = (
        "目前月內排序優先看 30 日公司事件、營收 / 財報加速與 second-leg evidence。"
        if month_score >= short_score
        else "短線節奏較強，但月內是否完全反映仍取決於第二段事件能否接棒。"
    )
    invalidation = (
        "若下一個月內事件節點無法接棒、且 5/10/20 日相對強弱同步轉負，月內續航假設失效。"
        if month_score >= 60
        else "若新的公司事件沒有出現，這筆 setup 會回到觀察池。"
    )
    downside = [
        "若 MOPS / 公司事件後續沒有延伸成營收、財報或訂單驗證，排序分數會下修。",
        "若 5/10/20 日相對強弱惡化，月內續航優勢會消失。",
    ]
    catalysts = [material_summary, revenue_summary, order_summary]
    sources = [
        {
            "label": f"MOPS {row.ticker} 近 30 日重大訊息",
            "url": "https://mops.twse.com.tw/mops/#/web/t05st01",
        }
    ]
    for item in mops_items[:2]:
        sources.append({"label": f"{item['date']} {item['title']}", "url": item["url"]})

    gate_status = {
        "mops3d": HELPERS["summarize_gate_mops"](mops3d_score, mops3d_signal),
        "materialCompanyEvents30d": material_summary,
        "revenueEarnings30d": revenue_summary,
        "orderQualification30d": order_summary,
        "secondLegEvidence": "通過" if second_leg >= 10 else "未通過",
        "persistence": "通過" if sum(v > 0 for v in [rs5, rs10, rs20]) >= 2 else "未通過",
        "speculation": speculation_flag or "none",
    }

    return {
        "rank": 0,
        "ticker": row.ticker,
        "name": row.name,
        "role": safe_get(meta, "supplyChainRole", "角色未驗證"),
        "priceDate": stock_info["price_date"],
        "close": format_price(row.close),
        "entry": entry,
        "target": target,
        "stop": stop,
        "pe": row.pe or "無法驗證",
        "pb": "無法驗證",
        "foreignFlow": f"{int(row.foreign_net):,}" if row.foreign_net else "0",
        "institutionFlow": f"{int(row.institution_net):,}" if row.institution_net else "0",
        "coreReason": core,
        "notPricedIn": not_priced,
        "targetLogic": f"20 日價位模型以月內續航 {month_score} 分、短線衝力 {short_score} 分、20 日催化 {calendar_score} 分與二階證據 {second_leg} 分共同決定。",
        "catalysts": [x for x in catalysts if x],
        "downside": downside,
        "sourceRefs": [source["label"] for source in sources],
        "stockScore": stock_score,
        "state": state,
        "scoreBreakdown": breakdown,
        "gateStatus": gate_status,
        "invalidationType": "month_continuation_failure" if month_score >= short_score else "short_failure",
        "invalidationTrigger": invalidation,
        "priceModel": price_model,
        "mops3dSignal": mops3d_signal,
        "mops3dSummary": mops_summary,
        "mops3dItems": mops_items,
        "materialCompanyEvent30dSummary": material_summary,
        "revenueEarnings30dSummary": revenue_summary,
        "orderQualification30dSummary": order_summary,
        "speculationFlag": speculation_flag,
        "theme": theme_def["name"],
    }


def summarize_theme(theme_def: dict[str, Any], stocks: list[dict[str, Any]]) -> tuple[str, str, str, list[str], list[str], dict[str, Any], dict[str, Any], str]:
    top3 = stocks[:3]
    score_breakdown = {
        "mops3dScore": clamp_int(sum(stock["scoreBreakdown"]["mops3dScore"] for stock in top3) / max(len(top3), 1), 0, 100),
        "externalDemandDeployment30dScore": clamp_int(sum(max(stock["scoreBreakdown"]["materialCompanyEvent30dScore"], stock["scoreBreakdown"]["orderQualificationScore"]) for stock in top3) / max(len(top3), 1), 0, 100),
        "priceShortageLeadtime30dScore": clamp_int(sum(max(stock["scoreBreakdown"]["revenueEarningsAccelerationScore"], stock["scoreBreakdown"]["mops3dScore"]) for stock in top3) / max(len(top3), 1), 0, 100),
        "companyEvidenceSpreadScore": HELPERS["score_company_evidence_spread"](stocks),
        "calendarSecondLegCompositeScore": clamp_int(sum((stock["scoreBreakdown"]["calendarScore"] * 2 + stock["scoreBreakdown"]["secondLegEvidenceScore"] * 2) for stock in top3) / max(len(top3), 1), 0, 100),
        "persistenceScaledScore": clamp_int(sum(stock["scoreBreakdown"]["persistenceScaledScore"] for stock in top3) / max(len(top3), 1), 0, 100),
        "shortImpulseScore": clamp_int(sum(stock["scoreBreakdown"]["shortImpulseScore"] for stock in top3) / max(len(top3), 1), 0, 100),
        "attentionScore": clamp_int(sum(stock["scoreBreakdown"]["attentionScore"] for stock in top3) / max(len(top3), 1), 0, 100),
    }
    theme_score = HELPERS["recompute_theme_score"]({"scoreBreakdown": score_breakdown})
    strong_count = sum(stock["stockScore"] >= 70 for stock in stocks[:5])
    short_avg = sum(stock["scoreBreakdown"]["shortImpulseScore"] for stock in top3) / max(len(top3), 1)
    month_avg = sum(stock["scoreBreakdown"]["monthContinuationScore"] for stock in top3) / max(len(top3), 1)
    state = theme_state(theme_score, strong_count, short_avg, month_avg)
    rs5_avg = round(sum(stock["scoreBreakdown"]["relativeStrength5d"] for stock in top3) / max(len(top3), 1), 2)
    rs10_avg = round(sum(stock["scoreBreakdown"]["relativeStrength10d"] for stock in top3) / max(len(top3), 1), 2)
    rs20_avg = round(sum(stock["scoreBreakdown"]["relativeStrength20d"] for stock in top3) / max(len(top3), 1), 2)
    institution_positive = sum(1 for stock in stocks[:5] if num(stock["institutionFlow"]) > 0)
    outperform_ratio = round(
        sum(
            stock["scoreBreakdown"]["relativeStrength20d"] > 0
            for stock in stocks[:5]
        ) / max(min(len(stocks), 5), 1),
        2,
    )
    heat = "偏熱" if short_avg >= 75 else "中偏熱" if short_avg >= 65 else "溫熱" if short_avg >= 55 else "中性"
    stance = "偏多" if theme_score >= 70 else "中性" if theme_score >= 55 else "保守"
    summary = (
        f"{theme_def['family']}；精確子題材是 {theme_def['name']}。"
        f" 30 日公司證據擴散與月內續航分數為主，最近最強成員為 {', '.join(stock['ticker'] for stock in top3)}。"
    )
    if score_breakdown["priceShortageLeadtime30dScore"] >= 70:
        pricing_view = "價格 / shortage / lead-time 訊號偏正面，原料與上游報價具支撐。"
    else:
        pricing_view = "價格與 shortage 訊號中性，這條主線更多靠公司事件與需求部署維持。"
    policy_view = theme_def["policy"]
    premium_space = (
        "月內仍有 premium space，因為 30 日公司事件、營收財報或訂單證據沒有只集中在單一股票。"
        if strong_count >= 2
        else "premium space 有限，因為證據擴散還不夠廣，後續要看第二段事件能否接棒。"
    )
    why_now = [
        {"label": "主因", "text": f"月內主分數 {theme_score} 分，短線衝力均值 {round(short_avg)} 分，題材狀態為 {state}。"},
        {"label": "證據", "text": f"公司證據擴散 {score_breakdown['companyEvidenceSpreadScore']} 分、外需部署 {score_breakdown['externalDemandDeployment30dScore']} 分。"},
        {"label": "廣度", "text": f"核心成員 20 日相對強弱平均 {rs20_avg}，outperformRatio {outperform_ratio}。"},
    ]
    downside = [
        "若下一個月內事件節點只剩單一旗艦股，題材會從交易池退回觀察池。",
        "若 5/10/20 日相對強弱同步轉負，月內續航分數將快速下修。",
    ]
    breadth_stats = {
        "coreStockCount": min(len(stocks), 5),
        "outperformRatio": outperform_ratio,
        "institutionPositiveCount": institution_positive,
        "relativeStrength5d": rs5_avg,
        "relativeStrength10d": rs10_avg,
        "relativeStrength20d": rs20_avg,
    }
    gate_status = {
        "mops3d": f"題材內三日 MOPS 平均 {score_breakdown['mops3dScore']} 分。",
        "secondLegEvidence": "通過" if score_breakdown["calendarSecondLegCompositeScore"] >= 55 else "未通過",
        "persistence": "通過" if sum(value > 0 for value in [rs5_avg, rs10_avg, rs20_avg]) >= 2 else "未通過",
        "candidateBreadth": f"前五成員中 {strong_count} 檔 stockScore >= 70。",
    }
    return summary, pricing_view, premium_space, why_now, downside, breadth_stats, gate_status, state, heat, stance, theme_score, score_breakdown


def build_theme_card(theme_def: dict[str, Any], stocks: list[dict[str, Any]], price_date: date) -> dict[str, Any]:
    (
        summary,
        pricing_view,
        premium_space,
        why_now,
        downside,
        breadth_stats,
        gate_status,
        state,
        heat,
        stance,
        theme_score,
        score_breakdown,
    ) = summarize_theme(theme_def, stocks)
    stock_infos = [{"ticker": stock["ticker"], "mops3dScore": stock["scoreBreakdown"]["mops3dScore"]} for stock in stocks]
    mops_score, mops_breadth, mops_summary = HELPERS["theme_mops_score"](stock_infos, gate_status["secondLegEvidence"])
    score_breakdown["mops3dScore"] = mops_score
    mops_breadth["windowDates"] = []
    return {
        "rank": 0,
        "name": theme_def["name"],
        "heat": heat,
        "stance": stance,
        "summary": summary,
        "pricingView": pricing_view,
        "policyView": theme_def["policy"],
        "premiumSpace": premium_space,
        "whyNow": why_now,
        "downsideEvents": downside,
        "stocks": stocks[:5],
        "state": state,
        "themeScore": theme_score,
        "gateStatus": gate_status,
        "breadthStats": breadth_stats,
        "scoreBreakdown": score_breakdown,
        "mops3dSummary": mops_summary,
        "mops3dBreadth": mops_breadth,
        "family": theme_def["family"],
        "nearestComparable": theme_def["comparable"],
        "separateReason": theme_def["separateReason"],
    }


def trade_theme_limit(score: int) -> tuple[int, int]:
    if score >= 75:
        return 5, 6
    if score >= 60:
        return 5, 6
    if score >= 40:
        return 4, 4
    if score >= 25:
        return 3, 4
    return 2, 2


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


def build_regimes(
    template: dict[str, Any],
    index_history: list[tuple[date, float]],
    foreign_flow_twd_bn: float,
    themes: list[dict[str, Any]],
    observation_themes: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    idx_close = [value for _, value in index_history]
    idx_ret = {}
    for window in (1, 3, 5, 10, 20):
        if len(idx_close) > window:
            idx_ret[window] = (idx_close[-1] / idx_close[-(window + 1)] - 1) * 100
        else:
            idx_ret[window] = 0.0

    monthly_macro = safe_get(template.get("marketSnapshot", {}).get("marketRegime", {}).get("scoreBreakdown", {}), "macro", 5)
    monthly_event_risk = safe_get(template.get("marketSnapshot", {}).get("marketRegime", {}).get("scoreBreakdown", {}), "eventRisk", 20)
    short_macro = safe_get(template.get("marketSnapshot", {}).get("shortTermRegime", {}).get("scoreBreakdown", {}), "macro", 5)
    short_event_risk = safe_get(template.get("marketSnapshot", {}).get("shortTermRegime", {}).get("scoreBreakdown", {}), "eventRisk", 20)

    confirm_or_expand = sum(theme["state"] in {"confirmation", "expansion"} for theme in themes)
    strong_breadth = sum(theme["breadthStats"]["outperformRatio"] >= 0.4 for theme in themes)
    tape_breadth_month = 0
    if idx_ret[1] > 0:
        tape_breadth_month += 7
    if idx_ret[5] > 0 and idx_ret[10] > 0:
        tape_breadth_month += 7
    elif idx_ret[5] > 0 or idx_ret[10] > 0:
        tape_breadth_month += 3
    if strong_breadth >= max(2, len(themes) // 2) and confirm_or_expand >= 3:
        tape_breadth_month += 6
    elif strong_breadth >= max(2, len(themes) // 2) or confirm_or_expand >= 3:
        tape_breadth_month += 3

    flow_score = 10 if foreign_flow_twd_bn > 20 else 5 if foreign_flow_twd_bn >= -20 else 0
    inst_positive = sum(theme["breadthStats"]["institutionPositiveCount"] for theme in themes)
    flow_score += 10 if inst_positive >= 10 else 5 if inst_positive >= 5 else 0

    avg_theme_score = sum(theme["themeScore"] for theme in themes) / max(len(themes), 1)
    breakdown_count = sum(theme["state"] == "breakdown" for theme in observation_themes)
    theme_health = 10 if avg_theme_score >= 80 else 5 if avg_theme_score >= 70 else 0
    theme_health += 10 if breakdown_count <= 1 else 5 if breakdown_count <= 3 else 0

    monthly_score_breakdown = {
        "tapeBreadth": tape_breadth_month,
        "flow": flow_score,
        "themeHealth": theme_health,
        "macro": int(monthly_macro),
        "eventRisk": int(monthly_event_risk),
    }
    monthly_score = sum(monthly_score_breakdown.values())
    monthly_stance, monthly_mode = regime_band(monthly_score)

    tape_breadth_short = 0
    if idx_ret[1] > 0:
        tape_breadth_short += 7
    if idx_ret[3] > 0 and idx_ret[5] > 0:
        tape_breadth_short += 7
    elif idx_ret[3] > 0 or idx_ret[5] > 0:
        tape_breadth_short += 3
    strong_short = sum(theme["scoreBreakdown"]["shortImpulseScore"] >= 70 for theme in themes)
    if strong_short >= 3:
        tape_breadth_short += 6
    elif strong_short >= 2:
        tape_breadth_short += 3

    avg_short = sum(theme["scoreBreakdown"]["shortImpulseScore"] for theme in themes) / max(len(themes), 1)
    short_theme_health = 10 if avg_short >= 80 else 5 if avg_short >= 70 else 0
    short_theme_health += 8 if breakdown_count <= 1 else 4 if breakdown_count <= 3 else 0
    short_flow = 10 if foreign_flow_twd_bn > 20 else 5 if foreign_flow_twd_bn >= -20 else 0
    short_flow += 10 if inst_positive >= 10 else 5 if inst_positive >= 5 else 0
    short_score_breakdown = {
        "tapeBreadth": tape_breadth_short,
        "flow": short_flow,
        "themeHealth": short_theme_health,
        "macro": int(short_macro),
        "eventRisk": int(short_event_risk),
    }
    short_score = sum(short_score_breakdown.values())
    short_stance, short_mode = regime_band(short_score)

    monthly = {
        "score": monthly_score,
        "stance": monthly_stance,
        "mode": monthly_mode,
        "summary": (
            "月內 Regime 以 5 / 10 / 20 日 persistence 與公司層證據為主。"
            if monthly_score >= 60
            else "月內 Regime 偏保守，因為續航與廣度不夠平均。"
        ),
        "scoreBreakdown": monthly_score_breakdown,
        "drivers": [
            f"{index_history[-1][0]} TAIEX 收 {idx_close[-1]:,.2f}，5 / 10 / 20 日延續性是本版主框架。",
            f"外資現貨買超 {foreign_flow_twd_bn:+.2f} 億，flow 直接影響主交易池上限。",
            f"月內前五主線平均 themeScore {avg_theme_score:.1f}，觀察池 breakdown 題材 {breakdown_count} 個。",
            "macro 與 eventRisk 目前沿用前一版已驗證數值，這次重建主體是價格、法人、供應鏈與 MOPS 路徑。",
        ],
        "effectOnSelection": "月內 Regime 直接控制交易池主題與主選股數量。",
    }
    short_term = {
        "score": short_score,
        "stance": short_stance,
        "mode": short_mode,
        "summary": (
            "短線 Regime 仍看 1 / 3 / 5 日節奏與追價風險。"
            if short_score >= 60
            else "短線 Regime 偏保守，因為近端節奏與分化較大。"
        ),
        "scoreBreakdown": short_score_breakdown,
        "drivers": [
            f"1 / 3 / 5 日 index return 分別為 {idx_ret[1]:.2f}% / {idx_ret[3]:.2f}% / {idx_ret[5]:.2f}%。",
            f"前五主線平均短線衝力 {avg_short:.1f} 分。",
            "短線分數只做節奏提示，不直接壓縮月內交易池 cap。",
        ],
        "effectOnSelection": "短線 Regime 只提示追價與分化風險，不改月內 cap。",
    }
    divergence = (
        "月內 Regime 高於短線 Regime，因為 5 / 10 / 20 日續航強於 1 / 3 / 5 日節奏。"
        if monthly_score > short_score
        else "短線 Regime 與月內 Regime 接近，代表節奏與續航沒有明顯背離。"
    )
    return monthly, short_term, divergence


def build_report() -> tuple[dict[str, Any], Path]:
    template = load_json(LATEST_JSON)
    report_date, anchor = weekday_report_date(now_local().date())
    price_date, twse_bundle = fetch_latest_twse_bundle(anchor)
    tpex_bundle = fetch_tpex_bundle(price_date)
    t86_bundle = fetch_twse_t86(price_date)
    bfi_bundle = fetch_twse_bfi82u(price_date)
    tpex_insti_bundle = fetch_tpex_insti(price_date)

    twse_market, index_info = parse_twse_market(twse_bundle)
    tpex_market = parse_tpex_market(tpex_bundle)
    all_market = {**twse_market, **tpex_market}

    twse_flows = parse_twse_t86_flows(t86_bundle)
    tpex_flows = parse_tpex_insti_flows(tpex_insti_bundle)
    for ticker, row in all_market.items():
        foreign_net, inst_net = (twse_flows.get(ticker) or tpex_flows.get(ticker) or (0.0, 0.0))
        row.foreign_net = foreign_net
        row.institution_net = inst_net

    supply_meta = merge_supply_chain_meta()
    theme_candidates: dict[str, list[tuple[float, PriceRow, dict[str, Any]]]] = {theme["name"]: [] for theme in THEME_DEFS}
    ticker_to_themes: dict[str, list[str]] = {}
    for ticker, row in all_market.items():
        meta = supply_meta.get(ticker)
        if not meta:
            continue
        matched: list[str] = []
        for theme_def in THEME_DEFS:
            if match_theme(meta, theme_def):
                matched.append(theme_def["name"])
                theme_candidates[theme_def["name"]].append((compute_preliminary_score(row, meta), row, meta))
        if matched:
            ticker_to_themes[ticker] = matched

    candidate_rows: dict[str, PriceRow] = {}
    candidate_theme_defs: dict[str, dict[str, Any]] = {theme["name"]: theme for theme in THEME_DEFS}
    for theme_name, rows in theme_candidates.items():
        rows.sort(key=lambda item: item[0], reverse=True)
        kept = 0
        for _, row, meta in rows:
            if row.amount < 30_000_000 and row.institution_net <= 0 and row.change_pct <= 0:
                continue
            candidate_rows.setdefault(row.ticker, row)
            kept += 1
            if kept >= 8:
                break

    histories = fetch_candidate_histories(candidate_rows, price_date)
    trading_dates = recent_trading_dates(price_date, 20)
    index_history = fetch_index_history(trading_dates)
    index_returns = {}
    closes = [close for _, close in index_history]
    for window in (1, 3, 5, 10, 20):
        if len(closes) > window:
            index_returns[window] = (closes[-1] / closes[-(window + 1)] - 1) * 100
        else:
            index_returns[window] = 0.0

    stock_info_map: dict[str, dict[str, Any]] = {}
    window_3d = HELPERS["hybrid_window"](price_date)
    window_30d = [price_date - timedelta(days=i) for i in range(30)]
    for ticker, row in candidate_rows.items():
        history = histories.get(ticker)
        if not history:
            continue
        raw_items_30d = HELPERS["fetch_stock_mops_items"](ticker, window_30d)
        hybrid_set = {iso(d) for d in window_3d}
        raw_items_3d = [
            item
            for item in raw_items_30d
            if HELPERS["parse_roc_date"](item.date) and iso(HELPERS["parse_roc_date"](item.date)) in hybrid_set
        ]
        mops3d_score, mops3d_signal, mops3d_summary = HELPERS["stock_mops_score"](raw_items_3d, window_3d)
        material_score, _, material_summary = HELPERS["score_material_company_events_30d"](raw_items_30d, price_date)
        procedural_score, _, procedural_summary = HELPERS["score_procedural_mops_30d"](raw_items_30d, price_date)
        revenue_score, revenue_summary = HELPERS["score_revenue_earnings_acceleration"]({}, raw_items_30d, price_date)
        order_score, order_summary = HELPERS["score_order_qualification"]({}, raw_items_30d, price_date)
        attention_score, attention_summary = HELPERS["score_attention"]({}, raw_items_30d)
        stock_info_map[ticker] = {
            "history": history,
            "price_date": iso(price_date),
            "mops3d_score": mops3d_score,
            "mops3d_signal": mops3d_signal,
            "mops3d_summary": mops3d_summary,
            "mops3d_items": [
                {"date": item.date, "title": item.title, "direction": item.direction, "url": item.url}
                for item in raw_items_3d
            ],
            "material_score": material_score,
            "material_summary": material_summary,
            "procedural_score": procedural_score,
            "procedural_summary": procedural_summary,
            "revenue_score": revenue_score,
            "revenue_summary": revenue_summary,
            "order_score": order_score,
            "order_summary": order_summary,
            "attention_score": attention_score,
            "attention_summary": attention_summary,
        }

    themed_stock_cards: dict[str, list[dict[str, Any]]] = {theme["name"]: [] for theme in THEME_DEFS}
    for ticker, row in candidate_rows.items():
        if ticker not in stock_info_map:
            continue
        meta = supply_meta[ticker]
        for theme_name in ticker_to_themes.get(ticker, []):
            card = build_stock_card(row, meta, candidate_theme_defs[theme_name], stock_info_map[ticker], index_returns)
            themed_stock_cards[theme_name].append(card)

    theme_cards: list[dict[str, Any]] = []
    observation_theme_cards: list[dict[str, Any]] = []
    for theme_def in THEME_DEFS:
        stocks = themed_stock_cards[theme_def["name"]]
        if not stocks:
            continue
        stocks.sort(key=lambda stock: (stock["stockScore"], stock["ticker"]), reverse=True)
        for idx, stock in enumerate(stocks, start=1):
            stock["rank"] = idx
        theme_card = build_theme_card(theme_def, stocks, price_date)
        if theme_card["state"] in {"breakdown", "late"} or theme_card["themeScore"] < 60:
            theme_card["observationCategory"] = (
                "short_strong_month_insufficient"
                if theme_card["scoreBreakdown"]["shortImpulseScore"] >= 70 and theme_card["scoreBreakdown"]["companyEvidenceSpreadScore"] < 35
                else "mops_insufficient_month_watch"
            )
            observation_theme_cards.append(theme_card)
        else:
            theme_cards.append(theme_card)

    theme_cards.sort(key=lambda theme: (theme["themeScore"], theme["name"]), reverse=True)
    observation_theme_cards.sort(key=lambda theme: (theme["themeScore"], theme["name"]), reverse=True)
    for idx, theme in enumerate(theme_cards, start=1):
        theme["rank"] = idx
    for idx, theme in enumerate(observation_theme_cards, start=1):
        theme["rank"] = idx

    foreign_flow_twd_bn = parse_foreign_flow_twd_bn(bfi_bundle)
    monthly_regime, short_regime, divergence = build_regimes(template, index_history, foreign_flow_twd_bn, theme_cards[:5], observation_theme_cards[:5])
    max_trade_themes, max_trade_stocks = trade_theme_limit(monthly_regime["score"])
    trade_themes = theme_cards[:max_trade_themes]
    overflow_trade_themes = theme_cards[max_trade_themes:]
    for theme in overflow_trade_themes:
        theme["observationCategory"] = "month_viable_short_crowded"
    observation_themes = (overflow_trade_themes + observation_theme_cards)[:5]
    for idx, theme in enumerate(observation_themes, start=1):
        theme["rank"] = idx

    eligible_top_picks: list[tuple[str, dict[str, Any]]] = []
    for theme in trade_themes:
        for stock in theme["stocks"]:
            if stock["scoreBreakdown"]["mops3dScore"] <= 15 and stock["mops3dSignal"] in {"high_negative", "medium_negative"}:
                continue
            if stock["speculationFlag"] == "attention_without_company_evidence":
                continue
            eligible_top_picks.append((theme["name"], stock))
    eligible_top_picks.sort(key=lambda pair: (pair[1]["stockScore"], pair[1]["ticker"]), reverse=True)

    top_picks = []
    used = set()
    for theme_name, stock in eligible_top_picks:
        if stock["ticker"] in used:
            continue
        used.add(stock["ticker"])
        top_picks.append(
            {
                "rank": len(top_picks) + 1,
                "ticker": stock["ticker"],
                "name": stock["name"],
                "theme": theme_name,
                "reason": stock["coreReason"],
                "state": stock["state"],
                "stockScore": stock["stockScore"],
                "gateStatus": deepcopy(stock["gateStatus"]),
                "alternativeRejected": f"比同族群次佳股更適合，因為 {stock['scoreBreakdown']['monthContinuationScore']} 分的月內續航高於同題材平均。",
                "scoreBreakdown": deepcopy(stock["scoreBreakdown"]),
                "invalidationType": stock["invalidationType"],
                "mops3dSignal": stock["mops3dSignal"],
                "mops3dSummary": stock["mops3dSummary"],
                "mops3dItems": deepcopy(stock["mops3dItems"]),
                "materialCompanyEvent30dSummary": stock["materialCompanyEvent30dSummary"],
                "revenueEarnings30dSummary": stock["revenueEarnings30dSummary"],
                "orderQualification30dSummary": stock["orderQualification30dSummary"],
                "speculationFlag": stock["speculationFlag"],
            }
        )
        if len(top_picks) >= max_trade_stocks:
            break

    observation_stock_cards = []
    for theme in overflow_trade_themes:
        for stock in theme["stocks"]:
            stock["observationCategory"] = "month_viable_short_crowded"
            observation_stock_cards.append(stock)
    for theme in observation_themes:
        for stock in theme["stocks"]:
            stock["observationCategory"] = observation_reason(stock)
            observation_stock_cards.append(stock)
    observation_stock_cards.sort(key=lambda stock: (stock["stockScore"], stock["ticker"]), reverse=True)
    observation_stocks = []
    top_pick_tickers = {stock["ticker"] for stock in top_picks}
    seen_obs = set()
    for stock in observation_stock_cards:
        if stock["ticker"] in top_pick_tickers:
            continue
        if stock["ticker"] in seen_obs:
            continue
        seen_obs.add(stock["ticker"])
        observation_stocks.append(stock)
        if len(observation_stocks) >= 5:
            break
    for idx, stock in enumerate(observation_stocks, start=1):
        stock["rank"] = idx

    strongest_theme = trade_themes[0] if trade_themes else (theme_cards[0] if theme_cards else None)
    strongest_group = {
        "name": strongest_theme["name"] if strongest_theme else "無法驗證",
        "change": f"{sum(stock['scoreBreakdown']['relativeStrength5d'] for stock in strongest_theme['stocks'][:3]) / max(len(strongest_theme['stocks'][:3]),1):+.2f}%"
        if strongest_theme
        else "無法驗證",
    }

    before_themes = [theme["name"] for theme in template.get("themes") or []]
    after_themes = [theme["name"] for theme in trade_themes]
    before_picks = [stock["ticker"] for stock in template.get("topPicks") or []]
    after_picks = [stock["ticker"] for stock in top_picks]

    discoveries = HELPERS["build_new_discoveries"](
        {
            ticker: {
                "material_score": info["material_score"],
                "revenue_score": info["revenue_score"],
                "raw_items_30d": [
                    type("Obj", (), item)() if isinstance(item, dict) else item  # unused here
                    for item in []
                ],
            }
            for ticker, info in {}
        },
        {},
        {},
    )
    discoveries = []
    for ticker, info in sorted(
        stock_info_map.items(),
        key=lambda kv: (kv[1]["material_score"], kv[1]["revenue_score"], kv[1]["order_score"]),
        reverse=True,
    )[:3]:
        if not info["mops3d_items"]:
            continue
        item = info["mops3d_items"][0]
        discoveries.append(
            {
                "scope": ", ".join(ticker_to_themes.get(ticker, [])[:1]) or "個股事件",
                "title": f"{ticker} {candidate_rows[ticker].name} {item['date']} {item['title']}",
                "detail": info["mops3d_summary"],
                "whyItMatters": "這則公司層事件已直接進入 30 日事件與月內續航排序分數。",
            }
        )

    report = deepcopy(template)
    report["reportDate"] = iso(report_date)
    report["priceDate"] = iso(price_date)
    report["weekRange"] = trading_week_range(report_date)
    report["selectionHorizon"] = {
        "basis": "20_trading_days",
        "label": "未來 20 個交易日",
        "style": "swing_month",
    }
    report["marketSnapshot"] = {
        "indexClose": round(index_info["indexClose"], 2),
        "indexChangePct": round(index_info["indexChangePct"], 2),
        "foreignFlowTwdBn": foreign_flow_twd_bn,
        "strongestGroup": strongest_group,
        "marketRegime": monthly_regime,
        "shortTermRegime": short_regime,
        "regimeDivergenceSummary": divergence,
    }
    report["themes"] = trade_themes
    report["topPicks"] = top_picks
    report["observationThemes"] = observation_themes
    report["observationStocks"] = observation_stocks
    report["newDiscoveries"] = discoveries
    report["headline"] = (
        f"{report_date.month}/{report_date.day} from-source 重建版：月內 Regime {monthly_regime['score']} 分 / {monthly_regime['mode']}、"
        f"短線 Regime {short_regime['score']} 分 / {short_regime['mode']}；"
        f"本版已從官方價格、法人、供應鏈與 MOPS 路徑重建題材與個股排序。"
    )
    report["deck"] = (
        f"這版不是沿用舊排名重算分數，而是用 {price_date} 官方 TWSE / TPEX 收盤、T86、BFI82U、TPEX 法人、"
        "供應鏈底圖與 MOPS 近 30 日公司事件，重新建出候選題材池與交易池。"
    )
    report["executiveSummary"] = [
        f"本版價格基準是 {price_date} 官方 TWSE / TPEX 收盤；題材與個股排名從零重建，不沿用前一版主題順序。",
        f"月內 Regime 為 {monthly_regime['score']} / {monthly_regime['mode']}，直接決定交易池上限；短線 Regime 為 {short_regime['score']} / {short_regime['mode']}，只做節奏提示。",
        f"新的月內前五主線依序為：{'、'.join(after_themes)}。",
        f"新的首頁主選股依序為：{'、'.join(after_picks)}。",
        "排序核心已改成 30 日公司事件、營收 / 財報加速、訂單 / 認證與 5/10/20 日續航，而不是只重算既有 top picks。",
    ]
    report["changesComparedToPrevious"] = {
        "summary": "這次用官方價格、法人、供應鏈底圖與 MOPS 近 30 日事件重新建池，前五題材與主選股都允許脫離上一版結果。",
        "items": [
            {
                "title": "前五題材重新由官方價格 + 供應鏈底圖建池",
                "reason": f"上一版主線為 {'、'.join(before_themes)}；這版重建後為 {'、'.join(after_themes)}。",
            },
            {
                "title": "主選股重新由 stockScore 決定",
                "reason": f"上一版主選股為 {'、'.join(before_picks)}；這版重建後為 {'、'.join(after_picks)}。",
            },
            {
                "title": "macro / eventRisk 仍沿用已驗證值",
                "reason": "這次新腳本重建的核心是價格、法人、供應鏈與 MOPS 路徑；macro 與地緣仍用上一版已驗證數值，避免在未腳本化前硬猜。",
            },
        ],
    }
    report["sources"] = [
        {
            "label": f"TWSE {price_date} MI_INDEX",
            "url": f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={price_date:%Y%m%d}&type=ALLBUT0999",
        },
        {
            "label": f"TWSE {price_date} T86",
            "url": f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={price_date:%Y%m%d}&selectType=ALLBUT0999",
        },
        {
            "label": f"TWSE {price_date} BFI82U",
            "url": f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json&dayDate={price_date:%Y%m%d}&type=day",
        },
        {
            "label": f"TPEX {price_date} 日行情",
            "url": f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={price_date:%Y/%m/%d}&response=json",
        },
        {
            "label": f"TPEX {price_date} 三大法人",
            "url": f"https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?date={price_date:%Y/%m/%d}&type=Daily&response=json",
        },
        {
            "label": "MOPS 歷史重大訊息 / 明細 API",
            "url": "https://mops.twse.com.tw/mops/#/web/t05st01",
        },
        {
            "label": "台股供應鏈底圖 JSON",
            "url": "https://dyes00003.github.io/tw-stock-morning-brief/site/data/tw_stock_supply_chain_tags.json",
        },
    ]
    report["footnote"] = (
        "本版已從官方價格、官方法人、供應鏈底圖與官方 MOPS 路徑重建題材與個股排序；"
        "但 macro 與 geopolitics 的 full rediscovery 目前仍有一部分沿用上一版已驗證數值。"
    )
    report["priceModel"] = {
        "version": "20d_continuation_v2_from_source",
        "label": "20 交易日續航價位模型",
        "basis": "30d company events + revenue/earnings acceleration + order/qualification + 5/10/20 persistence + short impulse",
        "summary": "entry / target / stop 已經改成 from-source 重建版月內價位模型。",
    }
    return report, write_log(
        template,
        report,
        price_date,
        window_3d,
        stock_info_map,
        candidate_rows,
        trade_themes,
        observation_themes,
    )


def write_log(
    before_report: dict[str, Any],
    after_report: dict[str, Any],
    price_date: date,
    window_dates: list[date],
    stock_info_map: dict[str, dict[str, Any]],
    candidate_rows: dict[str, PriceRow],
    themes: list[dict[str, Any]],
    observation_themes: list[dict[str, Any]],
) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = now_local().strftime("%Y-%m-%d_%H-%M-%S")
    path = LOG_DIR / f"{timestamp}.md"
    lines = [
        "# From-Source Morning Brief Rebuild",
        "",
        f"- Run timestamp: {now_local().isoformat()}",
        f"- Report date: {after_report['reportDate']}",
        f"- Price date: {after_report['priceDate']}",
        "- Rebuild scope: official TWSE / TPEX prices, T86, BFI82U, TPEX institution flows, supply-chain tag JSON, MOPS t05st01 / detail APIs.",
        "- Carried-forward scope: macroDrivers narrative and marketRegime macro / eventRisk buckets remain inherited from the prior verified brief unless separately scripted.",
        "",
        "## Windows",
        "",
        f"- 3-day MOPS hybrid window: {', '.join(iso(d) for d in window_dates)}",
        f"- Candidate stock universe rebuilt from {len(candidate_rows)} official-price names with supply-chain matches.",
        "",
        "## Theme Ranking",
        "",
    ]
    for theme in themes:
        lines.append(
            f"- {theme['rank']}. {theme['name']} | score {theme['themeScore']} | state {theme['state']} | RS20 {theme['breadthStats']['relativeStrength20d']} | company spread {theme['scoreBreakdown']['companyEvidenceSpreadScore']}"
        )
    if observation_themes:
        lines.extend(["", "## Observation Themes", ""])
        for theme in observation_themes[:5]:
            lines.append(
                f"- {theme['name']} | score {theme['themeScore']} | state {theme['state']} | category {theme.get('observationCategory', 'n/a')}"
            )
    lines.extend(["", "## Major Stock Evidence", ""])
    for ticker, info in sorted(
        stock_info_map.items(),
        key=lambda kv: (
            kv[1]["material_score"],
            kv[1]["revenue_score"],
            kv[1]["order_score"],
        ),
        reverse=True,
    )[:15]:
        lines.append(
            f"- {ticker} {candidate_rows[ticker].name}: material30d {info['material_score']}, revenue {info['revenue_score']}, order {info['order_score']}, mops3d {info['mops3d_score']} | {info['material_summary']}"
        )
    lines.extend(
        [
            "",
            "## Output Notes",
            "",
            "- This run rebuilt themes / stocks / top picks from official price and MOPS data instead of re-sorting the previous latest.json theme list.",
            "- Macro / geopolitical full rediscovery is still not fully scripted here; those buckets are explicitly carried forward.",
            "",
            "## Files Updated",
            "",
            f"- {LATEST_JSON}",
            f"- {path}",
        ]
    )
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> None:
    report, log_path = build_report()
    save_json(LATEST_JSON, report)
    print(str(log_path))


if __name__ == "__main__":
    main()
