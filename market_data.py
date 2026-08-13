"""
指數／ETF 的資料抓取與快取。

為什麼要有這個檔案：免費 API 每分鐘只能呼叫 5 次，但這個網站有好幾頁都要用到
同一批標的（大盤頁、產業頁、首頁）。所以統一在這裡抓，抓過的當天就存起來，
其他頁面直接拿快取，不會為了同一份資料重複打 API。

快取存成一個 JSON 檔（cache/market_data.json），內容長這樣：
  { "I:COMP": { "fetched_on": "2026-08-13", "bars": [ {...}, {...} ] }, ... }
「當天抓過就不再抓」——因為資料是每日收盤，一天內重抓也不會變。
"""

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("POLYGON_API_KEY")
AGGS_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_FILE = CACHE_DIR / "market_data.json"

# 免費方案每分鐘 5 次。留一點餘裕設 4，避免跟個股查詢的呼叫撞在一起剛好爆掉。
MAX_CALLS_PER_MINUTE = 4

# 記錄最近幾次呼叫 API 的時間（單位：秒），用來判斷要不要先等一下再打下一次。
_recent_call_times = []


# ── 這個網站要追蹤的標的 ──────────────────────────────────────────
# kind 標示這是「真指數」還是「ETF 替代」，頁面上要讓使用者看得出來差別。
#
# 2026-08-13 實測結果：
#   I:COMP（那斯達克綜合）→ 200 有資料 ✅
#   I:SOX （費城半導體）  → 200 有資料 ✅
#   I:SPX （標普500）     → 403 NOT_AUTHORIZED ❌ 免費層不含，改用 SPY ETF 替代
MARKET_TICKERS = [
    {
        "ticker": "I:COMP",
        "name": "那斯達克綜合指數",
        "short": "那斯達克",
        "kind": "index",
        "kind_label": "指數",
    },
    {
        "ticker": "I:SOX",
        "name": "費城半導體指數",
        "short": "費半",
        "kind": "index",
        "kind_label": "指數",
    },
    {
        "ticker": "SPY",
        "name": "SPDR 標普500 ETF",
        "short": "標普500",
        "kind": "etf",
        "kind_label": "ETF 替代",
        "note": "免費方案不含標普500指數（I:SPX）授權，改用追蹤同一指數的 SPY ETF。",
    },
]


def _load_cache():
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # 快取壞掉不該讓整個網站掛掉，當作沒有快取重抓就好
        return {}


def _save_cache(cache):
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except OSError:
        # 寫不進去（例如雲端主機檔案系統唯讀）只是少了快取，不影響這次的結果
        pass


def _wait_for_rate_limit():
    """
    打 API 前先確認這一分鐘內還有額度。若已經打滿，就等到最舊那次呼叫滿一分鐘為止。
    """
    now = time.time()
    # 只保留最近 60 秒內的紀錄
    _recent_call_times[:] = [t for t in _recent_call_times if now - t < 60]

    if len(_recent_call_times) >= MAX_CALLS_PER_MINUTE:
        wait_seconds = 60 - (now - _recent_call_times[0]) + 0.5
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        now = time.time()
        _recent_call_times[:] = [t for t in _recent_call_times if now - t < 60]

    _recent_call_times.append(time.time())


def _fetch_bars(ticker, days_back=260):
    """
    實際打一次 API 抓日 K。回傳 (bars, error_message)。

    days_back 預設 260 個日曆天（約 180 個交易日），夠畫 90 個交易日的圖，
    也夠算近 1 月漲跌幅，還留了緩衝。
    """
    if not API_KEY or API_KEY == "your_key_here":
        return None, ".env 裡沒有設定有效的 POLYGON_API_KEY。"

    end = date.today()
    start = end - timedelta(days=days_back)
    url = AGGS_URL.format(ticker=ticker, start=start.isoformat(), end=end.isoformat())
    params = {"adjusted": "true", "sort": "asc", "limit": 400, "apiKey": API_KEY}

    _wait_for_rate_limit()

    try:
        resp = requests.get(url, params=params, timeout=15)
    except requests.RequestException as e:
        return None, f"連線失敗：{e}"

    if resp.status_code == 429:
        return None, "已達免費方案每分鐘 5 次呼叫上限，請稍等一分鐘再重新整理。"
    if resp.status_code == 403:
        return None, f"免費方案沒有「{ticker}」的資料權限。"
    if resp.status_code != 200:
        return None, f"抓取「{ticker}」失敗（狀態碼 {resp.status_code}）。"

    results = resp.json().get("results")
    if not results:
        return None, f"查不到「{ticker}」的資料。"

    bars = [
        {
            "t": datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc).date().isoformat(),
            "o": r["o"],
            "h": r["h"],
            "l": r["l"],
            "c": r["c"],
            "v": r.get("v", 0),
        }
        for r in results
    ]
    return bars, None


def get_bars(ticker, force_refresh=False):
    """
    取得某個標的的日 K。當天抓過就直接用快取，不重打 API。

    回傳 (bars, error_message, is_from_cache)。
    若 API 掛了但有舊快取，會回傳舊快取並附上錯誤訊息，讓畫面至少有東西可看。
    """
    cache = _load_cache()
    today = date.today().isoformat()
    entry = cache.get(ticker)

    if not force_refresh and entry and entry.get("fetched_on") == today:
        return entry["bars"], None, True

    bars, error = _fetch_bars(ticker)

    if error:
        if entry and entry.get("bars"):
            # 抓失敗但有舊資料，先用舊的頂著，並把錯誤一起回傳讓畫面提示
            return entry["bars"], error, True
        return None, error, False

    cache[ticker] = {"fetched_on": today, "bars": bars}
    _save_cache(cache)
    return bars, None, False


def pct_change(bars, trading_days_ago):
    """
    算「最新收盤」對「N 個交易日前收盤」的漲跌幅（%）。
    資料不足回傳 None，畫面上會顯示成「—」而不是假裝有數字。
    """
    if not bars or len(bars) < trading_days_ago + 1:
        return None
    latest = bars[-1]["c"]
    past = bars[-(trading_days_ago + 1)]["c"]
    if not past:
        return None
    return (latest - past) / past * 100


def build_line_series(bars, display_count=90):
    """把日 K 整理成畫折線圖用的序列，只取最後 display_count 根。"""
    recent = bars[-display_count:] if len(bars) > display_count else bars
    return [{"time": b["t"], "value": round(b["c"], 2)} for b in recent]


def get_market_overview(display_count=90):
    """
    大盤頁要的完整資料：三個標的各自的最新價、各期間漲跌幅、走勢圖序列。

    回傳 (items, data_date, errors)：
      items      —— 每個標的一筆，含價格與圖表資料
      data_date  —— 資料日期（取最新一根 K 的日期）
      errors     —— 抓取過程的錯誤訊息 list，畫面上提示用
    """
    items = []
    errors = []
    data_date = None

    for meta in MARKET_TICKERS:
        bars, error, from_cache = get_bars(meta["ticker"])

        if error:
            errors.append(f"{meta['short']}：{error}")
        if not bars:
            items.append({**meta, "available": False})
            continue

        latest = bars[-1]
        prev_close = bars[-2]["c"] if len(bars) >= 2 else None
        day_pct = ((latest["c"] - prev_close) / prev_close * 100) if prev_close else None

        if data_date is None or latest["t"] > data_date:
            data_date = latest["t"]

        items.append({
            **meta,
            "available": True,
            "close": latest["c"],
            "day_pct": day_pct,
            "week_pct": pct_change(bars, 5),      # 近 1 週 ≈ 5 個交易日
            "month_pct": pct_change(bars, 21),    # 近 1 月 ≈ 21 個交易日
            "series": build_line_series(bars, display_count),
            "bar_date": latest["t"],
            "from_cache": from_cache,
        })

    return items, data_date, errors
