"""
Step 3: 測基本面資料（P/E、ROE、負債比）
Polygon/Massive 免費層的 /vX/reference/financials 端點「有開放」，
但它給的是原始財報數字（income statement / balance sheet / cash flow），
不是算好的比率，所以要自己算：

  P/E  = 收盤價 / 每股盈餘 (diluted_earnings_per_share)
  ROE  = 淨利 (net_income_loss) / 股東權益 (equity)
  負債比 = 總負債 (liabilities) / 總資產 (assets)

收盤價沿用 step1 用的 /v2/aggs/ticker/{ticker}/prev 端點（免費層可用）。

執行方式：
    python3 step3_fundamentals.py
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("POLYGON_API_KEY")
FINANCIALS_URL = "https://api.polygon.io/vX/reference/financials"
PREV_CLOSE_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/prev"
TICKERS = ["AAPL", "TSLA", "NVDA"]


def fetch_financials(ticker: str):
    params = {"ticker": ticker, "timeframe": "ttm", "apiKey": API_KEY}
    return requests.get(FINANCIALS_URL, params=params, timeout=10)


def fetch_prev_close(ticker: str):
    url = PREV_CLOSE_URL.format(ticker=ticker)
    params = {"adjusted": "true", "apiKey": API_KEY}
    return requests.get(url, params=params, timeout=10)


def get_value(item):
    """財報欄位是 {"value": ..., "unit": ..., "label": ...} 這種格式，取 value。"""
    if item is None:
        return None
    return item.get("value")


def main():
    if not API_KEY or API_KEY == "your_key_here":
        print("錯誤：.env 裡沒有讀到有效的 POLYGON_API_KEY，請檢查 .env 檔案內容。")
        return

    for ticker in TICKERS:
        print(f"\n--- {ticker} ---")

        fin_resp = fetch_financials(ticker)
        if fin_resp.status_code == 403:
            print("403：免費層沒有財報端點權限。")
            continue
        elif fin_resp.status_code == 429:
            print("429：超過每分鐘 5 次呼叫限制，請稍等再試。")
            continue
        elif fin_resp.status_code != 200:
            print(f"財報端點錯誤，狀態碼 {fin_resp.status_code}，內容：{fin_resp.text}")
            continue

        fin_data = fin_resp.json()
        results = fin_data.get("results")
        if not results:
            print("財報端點回傳 200 但沒有資料。")
            continue

        financials = results[0]["financials"]
        income = financials.get("income_statement", {})
        balance = financials.get("balance_sheet", {})

        eps = get_value(income.get("diluted_earnings_per_share"))
        net_income = get_value(income.get("net_income_loss"))
        equity = get_value(balance.get("equity"))
        liabilities = get_value(balance.get("liabilities"))
        assets = get_value(balance.get("assets"))

        price_resp = fetch_prev_close(ticker)
        price = None
        if price_resp.status_code == 200:
            price_results = price_resp.json().get("results")
            if price_results:
                price = price_results[0].get("c")

        print(f"每股盈餘 EPS (diluted): {eps}")
        print(f"淨利: {net_income}")
        print(f"股東權益: {equity}")
        print(f"總負債: {liabilities}")
        print(f"總資產: {assets}")
        print(f"前一交易日收盤價: {price}")

        if price is not None and eps not in (None, 0):
            pe_ratio = price / eps
            print(f"本益比 P/E: {pe_ratio:.2f}")
        else:
            print("本益比 P/E: 無法計算（缺價格或 EPS）")

        if net_income is not None and equity not in (None, 0):
            roe = net_income / equity
            print(f"ROE: {roe:.2%}")
        else:
            print("ROE: 無法計算（缺淨利或股東權益）")

        if liabilities is not None and assets not in (None, 0):
            debt_ratio = liabilities / assets
            print(f"負債比: {debt_ratio:.2%}")
        else:
            print("負債比: 無法計算（缺負債或資產）")


if __name__ == "__main__":
    main()
