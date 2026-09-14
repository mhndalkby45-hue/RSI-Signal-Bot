import requests
import pandas as pd
import ta
from datetime import datetime


# ==================================================
# SMART TRADING SIGNAL BOT V4
# ==================================================

BOT_NAME = "Smart Trading Signal Bot V4"

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

    # ADX + DI
    adx_indicator = ta.trend.ADXIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    )

    df["adx"] = adx_indicator.adx()
    df["di_plus"] = adx_indicator.adx_pos()
    df["di_minus"] = adx_indicator.adx_neg()

    # Volume average
    df["volume_ma"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    return df


# ==================================================
# CANDLE ANALYSIS
# ==================================================

def analyze_candle(current):

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

    # Bullish
    if (
        current["close"] >
        current["open"]
        and body_ratio >= 0.55
    ):
        return "BULLISH", 1

    # Bearish
    if (
        current["close"] <
        current["open"]
        and body_ratio >= 0.55
    ):
        return "BEARISH", -1

    return "NEUTRAL", 0


# ==================================================
# GENERATE SIGNAL V4
# ==================================================

def generate_signal(df):

    current = df.iloc[-1]

    trend_score = 0
    momentum_score = 0
    confirmation_score = 0

    reasons = []

    # ==================================================
    # 1. EMA TREND
    # ==================================================

    if current["ema9"] > current["ema21"]:

        trend_score += 25
        reasons.append("EMA BULLISH")

    elif current["ema9"] < current["ema21"]:

        trend_score -= 25
        reasons.append("EMA BEARISH")


    # Price vs EMA9

    if current["close"] > current["ema9"]:

        trend_score += 10
        reasons.append("PRICE ABOVE EMA9")

    elif current["close"] < current["ema9"]:

        trend_score -= 10
        reasons.append("PRICE BELOW EMA9")


    # ==================================================
    # 2. ADX DIRECTION
    # ==================================================

    if current["adx"] >= 25:

        reasons.append("ADX STRONG")

        if current["di_plus"] > current["di_minus"]:

            trend_score += 20
            reasons.append("DI+ ABOVE DI-")

        elif current["di_minus"] > current["di_plus"]:

            trend_score -= 20
            reasons.append("DI- ABOVE DI+")

    else:

        reasons.append("ADX WEAK")


    # ==================================================
    # 3. RSI
    # ==================================================

    if 55 <= current["rsi"] < 70:

        momentum_score += 20
        reasons.append("RSI BULLISH")

    elif 30 < current["rsi"] <= 45:

        momentum_score -= 20
        reasons.append("RSI BEARISH")

    elif current["rsi"] >= 70:

        reasons.append("RSI OVERBOUGHT")

    elif current["rsi"] <= 30:

        reasons.append("RSI OVERSOLD")


    # ==================================================
    # 4. MACD
    # ==================================================

    if current["macd"] > current["macd_signal"]:

        momentum_score += 20
        reasons.append("MACD BULLISH")

    elif current["macd"] < current["macd_signal"]:

        momentum_score -= 20
        reasons.append("MACD BEARISH")


    # MACD Histogram

    if current["macd_hist"] > 0:

        momentum_score += 10
        reasons.append("MACD HISTOGRAM POSITIVE")

    elif current["macd_hist"] < 0:

        momentum_score -= 10
        reasons.append("MACD HISTOGRAM NEGATIVE")


    # ==================================================
    # 5. CANDLE CONFIRMATION
    # ==================================================

    candle_type, candle_direction = analyze_candle(
        current
    )

    if candle_type == "BULLISH":

        confirmation_score += 10
        reasons.append("BULLISH CANDLE")

    elif candle_type == "BEARISH":

        confirmation_score -= 10
        reasons.append("BEARISH CANDLE")

    else:

        reasons.append("NEUTRAL CANDLE")


    # ==================================================
    # 6. VOLUME FILTER
    # ==================================================

    volume_ratio = 0

    if (
        pd.notna(current["volume_ma"])
        and current["volume_ma"] > 0
    ):

        volume_ratio = (
            current["volume"] /
            current["volume_ma"]
        )


    # Strong volume
    if volume_ratio >= 1.20:

        reasons.append("HIGH VOLUME")

        if trend_score > 0:
            confirmation_score += 10

        elif trend_score < 0:
            confirmation_score -= 10


    # Normal volume
    elif volume_ratio >= 0.80:

        reasons.append("NORMAL VOLUME")

        if trend_score > 0:
            confirmation_score += 5

        elif trend_score < 0:
            confirmation_score -= 5


    # Low volume
    else:

        reasons.append("LOW VOLUME")


    # ==================================================
    # TOTAL SCORE
    # ==================================================

    score = (
        trend_score +
        momentum_score +
        confirmation_score
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
    # DIRECTION ALIGNMENT
    # ==================================================

    bullish_alignment = (
        trend_score >= 25
        and momentum_score >= 20
    )

    bearish_alignment = (
        trend_score <= -25
        and momentum_score <= -20
    )


    # ==================================================
    # VOLUME APPROVAL
    # ==================================================

    volume_ok = volume_ratio >= 0.80


    # ==================================================
    # FINAL SIGNAL
    # ==================================================

    signal = "WAIT"

    if (
        score >= 70
        and bullish_alignment
        and market_quality != "WEAK"
        and volume_ok
    ):

        signal = "CALL"

    elif (
        score <= -70
        and bearish_alignment
        and market_quality != "WEAK"
        and volume_ok
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
        and volume_ratio >= 1.20
        and candle_type != "NEUTRAL"
    ):

        quality = "HIGH"

    elif abs(score) >= 75:

        quality = "MEDIUM"

    else:

        quality = "LOW"


    # ==================================================
    # CONFIDENCE
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
        trend_score,
        momentum_score,
        confirmation_score,
        volume_ratio,
        candle_type,
        reasons
    )


# ==================================================
# MAIN
# ==================================================

def main():

    print("=" * 65)
    print(BOT_NAME)
    print("=" * 65)

    print("Symbol:", SYMBOL)
    print("Market:", KRAKEN_PAIR)
    print("Timeframe:", INTERVAL)
    print("Bot started:", datetime.now())

    print()

    try:

        # Market data
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
            quality,
            market_quality,
            trend_score,
            momentum_score,
            confirmation_score,
            volume_ratio,
            candle_type,
            reasons
        ) = generate_signal(df)

        current = df.iloc[-1]

        print("-" * 65)

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
            "DI+:",
            round(current["di_plus"], 2)
        )

        print(
            "DI-:",
            round(current["di_minus"], 2)
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
            "Volume Ratio:",
            round(volume_ratio, 2)
        )

        print(
            "Candle:",
            candle_type
        )

        print()

        print(
            "TREND SCORE:",
            trend_score
        )

        print(
            "MOMENTUM SCORE:",
            momentum_score
        )

        print(
            "CONFIRMATION SCORE:",
            confirmation_score
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

        print("-" * 65)

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
