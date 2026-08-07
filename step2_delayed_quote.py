"""
Step 2: 測延遲 15 分鐘的報價端點
用 Polygon/Massive 的「最新成交」端點 /v2/last/trade/{ticker}。
免費層拿到的資料本身就是延遲 15 分鐘（不是換一個「delayed」專用端點，
是同一個端點，免費方案的資料本來就慢 15 分鐘）。

現在是台灣時間平日下午，美股還沒開盤，這時候測會是：
  - 200 但資料是「上一個交易日收盤前最後一筆成交」（沒有意義，因為當天還沒開盤）
  - 或 403，代表免費層根本沒有這個端點的權限（這是常見情況，要注意看）

怎麼判斷測試有沒有意義：
  1. 美股開盤時間＝台灣時間晚上 9:30（夏令時間，目前 8 月適用）
  2. 開盤後「至少等 15 分鐘以上」再跑這支腳本，例如晚上 9:50 之後
     （太早跑會抓到開盤前的舊資料，看起來像沒延遲，其實只是還沒到）
  3. 執行方式：
         python3 step2_delayed_quote.py
  4. 看輸出的時間戳（t，是 unix 奈秒），換算成台灣時間，
     跟你實際執行的時間比較，差距應該接近 15 分鐘（或更多，免費層是「至少」延遲 15 分鐘）
"""

import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("POLYGON_API_KEY")
BASE_URL = "https://api.polygon.io/v2/last/trade/{ticker}"
TICKERS = ["AAPL", "TSLA", "NVDA"]


def fetch_last_trade(ticker: str):
    url = BASE_URL.format(ticker=ticker)
    params = {"apiKey": API_KEY}
    return requests.get(url, params=params, timeout=10)


def main():
    if not API_KEY or API_KEY == "your_key_here":
        print("錯誤：.env 裡沒有讀到有效的 POLYGON_API_KEY，請檢查 .env 檔案內容。")
        return

    now = datetime.now(timezone.utc).astimezone()
    print(f"現在執行時間: {now.isoformat()}")

    for ticker in TICKERS:
        print(f"\n--- {ticker} ---")
        resp = fetch_last_trade(ticker)

        if resp.status_code == 200:
            data = resp.json()
            result = data.get("results")
            if not result:
                print(f"回傳 200 但沒有資料，完整回應：{data}")
                continue
            ts_ns = result.get("t")
            if ts_ns:
                trade_time = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc).astimezone()
                delay = now - trade_time
                print(f"成交時間: {trade_time.isoformat()}")
                print(f"與現在時間差: {delay}")
            print(f"價格 (p): {result.get('p')}")
            print(f"股數 (s): {result.get('s')}")
        elif resp.status_code == 401:
            print("401 未授權：API key 錯誤或無效。")
        elif resp.status_code == 403:
            print("403 禁止存取：免費層沒有這個端點的權限（常見於即時/延遲報價類端點）。")
        elif resp.status_code == 429:
            print("429 太多請求：免費層每分鐘最多 5 次呼叫，已超過限制，請稍等再試。")
        else:
            print(f"未預期的錯誤，狀態碼 {resp.status_code}，內容：{resp.text}")


if __name__ == "__main__":
    main()
