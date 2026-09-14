import requests
import pandas as pd
import ta
from datetime import datetime

BOT_NAME = "Smart Trading Signal Bot"

SYMBOL = "BTCUSDT"
INTERVAL = "5m"
CANDLE_LIMIT = 100


def get_market_data():

    url = "https://api.kraken.com/0/public/OHLC"

    params = {
        "pair": "XBTUSD",
        "interval": 5
    }

    response = requests.get(
        url,
        params=params,
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise Exception(
            "Kraken API error: " + str(data["error"])
        )

    result = data.get("result", {})

    pair_key = next(
        (key for key in result.keys() if key != "last"),
        None
    )

    if pair_key is None:
        raise Exception("No market data received")

    candles = result[pair_key]

    # Kraken returns 8 values per candle:
    # time, open, high, low, close, vwap, volume, trades

    df = pd.DataFrame(candles, columns=[
        "time",
        "open",
        "high",
        "low",
        "close",
        "vwap",
        "volume",
        "trades"
    ])

    df["close"] = pd.to_numeric(df["close"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])

    df = df.tail(CANDLE_LIMIT).reset_index(drop=True)

    return df

def calculate_indicators(df):

    # EMA 9
    df["ema9"] = ta.trend.EMAIndicator(
        close=df["close"],
        window=9
    ).ema_indicator()

    # EMA 21
    df["ema21"] = ta.trend.EMAIndicator(
        close=df["close"],
        window=21
    ).ema_indicator()

    # RSI 14
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

    score = 0

    # EMA Trend
    if current["ema9"] > current["ema21"]:
        score += 30
    elif current["ema9"] < current["ema21"]:
        score -= 30

    # RSI Momentum
    if current["rsi"] >= 55:
        score += 25
    elif current["rsi"] <= 45:
        score -= 25

    # MACD Confirmation
    if current["macd"] > current["macd_signal"]:
        score += 30
    elif current["macd"] < current["macd_signal"]:
        score -= 30

    # RSI extreme protection
    if current["rsi"] >= 70:
        score -= 10

    if current["rsi"] <= 30:
        score += 10

    # Final decision
    if score >= 60:
        signal = "CALL"
    elif score <= -60:
        signal = "PUT"
    else:
        signal = "WAIT"

    confidence = min(abs(score), 100)

    return signal, score, confidence

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

        if len(df) < 30:
            raise Exception(
                "Not enough candle data received"
            )

        df = calculate_indicators(df)

        signal, score, confidence = generate_signal(df)

        current = df.iloc[-1]

        print("-" * 50)
        print("Time:", datetime.now())
        print("Price:", round(current["close"], 4))
        print("EMA 9:", round(current["ema9"], 4))
        print("EMA 21:", round(current["ema21"], 4))
        print("RSI:", round(current["rsi"], 2))
        print("MACD:", round(current["macd"], 5))
        print(
            "MACD Signal:",
            round(current["macd_signal"], 5)
        )
        print("SIGNAL:", signal)
        print("SCORE:", score)
print("CONFIDENCE:", str(confidence) + "%")
        print("-" * 50)

    except Exception as e:

        print("ERROR:", e)


if __name__ == "__main__":
    main()
