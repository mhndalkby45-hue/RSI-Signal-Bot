import requests
import pandas as pd
import ta
from datetime import datetime


# ==================================================
# SMART TRADING SIGNAL BOT V3
# ==================================================

BOT_NAME = "Smart Trading Signal Bot V3"

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
# INDICATORS
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

    # Volume average
    df["volume_ma"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    return df


# ==================================================
# CANDLE CONFIRMATION
# ==================================================

def candle_confirmation(current):

    candle_range = (
        current["high"] -
        current["low"]
    )

    if candle_range <= 0:
        return "NEUTRAL", 0

    body = abs(
        current["close"] -
        current["open"]
    )

    body_ratio = body / candle_range

    # Strong bullish candle
    if (
        current["close"] >
        current["open"]
        and body_ratio >= 0.55
    ):
        return "BULLISH", 1

    # Strong bearish candle
    if (
        current["close"] <
        current["open"]
        and body_ratio >= 0.55
    ):
        return "BEARISH", -1

    return "NEUTRAL", 0


# ==================================================
# GENERATE SIGNAL V3
# ==================================================

def generate_signal(df):

    current = df.iloc[-1]

    score = 0

    trend_points = 0
    momentum_points = 0
    confirmation_points = 0

    reasons = []

    # ==================================================
    # TREND
    # ==================================================

    if current["ema9"] > current["ema21"]:

        trend_points += 25
        reasons.append("EMA BULLISH")

    elif current["ema9"] < current["ema21"]:

        trend_points -= 25
        reasons.append("EMA BEARISH")


    # Price position

    if current["close"] > current["ema9"]:

        trend_points += 10
        reasons.append("PRICE ABOVE EMA9")

    elif current["close"] < current["ema9"]:

        trend_points -= 10
        reasons.append("PRICE BELOW EMA9")


    # ADX

    if current["adx"] >= 25:

        reasons.append("ADX STRONG")

        if trend_points > 0:
            trend_points += 10

        elif trend_points < 0:
            trend_points -= 10

    else:

        reasons.append("ADX WEAK")


    # ==================================================
    # MOMENTUM
    # ==================================================

    # RSI

    if 55 <= current["rsi"] < 70:

        momentum_points += 20
        reasons.append("RSI BULLISH")

    elif 30 < current["rsi"] <= 45:

        momentum_points -= 20
        reasons.append("RSI BEARISH")

    elif current["rsi"] >= 70:

        reasons.append("RSI OVERBOUGHT")

    elif current["rsi"] <= 30:

        reasons.append("RSI OVERSOLD")


    # MACD

    if current["macd"] > current["macd_signal"]:

        momentum_points += 20
        reasons.append("MACD BULLISH")

    elif current["macd"] < current["macd_signal"]:

        momentum_points -= 20
        reasons.append("MACD BEARISH")


    # MACD Histogram

    if current["macd_hist"] > 0:

        momentum_points += 10
        reasons.append("MACD HISTOGRAM POSITIVE")

    elif current["macd_hist"] < 0:

        momentum_points -= 10
        reasons.append("MACD HISTOGRAM NEGATIVE")


    # ==================================================
    # CANDLE
    # ==================================================

    candle_type, candle_direction = candle_confirmation(
        current
    )

    if candle_type == "BULLISH":

        confirmation_points += 10
        reasons.append("BULLISH CANDLE")

    elif candle_type == "BEARISH":

        confirmation_points -= 10
        reasons.append("BEARISH CANDLE")

    else:

        reasons.append("NEUTRAL CANDLE")


    # ==================================================
    # VOLUME
    # ==================================================

    volume_confirmed = False

    if (
        pd.notna(current["volume_ma"])
        and
        current["volume"] >
        current["volume_ma"]
    ):

        volume_confirmed = True
        reasons.append("VOLUME CONFIRMED")

        if trend_points > 0:
            confirmation_points += 5

        elif trend_points < 0:
            confirmation_points -= 5

    else:

        reasons.append("LOW VOLUME")


    # ==================================================
    # TOTAL SCORE
    # ==================================================

    score = (
        trend_points +
        momentum_points +
        confirmation_points
    )


    # ==================================================
    # MARKET QUALITY
    # ==================================================

    if current["adx"] >= 30:

        market_quality = "STRONG"

    elif current["adx"] >= 20:

        market_quality = "MODERATE"

    else:

        market_quality = "WEAK"


    # ==================================================
    # ALIGNMENT
    # ==================================================

    bullish_alignment = (
        trend_points > 0
        and momentum_points > 0
    )

    bearish_alignment = (
        trend_points < 0
        and momentum_points < 0
    )


    # ==================================================
    # SIGNAL DECISION
    # ==================================================

    signal = "WAIT"

    if (
        score >= 70
        and bullish_alignment
        and market_quality != "WEAK"
    ):

        signal = "CALL"

    elif (
        score <= -70
        and bearish_alignment
        and market_quality != "WEAK"
    ):

        signal = "PUT"


    # ==================================================
    # SIGNAL QUALITY
    # ==================================================

    if signal == "WAIT":

        quality = "LOW"

    elif (
        abs(score) >= 90
        and market_quality == "STRONG"
        and volume_confirmed
        and candle_type != "NEUTRAL"
    ):

        quality = "HIGH"

    elif abs(score) >= 75:

        quality = "MEDIUM"

    else:

        quality = "LOW"


    # ==================================================
    # CONFIDENCE SCORE
    # ==================================================

    confidence = min(
        int(abs(score)),
        100
    )


    return (
        signal,
        score,
        confidence,
        quality,
        market_quality,
        trend_points,
        momentum_points,
        confirmation_points,
        reasons
    )


# ==================================================
# MAIN
# ==================================================

def main():

    print("=" * 60)
    print(BOT_NAME)
    print("=" * 60)

    print("Symbol:", SYMBOL)
    print("Market:", KRAKEN_PAIR)
    print("Timeframe:", INTERVAL)
    print("Bot started:", datetime.now())

    print()

    try:

        # Get candles
        df = get_market_data()

        if len(df) < 50:

            raise Exception(
                "Not enough candle data received"
            )

        # Calculate indicators
        df = calculate_indicators(df)

        # Generate signal
        (
            signal,
            score,
            confidence,
            quality,
            market_quality,
            trend_points,
            momentum_points,
            confirmation_points,
            reasons
        ) = generate_signal(df)

        current = df.iloc[-1]

        # ==================================================
        # OUTPUT
        # ==================================================

        print("-" * 60)

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

        print()

        print(
            "TREND SCORE:",
            trend_points
        )

        print(
            "MOMENTUM SCORE:",
            momentum_points
        )

        print(
            "CONFIRMATION SCORE:",
            confirmation_points
        )

        print(
            "TOTAL SCORE:",
            score
        )

        print(
            "MARKET QUALITY:",
            market_quality
        )

        print(
            "SIGNAL QUALITY:",
            quality
        )

        print(
            "SIGNAL:",
            signal
        )

        print(
            "CONFIDENCE:",
            str(confidence) + "%"
        )

        print()

        print("REASONS:")

        for reason in reasons:

            print("-", reason)

        print("-" * 60)

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
