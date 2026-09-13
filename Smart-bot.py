import requests
import pandas as pd
import ta
import time
from datetime import datetime

BOT_NAME = "Smart Trading Signal Bot"

SYMBOL = "BTCUSDT"
INTERVAL = "5m"
CANDLE_LIMIT = 100


def get_market_data():
    url = "https://api.binance.com/api/v3/klines"

    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "limit": CANDLE_LIMIT
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    df = pd.DataFrame(data, columns=[
        "time",
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
    ])

    df["close"] = pd.to_numeric(df["close"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])

    return df


def calculate_indicators(df):

    # EMA
    df["ema9"] = ta.trend.EMAIndicator(
        close=df["close"],
        window=9
    ).ema_indicator()

    df["ema21"] = ta.trend.EMAIndicator(
        close=df["close"],
        window=21
    ).ema_indicator()

    # RSI
    df["rsi"] = ta.momentum.RSIIndicator(
        close=df["close"],
        window=14
    ).rsi()

    # MACD
    macd = ta.trend.MACD(
        close=df["close"],
        window_slow=26,
        window_fast=12,
        window_sign=9
    )

    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    return df


def generate_signal(df):

    current = df.iloc[-1]

    bullish = (
        current["ema9"] > current["ema21"]
        and current["rsi"] > 50
        and current["macd"] > current["macd_signal"]
    )

    bearish = (
        current["ema9"] < current["ema21"]
        and current["rsi"] < 50
        and current["macd"] < current["macd_signal"]
    )

    if bullish:
        return "CALL"

    if bearish:
        return "PUT"

    return "WAIT"


def main():

    print("=" * 50)
    print(BOT_NAME)
    print("=" * 50)
    print("Symbol:", SYMBOL)
    print("Timeframe:", INTERVAL)
    print("Bot started:", datetime.now())
    print()

 try:

            df = get_market_data()
            df = calculate_indicators(df)

            signal = generate_signal(df)
            current = df.iloc[-1]

            print("-" * 50)
            print("Time:", datetime.now())
            print("Price:", round(current["close"], 4))
            print("EMA 9:", round(current["ema9"], 4))
            print("EMA 21:", round(current["ema21"], 4))
            print("RSI:", round(current["rsi"], 2))
            print("MACD:", round(current["macd"], 5))
            print("MACD Signal:", round(current["macd_signal"], 5))
            print("SIGNAL:", signal)
except Exception as e:
            print("ERROR:", e)

        


if __name__ == "__main__":
    main()
