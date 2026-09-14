import requests
import pandas as pd
import ta
from datetime import datetime


# ==================================================
# SMART TRADING SIGNAL BOT V2
# ==================================================

BOT_NAME = "Smart Trading Signal Bot V2"

SYMBOL = "BTCUSD"
KRAKEN_PAIR = "XBTUSD"

INTERVAL = "5m"
KRAKEN_INTERVAL = 5

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
    df["macd_hist"] = macd.macd_diff()

    # ADX
    adx = ta.trend.ADXIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    )

    df["adx"] = adx.adx()

    # Average volume
    df["volume_ma"] = (
        df["volume"]
        .rolling(window=20)
        .mean()
    )

    return df


# ==================================================
# CANDLE ANALYSIS
# ==================================================

def analyze_candle(current):

    candle_range = current["high"] - current["low"]

    if candle_range <= 0:
        return 0, "NEUTRAL"

    body = abs(
        current["close"] - current["open"]
    )

    body_ratio = body / candle_range

    # Bullish candle
    if (
        current["close"] > current["open"]
        and body_ratio >= 0.55
    ):
        return 10, "BULLISH"

    # Bearish candle
    if (
        current["close"] < current["open"]
        and body_ratio >= 0.55
    ):
        return -10, "BEARISH"

    return 0, "NEUTRAL"


# ==================================================
# GENERATE SIGNAL
# ==================================================

def generate_signal(df):

    current = df.iloc[-1]

    score = 0

    reasons = []

    # ----------------------------------------------
    # 1. EMA TREND
    # ----------------------------------------------

    if current["ema9"] > current["ema21"]:

        score += 25
        reasons.append("EMA BULLISH")

    elif current["ema9"] < current["ema21"]:

        score -= 25
        reasons.append("EMA BEARISH")


    # ----------------------------------------------
    # 2. PRICE VS EMA
    # ----------------------------------------------

    if current["close"] > current["ema9"]:

        score += 10
        reasons.append("PRICE ABOVE EMA9")

    elif current["close"] < current["ema9"]:

        score -= 10
        reasons.append("PRICE BELOW EMA9")


    # ----------------------------------------------
    # 3. RSI
    # ----------------------------------------------

    if 55 <= current["rsi"] < 70:

        score += 20
        reasons.append("RSI BULLISH")

    elif 30 < current["rsi"] <= 45:

        score -= 20
        reasons.append("RSI BEARISH")


    # Avoid chasing extreme RSI
    if current["rsi"] >= 70:

        score -= 10
        reasons.append("RSI OVERBOUGHT")

    elif current["rsi"] <= 30:

        score += 10
        reasons.append("RSI OVERSOLD")


    # ----------------------------------------------
    # 4. MACD
    # ----------------------------------------------

    if current["macd"] > current["macd_signal"]:

        score += 20
        reasons.append("MACD BULLISH")

    elif current["macd"] < current["macd_signal"]:

        score -= 20
        reasons.append("MACD BEARISH")


    # ----------------------------------------------
    # 5. MACD HISTOGRAM
    # ----------------------------------------------

    if current["macd_hist"] > 0:

        score += 10
        reasons.append("MACD HISTOGRAM POSITIVE")

    elif current["macd_hist"] < 0:

        score -= 10
        reasons.append("MACD HISTOGRAM NEGATIVE")


    # ----------------------------------------------
    # 6. ADX TREND STRENGTH
    # ----------------------------------------------

    if current["adx"] >= 25:

        reasons.append("STRONG TREND")

        # Strengthens existing direction
        if score > 0:
            score += 10

        elif score < 0:
            score -= 10

    else:

        reasons.append("WEAK TREND")


    # ----------------------------------------------
    # 7. VOLUME CONFIRMATION
    # ----------------------------------------------

    if (
        pd.notna(current["volume_ma"])
        and current["volume"] > current["volume_ma"]
    ):

        reasons.append("VOLUME CONFIRMED")

        if score > 0:
            score += 5

        elif score < 0:
            score -= 5

    else:

        reasons.append("LOW VOLUME")


    # ----------------------------------------------
    # 8. CANDLE CONFIRMATION
    # ----------------------------------------------

    candle_score, candle_type = analyze_candle(
        current
    )

    score += candle_score

    if candle_type == "BULLISH":

        reasons.append("BULLISH CANDLE")

    elif candle_type == "BEARISH":

        reasons.append("BEARISH CANDLE")


    # ----------------------------------------------
    # FINAL DECISION
    # ----------------------------------------------

    if score >= 65:

        signal = "CALL"

    elif score <= -65:

        signal = "PUT"

    else:

        signal = "WAIT"


    confidence = min(
        int(abs(score)),
        100
    )


    # ----------------------------------------------
    # MARKET QUALITY
    # ----------------------------------------------

    if current["adx"] < 20:

        market_quality = "LOW TREND"

    elif current["adx"] < 25:

        market_quality = "MODERATE"

    else:

        market_quality = "STRONG TREND"


    return (
        signal,
        score,
        confidence,
        market_quality,
        reasons
    )


# ==================================================
# MAIN
# ==================================================

def main():

    print("=" * 55)
    print(BOT_NAME)
    print("=" * 55)

    print("Symbol:", SYMBOL)
    print("Market:", KRAKEN_PAIR)
    print("Timeframe:", INTERVAL)
    print("Bot started:", datetime.now())

    print()

    try:

        # Get data
        df = get_market_data()

        if len(df) < 50:

            raise Exception(
                "Not enough candle data received"
            )

        # Indicators
        df = calculate_indicators(df)

        # Signal
        (
            signal,
            score,
            confidence,
            market_quality,
            reasons
        ) = generate_signal(df)

        current = df.iloc[-1]

        print("-" * 55)

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
            "ADX:",
            round(current["adx"], 2)
        )

        print(
            "Volume:",
            round(current["volume"], 4)
        )

        print(
            "Average Volume:",
            round(current["volume_ma"], 4)
        )

        print(
            "Market Quality:",
            market_quality
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

        print()

        print("REASONS:")

        for reason in reasons:

            print("-", reason)

        print("-" * 55)

    except Exception as e:

        print(
            "ERROR:",
            e
        )


# ==================================================
# START
# ==================================================

if __name__ == "__main__":
    main()
