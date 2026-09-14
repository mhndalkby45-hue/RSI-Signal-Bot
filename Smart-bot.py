import requests
import pandas as pd
import ta
from datetime import datetime


# ==================================================
# SMART TRADING SIGNAL BOT
# ==================================================

BOT_NAME = "Smart Trading Signal Bot"

# Symbol displayed by the bot
SYMBOL = "BTCUSD"

# Kraken market
KRAKEN_PAIR = "XBTUSD"

# Timeframe
INTERVAL = "5m"
KRAKEN_INTERVAL = 5

# Number of candles
CANDLE_LIMIT = 100


# ==================================================
# GET MARKET DATA
# ==================================================

def get_market_data():

    url = "https://api.kraken.com/0/public/OHLC"

    params = {
        "pair": KRAKEN_PAIR,
        "interval": KRAKEN_INTERVAL
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

    # Kraken:
    # time, open, high, low, close, vwap, volume, trades

    df = pd.DataFrame(
        candles,
        columns=[
            "time",
            "open",
            "high",
            "low",
            "close",
            "vwap",
            "volume",
            "trades"
        ]
    )

    # Convert numeric columns
    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "vwap",
        "volume"
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df.dropna().tail(
        CANDLE_LIMIT
    ).reset_index(drop=True)

    return df


# ==================================================
# CALCULATE INDICATORS
# ==================================================

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

    df["macd_hist"] = macd.macd_diff()

    return df


# ==================================================
# GENERATE SIGNAL
# ==================================================

def generate_signal(df):

    current = df.iloc[-1]

    score = 0

    # ----------------------------------------------
    # EMA TREND
    # ----------------------------------------------

    if current["ema9"] > current["ema21"]:
        score += 30

    elif current["ema9"] < current["ema21"]:
        score -= 30


    # ----------------------------------------------
    # RSI MOMENTUM
    # ----------------------------------------------

    if current["rsi"] >= 55:
        score += 25

    elif current["rsi"] <= 45:
        score -= 25


    # ----------------------------------------------
    # MACD CONFIRMATION
    # ----------------------------------------------

    if current["macd"] > current["macd_signal"]:
        score += 30

    elif current["macd"] < current["macd_signal"]:
        score -= 30


    # ----------------------------------------------
    # RSI EXTREME PROTECTION
    # ----------------------------------------------

    if current["rsi"] >= 70:
        score -= 10

    elif current["rsi"] <= 30:
        score += 10


    # ----------------------------------------------
    # FINAL SIGNAL
    # ----------------------------------------------

    if score >= 60:
        signal = "CALL"

    elif score <= -60:
        signal = "PUT"

    else:
        signal = "WAIT"


    confidence = min(abs(score), 100)

    return signal, score, confidence


# ==================================================
# MAIN
# ==================================================

def main():

    print("=" * 50)
    print(BOT_NAME)
    print("=" * 50)

    print("Symbol:", SYMBOL)
    print("Market:", KRAKEN_PAIR)
    print("Timeframe:", INTERVAL)
    print("Bot started:", datetime.now())

    print()

    try:

        # Get market data
        df = get_market_data()

        if len(df) < 30:
            raise Exception(
                "Not enough candle data received"
            )

        # Calculate indicators
        df = calculate_indicators(df)

        # Generate signal
        signal, score, confidence = generate_signal(df)

        current = df.iloc[-1]

        print("-" * 50)

        print(
            "Time:",
            datetime.now()
        )

        print(
            "Price:",
            round(current["close"], 4)
        )

        print(
            "EMA 9:",
            round(current["ema9"], 4)
        )

        print(
            "EMA 21:",
            round(current["ema21"], 4)
        )

        print(
            "RSI:",
            round(current["rsi"], 2)
        )

        print(
            "MACD:",
            round(current["macd"], 5)
        )

        print(
            "MACD Signal:",
            round(current["macd_signal"], 5)
        )

        print(
            "MACD Histogram:",
            round(current["macd_hist"], 5)
        )

        print(
            "SIGNAL:",
            signal
        )

        print(
            "SCORE:",
            score
        )

        print(
            "CONFIDENCE:",
            str(confidence) + "%"
        )

        print("-" * 50)

    except Exception as e:

        print(
            "ERROR:",
            e
        )


# ==================================================
# START BOT
# ==================================================

if __name__ == "__main__":
    main()
