import requests
import pandas as pd
import ta
from datetime import datetime

BOT_NAME = "Smart Trading Signal Bot V9 - DIRECTION ADAPTIVE"

SYMBOL = "BTCUSD"
KRAKEN_PAIR = "XBTUSD"
INTERVAL = "5m"

CANDLE_LIMIT = 720

EXPIRIES = [1, 2, 3]


# ============================================================
# DATA
# ============================================================

def get_data():

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
        raise Exception(data["error"])

    result = data["result"]

    pair_key = [
        key for key in result.keys()
        if key != "last"
    ][0]

    df = pd.DataFrame(
        result[pair_key],
        columns=[
            "time",
            "open",
            "high",
            "low",
            "close",
            "vwap",
            "volume",
            "count"
        ]
    )

    for col in [
        "open",
        "high",
        "low",
        "close",
        "vwap",
        "volume"
    ]:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df["time"] = pd.to_datetime(
        df["time"],
        unit="s"
    )

    df = df.dropna()

    if len(df) > 1:
        df = df.iloc[:-1]

    return df.tail(
        CANDLE_LIMIT
    ).reset_index(drop=True)


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(df):

    df["ema9"] = ta.trend.EMAIndicator(
        df["close"],
        window=9
    ).ema_indicator()

    df["ema21"] = ta.trend.EMAIndicator(
        df["close"],
        window=21
    ).ema_indicator()

    df["ema50"] = ta.trend.EMAIndicator(
        df["close"],
        window=50
    ).ema_indicator()

    df["rsi"] = ta.momentum.RSIIndicator(
        df["close"],
        window=14
    ).rsi()

    macd = ta.trend.MACD(
        df["close"],
        window_slow=26,
        window_fast=12,
        window_sign=9
    )

    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    adx = ta.trend.ADXIndicator(
        df["high"],
        df["low"],
        df["close"],
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

    atr = ta.volatility.AverageTrueRange(
        df["high"],
        df["low"],
        df["close"],
        window=14
    )

    df["atr"] = atr.average_true_range()

    df["atr_pct"] = (
        df["atr"] /
        df["close"] *
        100
    )

    # EMA distance
    df["ema_gap_pct"] = (
        abs(df["ema9"] - df["ema21"])
        / df["close"] *
        100
    )

    return df.dropna().reset_index(drop=True)


# ============================================================
# CANDLE
# ============================================================

def candle_info(row):

    candle_range = (
        row["high"] -
        row["low"]
    )

    body = abs(
        row["close"] -
        row["open"]
    )

    if candle_range <= 0:
        return "NEUTRAL", 0

    body_ratio = (
        body /
        candle_range
    )

    if body_ratio < 0.55:
        return "NEUTRAL", body_ratio

    if row["close"] > row["open"]:
        return "BULLISH", body_ratio

    if row["close"] < row["open"]:
        return "BEARISH", body_ratio

    return "NEUTRAL", body_ratio


# ============================================================
# CALL ENGINE
# ============================================================

def call_signal(row):

    score = 0
    reasons = []

    candle, body_ratio = candle_info(row)

    volume_ratio = (
        row["volume"] /
        row["volume_ma"]
        if row["volume_ma"] > 0
        else 0
    )

    # --------------------------------------------------------
    # CALL TREND
    # --------------------------------------------------------

    if (
        row["ema9"] >
        row["ema21"] >
        row["ema50"]
    ):
        score += 3
        reasons.append("EMA BULLISH")

    elif (
        row["ema9"] >
        row["ema21"]
    ):
        score += 1
        reasons.append("EMA SHORT BULLISH")

    else:
        reasons.append("EMA NOT BULLISH")

    if (
        row["close"] >
        row["ema9"] and
        row["close"] >
        row["ema21"]
    ):
        score += 2
        reasons.append("PRICE ABOVE EMA")

    # --------------------------------------------------------
    # CALL ADX
    # --------------------------------------------------------

    if (
        row["adx"] >= 25 and
        row["di_plus"] >
        row["di_minus"]
    ):
        score += 3
        reasons.append("ADX/DI BULLISH")

    # Strong trend bonus
    if (
        row["adx"] >= 30 and
        row["di_plus"] >
        row["di_minus"]
    ):
        score += 1

    # --------------------------------------------------------
    # CALL RSI
    # --------------------------------------------------------

    if 52 <= row["rsi"] <= 65:

        score += 2
        reasons.append("RSI BULLISH")

    elif 48 <= row["rsi"] < 52:

        score += 1
        reasons.append("RSI NEUTRAL-BULLISH")

    elif row["rsi"] > 70:

        score -= 2
        reasons.append("RSI OVERBOUGHT")

    # --------------------------------------------------------
    # CALL MACD
    # --------------------------------------------------------

    if (
        row["macd"] >
        row["macd_signal"] and
        row["macd_hist"] > 0
    ):
        score += 3
        reasons.append("MACD BULLISH")

    elif (
        row["macd"] >
        row["macd_signal"]
    ):
        score += 1

    # --------------------------------------------------------
    # CALL CANDLE
    # --------------------------------------------------------

    if candle == "BULLISH":

        score += 2
        reasons.append("BULLISH CANDLE")

    elif candle == "BEARISH":

        score -= 2
        reasons.append("BEARISH CANDLE")

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    if volume_ratio >= 1.20:

        score += 1
        reasons.append("HIGH VOLUME")

    elif volume_ratio < 0.70:

        score -= 2
        reasons.append("VERY LOW VOLUME")

    # --------------------------------------------------------
    # VOLATILITY
    # --------------------------------------------------------

    if (
        row["atr_pct"] < 0.025 or
        row["atr_pct"] > 0.80
    ):
        return None

    # --------------------------------------------------------
    # STRICT CALL
    # --------------------------------------------------------

    if (
        score >= 11 and
        row["adx"] >= 25 and
        row["di_plus"] >
        row["di_minus"] and
        candle == "BULLISH" and
        volume_ratio >= 0.70
    ):
        return {
            "score": score,
            "reasons": reasons,
            "volume_ratio": volume_ratio,
            "candle": candle
        }

    return None


# ============================================================
# PUT ENGINE
# ============================================================

def put_signal(row):

    score = 0
    reasons = []

    candle, body_ratio = candle_info(row)

    volume_ratio = (
        row["volume"] /
        row["volume_ma"]
        if row["volume_ma"] > 0
        else 0
    )

    # --------------------------------------------------------
    # PUT TREND
    # --------------------------------------------------------

    if (
        row["ema9"] <
        row["ema21"] <
        row["ema50"]
    ):
        score += 3
        reasons.append("EMA BEARISH")

    elif (
        row["ema9"] <
        row["ema21"]
    ):
        score += 1
        reasons.append("EMA SHORT BEARISH")

    else:
        reasons.append("EMA NOT BEARISH")

    if (
        row["close"] <
        row["ema9"] and
        row["close"] <
        row["ema21"]
    ):
        score += 2
        reasons.append("PRICE BELOW EMA")

    # --------------------------------------------------------
    # PUT ADX
    # --------------------------------------------------------

    if (
        row["adx"] >= 25 and
        row["di_minus"] >
        row["di_plus"]
    ):
        score += 3
        reasons.append("ADX/DI BEARISH")

    if (
        row["adx"] >= 30 and
        row["di_minus"] >
        row["di_plus"]
    ):
        score += 1

    # --------------------------------------------------------
    # PUT RSI
    # --------------------------------------------------------

    if 35 <= row["rsi"] <= 48:

        score += 2
        reasons.append("RSI BEARISH")

    elif 48 < row["rsi"] <= 52:

        score += 1
        reasons.append("RSI NEUTRAL-BEARISH")

    elif row["rsi"] < 30:

        score -= 2
        reasons.append("RSI OVERSOLD")

    # --------------------------------------------------------
    # PUT MACD
    # --------------------------------------------------------

    if (
        row["macd"] <
        row["macd_signal"] and
        row["macd_hist"] < 0
    ):
        score += 3
        reasons.append("MACD BEARISH")

    elif (
        row["macd"] <
        row["macd_signal"]
    ):
        score += 1

    # --------------------------------------------------------
    # PUT CANDLE
    # --------------------------------------------------------

    if candle == "BEARISH":

        score += 2
        reasons.append("BEARISH CANDLE")

    elif candle == "BULLISH":

        score -= 2
        reasons.append("BULLISH CANDLE")

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    if volume_ratio >= 1.20:

        score += 1
        reasons.append("HIGH VOLUME")

    elif volume_ratio < 0.70:

        score -= 2
        reasons.append("VERY LOW VOLUME")

    # --------------------------------------------------------
    # VOLATILITY
    # --------------------------------------------------------

    if (
        row["atr_pct"] < 0.025 or
        row["atr_pct"] > 0.80
    ):
        return None

    # --------------------------------------------------------
    # STRICT PUT
    # --------------------------------------------------------

    if (
        score >= 10 and
        row["adx"] >= 25 and
        row["di_minus"] >
        row["di_plus"] and
        candle == "BEARISH" and
        volume_ratio >= 0.70
    ):
        return {
            "score": score,
            "reasons": reasons,
            "volume_ratio": volume_ratio,
            "candle": candle
        }

    return None


# ============================================================
# MASTER SIGNAL
# ============================================================

def generate_signal(row):

    call = call_signal(row)
    put = put_signal(row)

    # Only one direction is allowed
    if call and not put:

        if call["score"] >= 13:
            quality = "HIGH"

        else:
            quality = "MEDIUM"

        return {
            "signal": "CALL",
            "quality": quality,
            "score": call["score"],
            "candle": call["candle"],
            "volume_ratio": call["volume_ratio"]
        }

    if put and not call:

        if put["score"] >= 12:
            quality = "HIGH"

        else:
            quality = "MEDIUM"

        return {
            "signal": "PUT",
            "quality": quality,
            "score": put["score"],
            "candle": put["candle"],
            "volume_ratio": put["volume_ratio"]
        }

    # If both directions trigger,
    # market is considered conflicted.
    return None


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(df, expiry):

    trades = []

    for i in range(
        len(df) - expiry
    ):

        row = df.iloc[i]

        signal_data = generate_signal(row)

        if signal_data is None:
            continue

        signal = signal_data["signal"]

        entry = row["close"]

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

        trades.append({
            "index": i,
            "signal": signal,
            "quality": signal_data["quality"],
            "score": signal_data["score"],
            "entry": entry,
            "exit": exit_price,
            "result": result
        })

    return pd.DataFrame(trades)


# ============================================================
# STATS
# ============================================================

def win_rate(data):

    wins = len(
        data[data["result"] == "WIN"]
    )

    losses = len(
        data[data["result"] == "LOSS"]
    )

    if wins + losses == 0:
        return 0

    return (
        wins /
        (wins + losses) *
        100
    )


def print_direction_stats(trades):

    print()
    print("DIRECTION ANALYSIS")

    for direction in [
        "CALL",
        "PUT"
    ]:

        data = trades[
            trades["signal"] == direction
        ]

        if data.empty:
            continue

        wins = len(
            data[data["result"] == "WIN"]
        )

        losses = len(
            data[data["result"] == "LOSS"]
        )

        print(
            f"{direction} -> "
            f"Trades: {len(data)} | "
            f"Wins: {wins} | "
            f"Losses: {losses} | "
            f"Win Rate: {round(win_rate(data), 2)} %"
        )


def print_quality_stats(trades):

    print()
    print("QUALITY ANALYSIS")

    for quality in [
        "HIGH",
        "MEDIUM"
    ]:

        data = trades[
            trades["quality"] == quality
        ]

        if data.empty:
            continue

        wins = len(
            data[data["result"] == "WIN"]
        )

        losses = len(
            data[data["result"] == "LOSS"]
        )

        print(
            f"{quality} -> "
            f"Trades: {len(data)} | "
            f"Wins: {wins} | "
            f"Losses: {losses} | "
            f"Win Rate: {round(win_rate(data), 2)} %"
        )


def print_score_stats(trades):

    print()
    print("SCORE ANALYSIS")

    if trades.empty:
        return

    bins = [
        (10, 11),
        (12, 12),
        (13, 13),
        (14, 20)
    ]

    for low, high in bins:

        data = trades[
            (trades["score"] >= low) &
            (trades["score"] <= high)
        ]

        if data.empty:
            continue

        print(
            f"Score {low}-{high} -> "
            f"Trades: {len(data)} | "
            f"Win Rate: {round(win_rate(data), 2)} %"
        )


def print_results(trades, expiry):

    print()
    print("=" * 70)
    print(
        f"EXPIRY: {expiry * 5} MINUTES"
    )
    print("=" * 70)

    if trades.empty:

        print("NO TRADES")
        return None

    total = len(trades)

    wins = len(
        trades[trades["result"] == "WIN"]
    )

    losses = len(
        trades[trades["result"] == "LOSS"]
    )

    draws = len(
        trades[trades["result"] == "DRAW"]
    )

    rate = win_rate(trades)

    print()
    print("TOTAL TRADES:", total)
    print("WINS:", wins)
    print("LOSSES:", losses)
    print("DRAWS:", draws)
    print(
        "WIN RATE:",
        round(rate, 2),
        "%"
    )

    print_direction_stats(
        trades
    )

    print_quality_stats(
        trades
    )

    print_score_stats(
        trades
    )

    return {
        "expiry": expiry * 5,
        "trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": rate
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print(BOT_NAME)
    print("=" * 70)

    print("Symbol:", SYMBOL)
    print("Market:", KRAKEN_PAIR)
    print("Timeframe:", INTERVAL)
    print("Started:", datetime.now())

    print()

    try:

        df = get_data()

        print(
            "Candles received:",
            len(df)
        )

        if len(df) < 100:

            print(
                "Not enough candles."
            )

            return

        df = calculate_indicators(
            df
        )

        results = []

        for expiry in EXPIRIES:

            trades = run_backtest(
                df,
                expiry
            )

            result = print_results(
                trades,
                expiry
            )

            if result:
                results.append(
                    result
                )

        print()
        print("=" * 70)
        print("FINAL COMPARISON")
        print("=" * 70)

        if results:

            comparison = pd.DataFrame(
                results
            )

            print(
                comparison[
                    [
                        "expiry",
                        "trades",
                        "wins",
                        "losses",
                        "win_rate"
                    ]
                ].to_string(
                    index=False
                )
            )

            best = comparison.loc[
                comparison["win_rate"].idxmax()
            ]

            print()
            print(
                "BEST HISTORICAL EXPIRY:",
                int(best["expiry"]),
                "minutes"
            )

            print(
                "BEST WIN RATE:",
                round(
                    best["win_rate"],
                    2
                ),
                "%"
            )

        print()
        print("=" * 70)
        print("IMPORTANT")
        print("=" * 70)

        print(
            "Historical backtest only."
        )

        print(
            "It does NOT guarantee future profitability."
        )

        print(
            "It does NOT reproduce Pocket Option "
            "execution, payout, spread or price feed."
        )

        print(
            "Win rate alone does not determine profitability."
        )

        print(
            "Do not use real money based only on this test."
        )

    except Exception as e:

        print()
        print("ERROR:", e)


if __name__ == "__main__":
    main()
