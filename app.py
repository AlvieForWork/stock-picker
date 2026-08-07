import os
from datetime import date, datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request

from candlestick import analyze_latest_candle, build_chart_series

load_dotenv()

API_KEY = os.getenv("POLYGON_API_KEY")
AGGS_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"

app = Flask(__name__)


def fetch_daily_bars(ticker: str):
    """
    回傳 (bars, error_message)。成功時 error_message 為 None。
    bars 是由舊到新排序的 list，每筆為 {"t","o","h","l","c","v"}（t 是 "YYYY-MM-DD"）。

    往回抓約 260 個日曆天，是為了讓圖表上「每一根蠟燭」都能算出自己的 60MA
    （最早顯示的那根蠟燭，也需要往前 60 個交易日的資料），跟 90 根蠟燭合起來
    大約要 150 個交易日，260 個日曆天含假日週末後綽綽有餘。
    這仍然只是同一支 API 呼叫，只是放寬日期區間，不會增加呼叫次數。
    """
    end = date.today()
    start = end - timedelta(days=260)

    url = AGGS_URL.format(ticker=ticker, start=start.isoformat(), end=end.isoformat())
    params = {"adjusted": "true", "sort": "asc", "limit": 300, "apiKey": API_KEY}

    try:
        resp = requests.get(url, params=params, timeout=10)
    except requests.RequestException as e:
        return None, f"連線失敗：{e}"

    if resp.status_code == 401:
        return None, "API key 無效，請確認 .env 裡的 POLYGON_API_KEY 是否正確。"
    if resp.status_code == 403:
        return None, "權限不足：這個資料超出免費方案範圍。"
    if resp.status_code == 429:
        return None, "已達免費方案每分鐘 5 次呼叫上限，請稍等一分鐘再查詢。"
    if resp.status_code != 200:
        return None, f"查詢發生錯誤（狀態碼 {resp.status_code}），請稍後再試。"

    data = resp.json()
    results = data.get("results")
    if not results:
        return None, f"查不到「{ticker}」這個美股代號，請確認拼寫是否正確（例如 AAPL、TSLA）。"

    bars = [
        {
            "t": datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc).date().isoformat(),
            "o": r["o"],
            "h": r["h"],
            "l": r["l"],
            "c": r["c"],
            "v": r["v"],
        }
        for r in results
    ]
    return bars, None


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    chart_data = None
    error = None
    ticker = ""

    if request.method == "POST":
        ticker = request.form.get("ticker", "").strip().upper()

        if not ticker:
            error = "請輸入美股代號。"
        elif not API_KEY or API_KEY == "your_key_here":
            error = ".env 裡沒有設定有效的 POLYGON_API_KEY。"
        else:
            bars, fetch_error = fetch_daily_bars(ticker)
            if fetch_error:
                error = fetch_error
            else:
                try:
                    result = analyze_latest_candle(bars)
                    chart_data = build_chart_series(bars)
                except ValueError as e:
                    error = str(e)

    return render_template(
        "index.html", result=result, chart_data=chart_data, error=error, ticker=ticker
    )


if __name__ == "__main__":
    app.run(debug=True, port=5002)
