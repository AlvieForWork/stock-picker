"""
K 棒型態判斷邏輯。

輸入：由舊到新排序的日 K 資料 list，每筆至少要有 o/h/l/c/v（開高低收量）。
輸出：dict，包含最新一根 K 棒的型態標籤、參考說明，以及所有中間計算值。
"""

# 每個型態標籤對應的白話解釋，給完全沒學過股票的人看，不用術語。
TAG_EXPLANATIONS = {
    "中長紅K": "這天大漲，而且漲勢很有力，買方明顯佔上風。",
    "中長黑K": "這天大跌，而且跌勢很有力，賣方明顯佔上風。",
    "小紅K": "這天漲跌都不多，買賣雙方力量差不多，方向不明朗。",
    "小黑K": "這天漲跌都不多，買賣雙方力量差不多，方向不明朗。",
    "十字線": "這天開盤和收盤價幾乎一樣，買賣雙方力量打平，方向不明朗。",
    "帶長上影線": "這天股價一度衝高，但碰到「天花板」被壓了回來。這個天花板叫「賣壓」，"
                  "意思是漲到那個價位就有很多人想賣，讓股價比較難再往上。",
    "帶長下影線": "這天股價一度跌深，但碰到「地板」被買了回來。這個地板叫「支撐」，"
                  "意思是跌到那個價位就有很多人想買，讓股價比較難再往下。",
    "爆大量": "這天成交量比平常大很多，代表這天特別多人在交易，市場很關注它。",
    "高檔": "股價已經漲得比它最近的平均價高出很多（超過 30%），位置偏高，"
            "要留意漲多之後可能回檔（往回跌一點）。",
}

# 紅漲綠跌，跟型態標籤的顏色（.pill-red / .pill-green）一致。
# 色值取自 E8D 設計系統的語意色階：紅漲＝Error 700，綠跌＝Success 700。
CHART_UP_COLOR = "#EC2D30"
CHART_DOWN_COLOR = "#0C9D61"


def analyze_latest_candle(bars):
    """
    bars: list of dict，由舊到新排序，每筆包含 o, h, l, c, v（開高低收量）。
    至少要有 61 筆才能算 60MA；至少要有 6 筆才能算前 5 日均量。
    """
    if len(bars) < 61:
        raise ValueError(f"資料筆數不足，需要至少 61 根日K才能算 60MA，目前只有 {len(bars)} 根")

    latest = bars[-1]
    o, h, l, c, v = latest["o"], latest["h"], latest["l"], latest["c"], latest["v"]

    body = abs(c - o)
    day_range = h - l
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l

    body_ratio = body / day_range if day_range > 0 else 0

    prev_5_bars = bars[-6:-1]
    avg_vol_5 = sum(b["v"] for b in prev_5_bars) / len(prev_5_bars)
    volume_multiple = v / avg_vol_5 if avg_vol_5 > 0 else 0

    ma60_bars = bars[-60:]
    ma60 = sum(b["c"] for b in ma60_bars) / len(ma60_bars)
    bias_pct = (c - ma60) / ma60 * 100 if ma60 > 0 else 0

    is_red = c > o
    is_black = c < o

    if is_red:
        color_tag = "紅K"
    elif is_black:
        color_tag = "黑K"
    else:
        color_tag = "平盤（開收同價）"

    is_long_body = body_ratio >= 0.6
    if is_red:
        body_tag = "中長紅K" if is_long_body else "小紅K"
    elif is_black:
        body_tag = "中長黑K" if is_long_body else "小黑K"
    else:
        body_tag = "十字線"

    has_long_upper = upper_shadow >= body and body > 0
    has_long_lower = lower_shadow >= body and body > 0
    is_high_volume = v >= avg_vol_5 * 2
    is_high_bias = bias_pct >= 30

    # 型態標籤順序：高檔 > 爆大量 > 實體 > 影線（跟範例的顯示順序一致）
    ordered_tags = []
    if is_high_bias:
        ordered_tags.append("高檔")
    if is_high_volume:
        ordered_tags.append("爆大量")
    ordered_tags.append(body_tag)
    if has_long_upper:
        ordered_tags.append("帶長上影線")
    if has_long_lower:
        ordered_tags.append("帶長下影線")

    pattern_label = " + ".join(ordered_tags)

    tag_explanations = [
        {"tag": tag, "explanation": TAG_EXPLANATIONS.get(tag, "")} for tag in ordered_tags
    ]

    # 綜合傾向描述：只在有明確的高檔＋轉弱訊號組合時才給方向性的「傾向」字眼
    if is_high_bias and is_red and (is_high_volume or has_long_upper):
        tendency = "這幾個訊號合在一起看，過去統計上次日「傾向」回檔（也就是股價有機會往回跌一點）"
    elif is_high_bias and is_black:
        tendency = "這幾個訊號合在一起看，過去統計上賣方力道有機會持續，次日「傾向」偏弱"
    elif is_high_volume and has_long_upper and is_red:
        tendency = "這幾個訊號合在一起看，股價漲高後又被打了回來，過去統計上次日「傾向」震盪或回檔"
    else:
        tendency = "目前沒有明顯偏多或偏空的常見對應說法，以上僅呈現型態特徵供參考"

    explanation = tendency + "，但這是機率性訊號，不代表預測，僅供參考。"

    return {
        "pattern_label": pattern_label,
        "tags": ordered_tags,
        "tag_explanations": tag_explanations,
        "explanation": explanation,
        "metrics": {
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": round(v),
            "body": round(body, 4),
            "day_range": round(day_range, 4),
            "body_ratio": round(body_ratio, 4),
            "upper_shadow": round(upper_shadow, 4),
            "lower_shadow": round(lower_shadow, 4),
            "avg_vol_5": round(avg_vol_5, 2),
            "volume_multiple": round(volume_multiple, 2),
            "ma60": round(ma60, 4),
            "bias_pct": round(bias_pct, 2),
        },
        "flags": {
            "is_red": is_red,
            "is_black": is_black,
            "is_long_body": is_long_body,
            "has_long_upper": has_long_upper,
            "has_long_lower": has_long_lower,
            "is_high_volume": is_high_volume,
            "is_high_bias": is_high_bias,
        },
    }


def build_chart_series(bars, display_count=90, ma_window=60):
    """
    把日 K 資料整理成畫圖用的三組序列：蠟燭、成交量、60MA。

    bars: 由舊到新排序，每筆包含 t（"YYYY-MM-DD"）、o、h、l、c、v。
    只顯示最後 display_count 根蠟燭，但每一根顯示出來的蠟燭都要有自己的
    60MA 可以畫，所以起點會往前抓到「有完整 60 天可以算 MA」的地方。
    """
    if len(bars) < ma_window:
        start_index = 0
    else:
        start_index = max(ma_window - 1, len(bars) - display_count)

    candles = []
    volumes = []
    ma60 = []

    for i in range(start_index, len(bars)):
        bar = bars[i]
        candles.append({
            "time": bar["t"],
            "open": bar["o"],
            "high": bar["h"],
            "low": bar["l"],
            "close": bar["c"],
        })
        is_up = bar["c"] >= bar["o"]
        volumes.append({
            "time": bar["t"],
            "value": bar["v"],
            "color": CHART_UP_COLOR if is_up else CHART_DOWN_COLOR,
        })
        if i >= ma_window - 1:
            window = bars[i - ma_window + 1: i + 1]
            avg = sum(b["c"] for b in window) / ma_window
            ma60.append({"time": bar["t"], "value": round(avg, 4)})

    return {"candles": candles, "volumes": volumes, "ma60": ma60}
