import requests
import pandas as pd
import ta
from datetime import datetime

BOT_NAME = "Smart Trading Signal Bot V8 - ANALYSIS BACKTEST"

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

    # Remove incomplete candle
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

    candle_range = row["high"] - row["low"]

    body = abs(
        row["close"] - row["open"]
    )

    if candle_range <= 0:
        return "NEUTRAL", 0

    body_ratio = body / candle_range

    if body_ratio < 0.55:
        return "NEUTRAL", body_ratio

    if row["close"] > row["open"]:
        return "BULLISH", body_ratio

    if row["close"] < row["open"]:
        return "BEARISH", body_ratio

    return "NEUTRAL", body_ratio


# ============================================================
# SIGNAL ENGINE
# ============================================================

def generate_signal(row):

    bullish = 0
    bearish = 0

    candle, body_ratio = candle_info(row)

    volume_ratio = (
        row["volume"] /
        row["volume_ma"]
        if row["volume_ma"] > 0
        else 0
    )

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    if (
        row["ema9"] >
        row["ema21"] >
        row["ema50"]
    ):
        bullish += 3

    elif (
        row["ema9"] <
        row["ema21"] <
        row["ema50"]
    ):
        bearish += 3

    # Price position
    if (
        row["close"] >
        row["ema9"] and
        row["close"] >
        row["ema21"]
    ):
        bullish += 2

    elif (
        row["close"] <
        row["ema9"] and
        row["close"] <
        row["ema21"]
    ):
        bearish += 2

    # ADX direction
    if row["adx"] >= 25:

        if row["di_plus"] > row["di_minus"]:
            bullish += 2

        elif row["di_minus"] > row["di_plus"]:
            bearish += 2

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    # RSI
    if 52 <= row["rsi"] <= 68:
        bullish += 2

    elif 32 <= row["rsi"] <= 48:
        bearish += 2

    # MACD
    if (
        row["macd"] >
        row["macd_signal"] and
        row["macd_hist"] > 0
    ):
        bullish += 2

    elif (
        row["macd"] <
        row["macd_signal"] and
        row["macd_hist"] < 0
    ):
        bearish += 2

    # --------------------------------------------------------
    # CANDLE
    # --------------------------------------------------------

    if candle == "BULLISH":
        bullish += 2

    elif candle == "BEARISH":
        bearish += 2

    # --------------------------------------------------------
    # MARKET QUALITY
    # --------------------------------------------------------

    if row["adx"] >= 30:
        market = "STRONG"

    elif row["adx"] >= 20:
        market = "MODERATE"

    else:
        market = "WEAK"

    # --------------------------------------------------------
    # VOLATILITY FILTER
    # --------------------------------------------------------

    # Avoid extremely tiny movements
    volatility_ok = row["atr_pct"] >= 0.025

    # Avoid extremely large abnormal candles
    volatility_not_extreme = row["atr_pct"] <= 0.80

    # --------------------------------------------------------
    # ALIGNMENT
    # --------------------------------------------------------

    difference = abs(
        bullish - bearish
    )

    signal = "WAIT"

    # Strict CALL
    if (
        bullish >= 9 and
        bullish - bearish >= 4 and
        row["adx"] >= 25 and
        row["di_plus"] > row["di_minus"] and
        candle == "BULLISH" and
        volume_ratio >= 0.80 and
        volatility_ok and
        volatility_not_extreme
    ):
        signal = "CALL"

    # Strict PUT
    elif (
        bearish >= 9 and
        bearish - bullish >= 4 and
        row["adx"] >= 25 and
        row["di_minus"] > row["di_plus"] and
        candle == "BEARISH" and
        volume_ratio >= 0.80 and
        volatility_ok and
        volatility_not_extreme
    ):
        signal = "PUT"

    # --------------------------------------------------------
    # QUALITY
    # --------------------------------------------------------

    quality = "LOW"

    if signal != "WAIT":

        strength = max(
            bullish,
            bearish
        )

        if (
            strength >= 13 and
            difference >= 6 and
            row["adx"] >= 30 and
            volume_ratio >= 1.20 and
            body_ratio >= 0.60
        ):
            quality = "HIGH"

        elif (
            strength >= 10 and
            difference >= 4
        ):
            quality = "MEDIUM"

        else:
            quality = "LOW"

    return {
        "signal": signal,
        "quality": quality,
        "bullish": bullish,
        "bearish": bearish,
        "market": market,
        "volume_ratio": volume_ratio,
        "rsi": row["rsi"],
        "adx": row["adx"],
        "candle": candle,
        "ema_gap": row["ema_gap_pct"],
        "atr_pct": row["atr_pct"]
    }


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(df, expiry):

    trades = []

    for i in range(
        len(df) - expiry
    ):

        row = df.iloc[i]

        analysis = generate_signal(row)

        signal = analysis["signal"]

        if signal == "WAIT":
            continue

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
            "quality": analysis["quality"],
            "market": analysis["market"],
            "entry": entry,
            "exit": exit_price,
            "result": result,
            "volume_ratio": analysis["volume_ratio"],
            "rsi": analysis["rsi"],
            "adx": analysis["adx"],
            "candle": analysis["candle"]
        })

    return pd.DataFrame(trades)


# ============================================================
# ANALYSIS
# ============================================================

def calculate_rate(data):

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


def print_breakdown(trades):

    print()
    print("SIGNAL DIRECTION")

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

        rate = calculate_rate(data)

        print(
            f"{direction} -> "
            f"Trades: {len(data)} | "
            f"Wins: {wins} | "
            f"Losses: {losses} | "
            f"Win Rate: {round(rate, 2)} %"
        )

    print()
    print("MARKET CONDITION")

    for market in [
        "STRONG",
        "MODERATE",
        "WEAK"
    ]:

        data = trades[
            trades["market"] == market
        ]

        if data.empty:
            continue

        rate = calculate_rate(data)

        print(
            f"{market} -> "
            f"Trades: {len(data)} | "
            f"Win Rate: {round(rate, 2)} %"
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

    win_rate = calculate_rate(
        trades
    )

    print()
    print("TOTAL TRADES:", total)
    print("WINS:", wins)
    print("LOSSES:", losses)
    print("DRAWS:", draws)
    print(
        "WIN RATE:",
        round(win_rate, 2),
        "%"
    )

    print()
    print("QUALITY BREAKDOWN")

    for quality in [
        "HIGH",
        "MEDIUM",
        "LOW"
    ]:

        data = trades[
            trades["quality"] == quality
        ]

        if data.empty:
            continue

        rate = calculate_rate(data)

        wins_q = len(
            data[data["result"] == "WIN"]
        )

        losses_q = len(
            data[data["result"] == "LOSS"]
        )

        print(
            f"{quality} -> "
            f"Trades: {len(data)} | "
            f"Wins: {wins_q} | "
            f"Losses: {losses_q} | "
            f"Win Rate: {round(rate, 2)} %"
        )

    print_breakdown(trades)

    return {
        "expiry": expiry * 5,
        "trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate
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

        df = calculate_indicators(df)

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
                results.append(result)

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
            "This is historical testing only."
        )

        print(
            "It is NOT a guarantee of future profit."
        )

        print(
            "It does NOT reproduce Pocket Option "
            "execution, payout, spread or price feed."
        )

        print(
            "WIN RATE is not the same as profitability."
        )

        print(
            "Do not use real money based only "
            "on this backtest."
        )

    except Exception as e:

        print()
        print("ERROR:", e)


if __name__ == "__main__":
    main()
