import requests
import pandas as pd
import ta
from datetime import datetime

BOT_NAME = "Smart Trading Signal Bot V6 - ADVANCED BACKTEST"

SYMBOL = "BTCUSD"
KRAKEN_PAIR = "XBTUSD"
INTERVAL = "5m"

CANDLE_LIMIT = 720

# سنختبر 5 و10 و15 دقيقة
EXPIRIES = [1, 2, 3]


def get_market_data():

    url = "https://api.kraken.com/0/public/OHLC"

    params = {
        "pair": KRAKEN_PAIR,
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
            "Kraken API error: "
            + str(data["error"])
        )

    result = data.get("result", {})

    pair_key = next(
        (
            key for key in result.keys()
            if key != "last"
        ),
        None
    )

    if pair_key is None:
        raise Exception(
            "No market data received"
        )

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

    df = (
        df
        .dropna()
        .reset_index(drop=True)
    )

    # حذف آخر شمعة لأنها قد تكون غير مكتملة
    if len(df) > 1:

        df = df.iloc[:-1].reset_index(
            drop=True
        )

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

    adx = ta.trend.ADXIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    )

    df["adx"] = adx.adx()
    df["di_plus"] = adx.adx_pos()
    df["di_minus"] = adx.adx_neg()

    df["volume_ma"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    return df


def candle_analysis(row):

    candle_range = (
        row["high"] - row["low"]
    )

    if candle_range <= 0:

        return "NEUTRAL"

    body = abs(
        row["close"] - row["open"]
    )

    body_ratio = (
        body / candle_range
    )

    if (
        row["close"] > row["open"]
        and body_ratio >= 0.55
    ):

        return "BULLISH"

    if (
        row["close"] < row["open"]
        and body_ratio >= 0.55
    ):

        return "BEARISH"

    return "NEUTRAL"


def generate_signal(df, index):

    row = df.iloc[index]

    trend = 0
    momentum = 0
    confirmation = 0

    # =========================
    # EMA TREND
    # =========================

    if row["ema9"] > row["ema21"]:

        trend += 25

    elif row["ema9"] < row["ema21"]:

        trend -= 25

    # Price location
    if row["close"] > row["ema9"]:

        trend += 10

    elif row["close"] < row["ema9"]:

        trend -= 10

    # =========================
    # ADX + DI
    # =========================

    if row["adx"] >= 25:

        if row["di_plus"] > row["di_minus"]:

            trend += 20

        elif row["di_minus"] > row["di_plus"]:

            trend -= 20

    # =========================
    # RSI
    # =========================

    if 55 <= row["rsi"] < 70:

        momentum += 20

    elif 30 < row["rsi"] <= 45:

        momentum -= 20

    # =========================
    # MACD
    # =========================

    if row["macd"] > row["macd_signal"]:

        momentum += 20

    elif row["macd"] < row["macd_signal"]:

        momentum -= 20

    # =========================
    # HISTOGRAM
    # =========================

    if row["macd_hist"] > 0:

        momentum += 10

    elif row["macd_hist"] < 0:

        momentum -= 10

    # =========================
    # CANDLE
    # =========================

    candle = candle_analysis(row)

    if candle == "BULLISH":

        confirmation += 10

    elif candle == "BEARISH":

        confirmation -= 10

    # =========================
    # VOLUME
    # =========================

    volume_ratio = 0

    if (
        pd.notna(row["volume_ma"])
        and row["volume_ma"] > 0
    ):

        volume_ratio = (
            row["volume"]
            / row["volume_ma"]
        )

    if volume_ratio >= 1.20:

        if trend > 0:

            confirmation += 10

        elif trend < 0:

            confirmation -= 10

    elif volume_ratio >= 0.80:

        if trend > 0:

            confirmation += 5

        elif trend < 0:

            confirmation -= 5

    total = (
        trend
        + momentum
        + confirmation
    )

    # =========================
    # MARKET QUALITY
    # =========================

    if row["adx"] >= 30:

        market = "STRONG"

    elif row["adx"] >= 20:

        market = "MODERATE"

    else:

        market = "WEAK"

    bullish_alignment = (
        trend >= 25
        and momentum >= 20
    )

    bearish_alignment = (
        trend <= -25
        and momentum <= -20
    )

    volume_ok = (
        volume_ratio >= 0.80
    )

    signal = "WAIT"

    if (
        total >= 70
        and bullish_alignment
        and market != "WEAK"
        and volume_ok
    ):

        signal = "CALL"

    elif (
        total <= -70
        and bearish_alignment
        and market != "WEAK"
        and volume_ok
    ):

        signal = "PUT"

    # =========================
    # V6 FILTER
    # =========================
    #
    # لا نعتبر HIGH تلقائياً أفضل.
    # نحتفظ بدرجات القوة فقط.

    if (
        abs(total) >= 90
        and market == "STRONG"
        and volume_ratio >= 1.20
        and candle != "NEUTRAL"
    ):

        quality = "HIGH"

    elif abs(total) >= 75:

        quality = "MEDIUM"

    else:

        quality = "LOW"

    return (
        signal,
        total,
        quality,
        trend,
        momentum,
        confirmation,
        volume_ratio
    )


def backtest_expiry(
    df,
    expiry
):

    records = []

    start = 60
    end = len(df) - expiry

    for i in range(start, end):

        (
            signal,
            score,
            quality,
            trend,
            momentum,
            confirmation,
            volume_ratio
        ) = generate_signal(
            df,
            i
        )

        if signal == "WAIT":

            continue

        entry = df.iloc[i]["close"]

        exit_price = df.iloc[
            i + expiry
        ]["close"]

        if signal == "CALL":

            if exit_price > entry:

                result = "WIN"

            elif exit_price < entry:

                result = "LOSS"

            else:

                result = "DRAW"

        else:

            if exit_price < entry:

                result = "WIN"

            elif exit_price > entry:

                result = "LOSS"

            else:

                result = "DRAW"

        records.append({
            "signal": signal,
            "score": score,
            "quality": quality,
            "trend": trend,
            "momentum": momentum,
            "confirmation": confirmation,
            "volume_ratio": volume_ratio,
            "result": result
        })

    return pd.DataFrame(records)


def statistics(df):

    if df.empty:

        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "win_rate": 0
        }

    wins = len(
        df[df["result"] == "WIN"]
    )

    losses = len(
        df[df["result"] == "LOSS"]
    )

    draws = len(
        df[df["result"] == "DRAW"]
    )

    decisive = wins + losses

    win_rate = (
        wins / decisive * 100
        if decisive > 0
        else 0
    )

    return {
        "trades": len(df),
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": win_rate
    }


def quality_statistics(
    df,
    quality
):

    subset = df[
        df["quality"] == quality
    ]

    return statistics(subset)


def main():

    print("=" * 70)
    print(BOT_NAME)
    print("=" * 70)

    print("Symbol:", SYMBOL)
    print("Market:", KRAKEN_PAIR)
    print("Timeframe:", INTERVAL)

    print(
        "Started:",
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

        all_results = {}

        # =========================
        # TEST ALL EXPIRIES
        # =========================

        for expiry in EXPIRIES:

            minutes = expiry * 5

            print()
            print("=" * 70)
            print(
                "EXPIRY:",
                minutes,
                "MINUTES"
            )
            print("=" * 70)

            results = backtest_expiry(
                df,
                expiry
            )

            all_results[expiry] = results

            stats = statistics(
                results
            )

            print()
            print("TOTAL TRADES:",
                  stats["trades"])

            print("WINS:",
                  stats["wins"])

            print("LOSSES:",
                  stats["losses"])

            print("DRAWS:",
                  stats["draws"])

            print(
                "WIN RATE:",
                round(
                    stats["win_rate"],
                    2
                ),
                "%"
            )

            print()
            print("QUALITY BREAKDOWN")
            print()

            for quality in [
                "HIGH",
                "MEDIUM",
                "LOW"
            ]:

                q = quality_statistics(
                    results,
                    quality
                )

                print(
                    quality,
                    "->",
                    "Trades:",
                    q["trades"],
                    "| Wins:",
                    q["wins"],
                    "| Losses:",
                    q["losses"],
                    "| Win Rate:",
                    round(
                        q["win_rate"],
                        2
                    ),
                    "%"
                )

        # =========================
        # BEST EXPIRY
        # =========================

        print()
        print("=" * 70)
        print("FINAL COMPARISON")
        print("=" * 70)

        comparison = []

        for expiry, results in all_results.items():

            stats = statistics(
                results
            )

            comparison.append({
                "Expiry": str(
                    expiry * 5
                ) + " min",
                "Trades": stats["trades"],
                "Wins": stats["wins"],
                "Losses": stats["losses"],
                "Win Rate": round(
                    stats["win_rate"],
                    2
                )
            })

        comparison_df = pd.DataFrame(
            comparison
        )

        print(
            comparison_df.to_string(
                index=False
            )
        )

        if not comparison_df.empty:

            best_index = (
                comparison_df[
                    "Win Rate"
                ].idxmax()
            )

            best = comparison_df.loc[
                best_index
            ]

            print()
            print(
                "BEST HISTORICAL EXPIRY:",
                best["Expiry"]
            )

            print(
                "BEST WIN RATE:",
                best["Win Rate"],
                "%"
            )

        # =========================
        # IMPORTANT WARNING
        # =========================

        print()
        print("=" * 70)
        print("IMPORTANT")
        print("=" * 70)

        print(
            "This is historical testing only."
        )

        print(
            "It is NOT a guarantee of future profit."
        )

        print(
            "It does NOT reproduce Pocket Option"
            " execution, payout, spread or price feed."
        )

        print(
            "WIN RATE is not the same as profitability."
        )

        print(
            "Do not use real money based only"
            " on this backtest."
        )

        print("=" * 70)

    except Exception as e:

        print(
            "ERROR:",
            e
        )


if __name__ == "__main__":
    main()
