import requests
import pandas as pd
import numpy as np
from datetime import datetime

# ============================================================
# Smart Trading Signal Bot - Backtest V13
# ============================================================

BOT_NAME = "Smart Trading Signal Bot V13"

SYMBOL = "BTCUSDT"
INTERVAL = "5m"

# عدد الشموع المستخدمة في الاختبار
LIMIT = 1000

# إعدادات المؤشرات
EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 50

RSI_PERIOD = 14
RSI_BUY_MIN = 50
RSI_BUY_MAX = 70
RSI_SELL_MIN = 30
RSI_SELL_MAX = 50

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# إعدادات الصفقة
EXPIRY_CANDLES = 1

# ============================================================
# تحميل البيانات
# ============================================================

def get_data():
    url = "https://api.binance.com/api/v3/klines"

    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "limit": LIMIT
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()

    columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "trades",
        "buy_volume",
        "buy_quote_volume",
        "ignore"
    ]

    df = pd.DataFrame(data, columns=columns)

    df["open"] = pd.to_numeric(df["open"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])
    df["close"] = pd.to_numeric(df["close"])
    df["volume"] = pd.to_numeric(df["volume"])

    df["time"] = pd.to_datetime(df["open_time"], unit="ms")

    return df


# ============================================================
# المؤشرات
# ============================================================

def calculate_indicators(df):

    # EMA
    df["ema_fast"] = df["close"].ewm(
        span=EMA_FAST,
        adjust=False
    ).mean()

    df["ema_slow"] = df["close"].ewm(
        span=EMA_SLOW,
        adjust=False
    ).mean()

    df["ema_trend"] = df["close"].ewm(
        span=EMA_TREND,
        adjust=False
    ).mean()

    # RSI
    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / RSI_PERIOD,
        min_periods=RSI_PERIOD,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / RSI_PERIOD,
        min_periods=RSI_PERIOD,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss

    df["rsi"] = 100 - (100 / (1 + rs))

    # MACD
    ema_macd_fast = df["close"].ewm(
        span=MACD_FAST,
        adjust=False
    ).mean()

    ema_macd_slow = df["close"].ewm(
        span=MACD_SLOW,
        adjust=False
    ).mean()

    df["macd"] = ema_macd_fast - ema_macd_slow

    df["macd_signal"] = df["macd"].ewm(
        span=MACD_SIGNAL,
        adjust=False
    ).mean()

    df["macd_hist"] = (
        df["macd"] - df["macd_signal"]
    )

    return df


# ============================================================
# توليد الإشارة
# ============================================================

def get_signal(df, i):

    row = df.iloc[i]
    previous = df.iloc[i - 1]

    # حماية من البيانات الناقصة
    if pd.isna(row["rsi"]):
        return "WAIT", 0

    confidence = 0

    # --------------------------------------------------------
    # CALL / شراء
    # --------------------------------------------------------

    buy_conditions = 0

    if row["ema_fast"] > row["ema_slow"]:
        buy_conditions += 1
        confidence += 20

    if row["close"] > row["ema_trend"]:
        buy_conditions += 1
        confidence += 20

    if RSI_BUY_MIN <= row["rsi"] <= RSI_BUY_MAX:
        buy_conditions += 1
        confidence += 20

    if row["macd"] > row["macd_signal"]:
        buy_conditions += 1
        confidence += 20

    if row["macd_hist"] > previous["macd_hist"]:
        buy_conditions += 1
        confidence += 20

    if buy_conditions >= 4:
        return "CALL", confidence

    # --------------------------------------------------------
    # PUT / بيع
    # --------------------------------------------------------

    sell_conditions = 0
    confidence = 0

    if row["ema_fast"] < row["ema_slow"]:
        sell_conditions += 1
        confidence += 20

    if row["close"] < row["ema_trend"]:
        sell_conditions += 1
        confidence += 20

    if RSI_SELL_MIN <= row["rsi"] <= RSI_SELL_MAX:
        sell_conditions += 1
        confidence += 20

    if row["macd"] < row["macd_signal"]:
        sell_conditions += 1
        confidence += 20

    if row["macd_hist"] < previous["macd_hist"]:
        sell_conditions += 1
        confidence += 20

    if sell_conditions >= 4:
        return "PUT", confidence

    return "WAIT", 0


# ============================================================
# تنفيذ Backtest
# ============================================================

def run_backtest(df):

    trades = []

    start_index = max(
        EMA_TREND,
        MACD_SLOW,
        RSI_PERIOD
    ) + 2

    for i in range(start_index, len(df) - EXPIRY_CANDLES):

        signal, confidence = get_signal(df, i)

        if signal == "WAIT":
            continue

        entry_price = df.iloc[i]["close"]

        exit_index = i + EXPIRY_CANDLES

        exit_price = df.iloc[exit_index]["close"]

        if signal == "CALL":

            if exit_price > entry_price:
                result = "WIN"
            else:
                result = "LOSS"

        elif signal == "PUT":

            if exit_price < entry_price:
                result = "WIN"
            else:
                result = "LOSS"

        trades.append({
            "time": df.iloc[i]["time"],
            "signal": signal,
            "confidence": confidence,
            "entry": entry_price,
            "exit": exit_price,
            "result": result
        })

    return pd.DataFrame(trades)


# ============================================================
# تحليل النتائج
# ============================================================

def analyze_results(trades):

    if trades.empty:
        print("\nNo trades found.")
        return

    total = len(trades)

    wins = len(
        trades[trades["result"] == "WIN"]
    )

    losses = len(
        trades[trades["result"] == "LOSS"]
    )

    win_rate = (wins / total) * 100

    print("\n==================================================")
    print("BACKTEST RESULTS")
    print("==================================================")

    print("Total Trades :", total)
    print("Wins         :", wins)
    print("Losses       :", losses)

    print(
        "Win Rate     :",
        f"{win_rate:.2f}%"
    )

    print(
        "Average Confidence :",
        f"{trades['confidence'].mean():.2f}%"
    )

    call_trades = trades[
        trades["signal"] == "CALL"
    ]

    put_trades = trades[
        trades["signal"] == "PUT"
    ]

    # CALL statistics
    if len(call_trades) > 0:

        call_wins = len(
            call_trades[
                call_trades["result"] == "WIN"
            ]
        )

        call_rate = (
            call_wins / len(call_trades)
        ) * 100

        print("\nCALL Trades :", len(call_trades))
        print(
            "CALL Win Rate :",
            f"{call_rate:.2f}%"
        )

    # PUT statistics
    if len(put_trades) > 0:

        put_wins = len(
            put_trades[
                put_trades["result"] == "WIN"
            ]
        )

        put_rate = (
            put_wins / len(put_trades)
        ) * 100

        print("\nPUT Trades :", len(put_trades))
        print(
            "PUT Win Rate :",
            f"{put_rate:.2f}%"
        )

    # ========================================================
    # سلسلة الخسائر
    # ========================================================

    max_loss_streak = 0
    current_loss_streak = 0

    for result in trades["result"]:

        if result == "LOSS":

            current_loss_streak += 1

            max_loss_streak = max(
                max_loss_streak,
                current_loss_streak
            )

        else:
            current_loss_streak = 0

    print(
        "\nMax Consecutive Losses :",
        max_loss_streak
    )

    # ========================================================
    # سلسلة الأرباح
    # ========================================================

    max_win_streak = 0
    current_win_streak = 0

    for result in trades["result"]:

        if result == "WIN":

            current_win_streak += 1

            max_win_streak = max(
                max_win_streak,
                current_win_streak
            )

        else:
            current_win_streak = 0

    print(
        "Max Consecutive Wins   :",
        max_win_streak
    )

    # ========================================================
    # تقييم بسيط
    # ========================================================

    print("\n==================================================")
    print("STRATEGY EVALUATION")
    print("==================================================")

    if win_rate >= 65:
        print("STATUS: VERY STRONG")

    elif win_rate >= 58:
        print("STATUS: PROMISING")

    elif win_rate >= 52:
        print("STATUS: WEAK EDGE")

    else:
        print("STATUS: NOT PROFITABLE")

    print("==================================================")


# ============================================================
# Main
# ============================================================

def main():

    print("==================================================")
    print(BOT_NAME)
    print("==================================================")

    print("Symbol   :", SYMBOL)
    print("Timeframe:", INTERVAL)
    print("Candles  :", LIMIT)

    try:

        print("\nDownloading market data...")

        df = get_data()

        print(
            "Downloaded:",
            len(df),
            "candles"
        )

       
