import requests
import pandas as pd
import ta
from datetime import datetime

BOT_NAME = "Smart Trading Signal Bot V5 - BACKTEST"

SYMBOL = "BTCUSD"
KRAKEN_PAIR = "XBTUSD"
INTERVAL = "5m"
KRAKEN_INTERVAL = 5
CANDLE_LIMIT = 700

# عدد الشموع التي تمثل مدة الصفقة
# 1 = خمس دقائق
# 2 = عشر دقائق
# 3 = خمس عشرة دقيقة
EXPIRY_CANDLES = 1


def get_market_data():
    url = "https://api.kraken.com/0/public/OHLC"

    params = {
        "pair": KRAKEN_PAIR,
        "interval": KRAKEN_INTERVAL
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise Exception("Kraken API error: " + str(data["error"]))

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

    df = df.dropna().reset_index(drop=True)

    # آخر شمعة قد تكون غير مكتملة
    if len(df) > 1:
        df = df.iloc[:-1].reset_index(drop=True)

    return df


def calculate_indicators(df):

    df["ema9"] = ta.trend.EMAIndicator(
        close=df["close"],
        window=9
    ).ema_indicator()

    df["ema21"] = ta.trend.EMAIndicator(
        close=df["close"],
        window=21
    ).ema_indicator()

    df["rsi"] = ta.momentum.RSIIndicator(
        close=df["close"],
        window=14
    ).rsi()

    macd = ta.trend.MACD(
        close=df["close"],
        window_slow=26,
        window_fast=12,
        window_sign=9
    )

    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    adx_indicator = ta.trend.ADXIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    )

    df["adx"] = adx_indicator.adx()
    df["di_plus"] = adx_indicator.adx_pos()
    df["di_minus"] = adx_indicator.adx_neg()

    df["volume_ma"] = df["volume"].rolling(20).mean()

    return df


def analyze_candle(current):

    candle_range = current["high"] - current["low"]

    if candle_range <= 0:
        return "NEUTRAL", 0

    body = abs(
        current["close"] - current["open"]
    )

    body_ratio = body / candle_range

    if (
        current["close"] > current["open"]
        and body_ratio >= 0.55
    ):
        return "BULLISH", 1

    if (
        current["close"] < current["open"]
        and body_ratio >= 0.55
    ):
        return "BEARISH", -1

    return "NEUTRAL", 0


def generate_signal(df, index):

    current = df.iloc[index]

    trend_score = 0
    momentum_score = 0
    confirmation_score = 0

    # =========================
    # TREND
    # =========================

    if current["ema9"] > current["ema21"]:

        trend_score += 25

    elif current["ema9"] < current["ema21"]:

        trend_score -= 25

    if current["close"] > current["ema9"]:

        trend_score += 10

    elif current["close"] < current["ema9"]:

        trend_score -= 10

    # =========================
    # ADX + DI
    # =========================

    if current["adx"] >= 25:

        if current["di_plus"] > current["di_minus"]:

            trend_score += 20

        elif current["di_minus"] > current["di_plus"]:

            trend_score -= 20

    # =========================
    # RSI
    # =========================

    if 55 <= current["rsi"] < 70:

        momentum_score += 20

    elif 30 < current["rsi"] <= 45:

        momentum_score -= 20

    # =========================
    # MACD
    # =========================

    if current["macd"] > current["macd_signal"]:

        momentum_score += 20

    elif current["macd"] < current["macd_signal"]:

        momentum_score -= 20

    # =========================
    # MACD HISTOGRAM
    # =========================

    if current["macd_hist"] > 0:

        momentum_score += 10

    elif current["macd_hist"] < 0:

        momentum_score -= 10

    # =========================
    # CANDLE
    # =========================

    candle_type, candle_direction = analyze_candle(
        current
    )

    if candle_type == "BULLISH":

        confirmation_score += 10

    elif candle_type == "BEARISH":

        confirmation_score -= 10

    # =========================
    # VOLUME
    # =========================

    volume_ratio = 0

    if (
        pd.notna(current["volume_ma"])
        and current["volume_ma"] > 0
    ):

        volume_ratio = (
            current["volume"]
            / current["volume_ma"]
        )

    if volume_ratio >= 1.20:

        if trend_score > 0:

            confirmation_score += 10

        elif trend_score < 0:

            confirmation_score -= 10

    elif volume_ratio >= 0.80:

        if trend_score > 0:

            confirmation_score += 5

        elif trend_score < 0:

            confirmation_score -= 5

    # =========================
    # TOTAL SCORE
    # =========================

    score = (
        trend_score
        + momentum_score
        + confirmation_score
    )

    # =========================
    # MARKET QUALITY
    # =========================

    if current["adx"] >= 30:

        market_quality = "STRONG"

    elif current["adx"] >= 20:

        market_quality = "MODERATE"

    else:

        market_quality = "WEAK"

    # =========================
    # ALIGNMENT
    # =========================

    bullish_alignment = (
        trend_score >= 25
        and momentum_score >= 20
    )

    bearish_alignment = (
        trend_score <= -25
        and momentum_score <= -20
    )

    volume_ok = volume_ratio >= 0.80

    # =========================
    # SIGNAL
    # =========================

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

    # =========================
    # QUALITY
    # =========================

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

    return signal, score, quality


def run_backtest(df):

    results = []

    start_index = 50

    end_index = len(df) - EXPIRY_CANDLES

    for i in range(start_index, end_index):

        signal, score, quality = generate_signal(
            df,
            i
        )

        if signal == "WAIT":

            continue

        entry_price = df.iloc[i]["close"]

        exit_index = i + EXPIRY_CANDLES

        exit_price = df.iloc[exit_index]["close"]

        result = "DRAW"

        if signal == "CALL":

            if exit_price > entry_price:
                result = "WIN"

            elif exit_price < entry_price:
                result = "LOSS"

        elif signal == "PUT":

            if exit_price < entry_price:
                result = "WIN"

            elif exit_price > entry_price:
                result = "LOSS"

        results.append({
            "index": i,
            "signal": signal,
            "score": score,
            "quality": quality,
            "entry": entry_price,
            "exit": exit_price,
            "result": result
        })

    return pd.DataFrame(results)


def calculate_statistics(results):

    if results.empty:

        return None

    total = len(results)

    wins = len(
        results[results["result"] == "WIN"]
    )

    losses = len(
        results[results["result"] == "LOSS"]
    )

    draws = len(
        results[results["result"] == "DRAW"]
    )

    win_rate = (
        wins / (wins + losses) * 100
        if (wins + losses) > 0
        else 0
    )

    # =========================
    # MAX LOSING STREAK
    # =========================

    max_losing_streak = 0
    current_streak = 0

    for result in results["result"]:

        if result == "LOSS":

            current_streak += 1

            if current_streak > max_losing_streak:

                max_losing_streak = current_streak

        else:

            current_streak = 0

    # =========================
    # QUALITY STATISTICS
    # =========================

    quality_stats = {}

    for quality in ["HIGH", "MEDIUM", "LOW"]:

        subset = results[
            results["quality"] == quality
        ]

        q_total = len(subset)

        q_wins = len(
            subset[subset["result"] == "WIN"]
        )

        q_losses = len(
            subset[subset["result"] == "LOSS"]
        )

        q_win_rate = (
            q_wins / (q_wins + q_losses) * 100
            if (q_wins + q_losses) > 0
            else 0
        )

        quality_stats[quality] = {
            "total": q_total,
            "wins": q_wins,
            "losses": q_losses,
            "win_rate": q_win_rate
        }

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": win_rate,
        "max_losing_streak": max_losing_streak,
        "quality_stats": quality_stats
    }


def main():

    print("=" * 65)
    print(BOT_NAME)
    print("=" * 65)

    print("Symbol:", SYMBOL)
    print("Market:", KRAKEN_PAIR)
    print("Timeframe:", INTERVAL)
    print(
        "Expiry:",
        EXPIRY_CANDLES * 5,
        "minutes"
    )

    print(
        "Backtest started:",
        datetime.now()
    )

    print()

    try:

        df = get_market_data()

        print(
            "Candles received:",
            len(df)
        )

        if len(df) < 100:

            raise Exception(
                "Not enough candle data"
            )

        df = calculate_indicators(df)

        results = run_backtest(df)

        statistics = calculate_statistics(
            results
        )

        print("-" * 65)

        if statistics is None:

            print(
                "No CALL/PUT signals were generated."
            )

            return

        print("BACKTEST RESULTS")
        print()

        print(
            "TOTAL TRADES:",
            statistics["total"]
        )

        print(
            "WINS:",
            statistics["wins"]
        )

        print(
            "LOSSES:",
            statistics["losses"]
        )

        print(
            "DRAWS:",
            statistics["draws"]
        )

        print(
            "WIN RATE:",
            round(
                statistics["win_rate"],
                2
            ),
            "%"
        )

        print(
            "MAX LOSING STREAK:",
            statistics["max_losing_streak"]
        )

        print()
        print("QUALITY BREAKDOWN")
        print()

        for quality, data in statistics[
            "quality_stats"
        ].items():

            print(
                quality,
                "->",
                "Trades:",
                data["total"],
                "| Wins:",
                data["wins"],
                "| Losses:",
                data["losses"],
                "| Win Rate:",
                round(
                    data["win_rate"],
                    2
                ),
                "%"
            )

        print()
        print("-" * 65)

        # آخر 10 إشارات
        print("LAST 10 SIGNALS")
        print()

        print(
            results.tail(10).to_string(
                index=False
            )
        )

        print("-" * 65)

        print()
        print(
            "NOTE: This backtest is a historical"
            " close-to-close test."
        )

        print(
            "It does NOT guarantee future profits"
            " or equal Pocket Option results."
        )

        print(
            "Confidence/score is NOT a true"
            " probability of winning."
        )

    except Exception as e:

        print("ERROR:", e)


if __name__ == "__main__":
    main()
