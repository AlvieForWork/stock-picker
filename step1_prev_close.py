"""
Step 1: 測前一交易日收盤資料
用 Polygon/Massive 免費 API 的 /v2/aggs/ticker/{ticker}/prev 端點，
抓 AAPL、TSLA、NVDA 前一交易日的開高低收和成交量。
這是歷史資料端點，免費層可用，休市時也能測。

執行方式：
    python3 step1_prev_close.py
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("POLYGON_API_KEY")
BASE_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/prev"
TICKERS = ["AAPL", "TSLA", "NVDA"]


def fetch_prev_close(ticker: str):
    url = BASE_URL.format(ticker=ticker)
    params = {"adjusted": "true", "apiKey": API_KEY}
    resp = requests.get(url, params=params, timeout=10)
    return resp


def main():
    if not API_KEY or API_KEY == "your_key_here":
        print("錯誤：.env 裡沒有讀到有效的 POLYGON_API_KEY，請檢查 .env 檔案內容。")
        return

    for ticker in TICKERS:
        print(f"\n--- {ticker} ---")
        resp = fetch_prev_close(ticker)

        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results")
            if not results:
                print(f"回傳 200 但沒有資料，完整回應：{data}")
                continue
            bar = results[0]
            print(f"日期時間戳: {bar.get('t')}")
            print(f"開盤 (o): {bar.get('o')}")
            print(f"最高 (h): {bar.get('h')}")
            print(f"最低 (l): {bar.get('l')}")
            print(f"收盤 (c): {bar.get('c')}")
            print(f"成交量 (v): {bar.get('v')}")
        elif resp.status_code == 401:
            print("401 未授權：API key 錯誤或無效，請確認 .env 裡的 POLYGON_API_KEY 是否正確。")
        elif resp.status_code == 403:
            print("403 禁止存取：key 有效，但這個端點/資料超出你的方案權限。")
        elif resp.status_code == 429:
            print("429 太多請求：免費層每分鐘最多 5 次呼叫，已超過限制，請稍等再試。")
        else:
            print(f"未預期的錯誤，狀態碼 {resp.status_code}，內容：{resp.text}")


if __name__ == "__main__":
    main()
