import requests
import pandas as pd
import ta
from datetime import datetime

BOT_NAME = "Smart Trading Signal Bot V7 - STRICT BACKTEST"

SYMBOL = "BTCUSD"
KRAKEN_PAIR = "XBTUSD"
INTERVAL = "5m"

CANDLE_LIMIT = 720

# 1 = 5 minutes, 2 = 10 minutes, 3 = 15 minutes
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

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise Exception(data["error"])

    result = data["result"]

    pair_key = [k for k in result.keys() if k != "last"][0]

    rows = result[pair_key]

    df = pd.DataFrame(
        rows,
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

    numeric_cols = [
        "open",
        "high",
        "low",
        "close",
        "vwap",
        "volume"
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["time"] = pd.to_datetime(df["time"], unit="s")

    df = df.dropna().copy()

    # Remove current incomplete candle
    if len(df) > 1:
        df = df.iloc[:-1].copy()

    df = df.tail(CANDLE_LIMIT).reset_index(drop=True)

    return df


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(df):

    df["ema9"] = ta.trend.EMAIndicator(
        close=df["close"],
        window=9
    ).ema_indicator()

    df["ema21"] = ta.trend.EMAIndicator(
        close=df["close"],
        window=21
    ).ema_indicator()

    df["ema50"] = ta.trend.EMAIndicator(
        close=df["close"],
        window=50
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

    df["volume_ma"] = df["volume"].rolling(20).mean()

    # ATR for volatility filter
    atr = ta.volatility.AverageTrueRange(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    )

    df["atr"] = atr.average_true_range()

    # EMA separation
    df["ema_distance"] = (
        (df["ema9"] - df["ema21"]).abs()
        / df["close"]
    ) * 100

    df = df.dropna().reset_index(drop=True)

    return df


# ============================================================
# CANDLE ANALYSIS
# ============================================================

def candle_direction(row):

    body = abs(row["close"] - row["open"])

    candle_range = row["high"] - row["low"]

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
# STRICT SIGNAL ENGINE
# ============================================================

def generate_signal(row):

    bullish = 0
    bearish = 0

    reasons = []

    candle, body_ratio = candle_direction(row)

    volume_ratio = (
        row["volume"] / row["volume_ma"]
        if row["volume_ma"] > 0
        else 0
    )

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    # EMA structure
    if row["ema9"] > row["ema21"] > row["ema50"]:
        bullish += 3
        reasons.append("EMA STRUCTURE BULLISH")

    elif row["ema9"] < row["ema21"] < row["ema50"]:
        bearish += 3
        reasons.append("EMA STRUCTURE BEARISH")

    else:
        reasons.append("EMA STRUCTURE MIXED")

    # Price location
    if row["close"] > row["ema9"] and row["close"] > row["ema21"]:
        bullish += 2
        reasons.append("PRICE ABOVE EMA9/EMA21")

    elif row["close"] < row["ema9"] and row["close"] < row["ema21"]:
        bearish += 2
        reasons.append("PRICE BELOW EMA9/EMA21")

    # ADX + DI
    if row["adx"] >= 25:

        if row["di_plus"] > row["di_minus"]:
            bullish += 2
            reasons.append("ADX BULLISH DIRECTION")

        elif row["di_minus"] > row["di_plus"]:
            bearish += 2
            reasons.append("ADX BEARISH DIRECTION")

    else:
        reasons.append("ADX WEAK")

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    # RSI
    if 52 <= row["rsi"] <= 68:
        bullish += 2
        reasons.append("RSI BULLISH ZONE")

    elif 32 <= row["rsi"] <= 48:
        bearish += 2
        reasons.append("RSI BEARISH ZONE")

    elif row["rsi"] > 70:
        reasons.append("RSI OVERBOUGHT")

    elif row["rsi"] < 30:
        reasons.append("RSI OVERSOLD")

    # MACD
    if (
        row["macd"] > row["macd_signal"]
        and row["macd_hist"] > 0
    ):
        bullish += 2
        reasons.append("MACD MOMENTUM BULLISH")

    elif (
        row["macd"] < row["macd_signal"]
        and row["macd_hist"] < 0
    ):
        bearish += 2
        reasons.append("MACD MOMENTUM BEARISH")

    # --------------------------------------------------------
    # CANDLE CONFIRMATION
    # --------------------------------------------------------

    if candle == "BULLISH":
        bullish += 2
        reasons.append("BULLISH CANDLE")

    elif candle == "BEARISH":
        bearish += 2
        reasons.append("BEARISH CANDLE")

    else:
        reasons.append("CANDLE NEUTRAL")

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    if volume_ratio >= 1.20:
        reasons.append("HIGH VOLUME")

    elif volume_ratio >= 0.80:
        reasons.append("NORMAL VOLUME")

    else:
        reasons.append("LOW VOLUME")

    # --------------------------------------------------------
    # VOLATILITY
    # --------------------------------------------------------

    volatility_ok = row["atr"] > 0

    # --------------------------------------------------------
    # DECISION
    # --------------------------------------------------------

    difference = abs(bullish - bearish)

    signal = "WAIT"
    quality = "LOW"

    # Strict CALL
    if (
        bullish >= 9
        and bullish - bearish >= 4
        and row["adx"] >= 25
        and row["di_plus"] > row["di_minus"]
        and candle == "BULLISH"
        and volume_ratio >= 0.80
        and volatility_ok
    ):
        signal = "CALL"

    # Strict PUT
    elif (
        bearish >= 9
        and bearish - bullish >= 4
        and row["adx"] >= 25
        and row["di_minus"] > row["di_plus"]
        and candle == "BEARISH"
        and volume_ratio >= 0.80
        and volatility_ok
    ):
        signal = "PUT"

    # --------------------------------------------------------
    # QUALITY
    # --------------------------------------------------------

    if signal != "WAIT":

        strength = max(bullish, bearish)

        if (
            strength >= 13
            and difference >= 6
            and volume_ratio >= 1.20
            and row["adx"] >= 30
        ):
            quality = "HIGH"

        elif (
            strength >= 10
            and difference >= 4
        ):
            quality = "MEDIUM"

        else:
            quality = "LOW"

    return signal, quality, bullish, bearish, reasons


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(df, expiry):

    trades = []

    # Need future candles
    for i in range(len(df) - expiry):

        row = df.iloc[i]

        signal, quality, bullish, bearish, reasons = generate_signal(row)

        if signal == "WAIT":
            continue

        entry = row["close"]

        exit_price = df.iloc[i + expiry]["close"]

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
            "quality": quality,
            "bullish": bullish,
            "bearish": bearish,
            "entry": entry,
            "exit": exit_price,
            "result": result
        })

    return pd.DataFrame(trades)


# ============================================================
# STATISTICS
# ============================================================

def print_results(trades, expiry):

    print()
    print("=" * 70)
    print(f"EXPIRY: {expiry * 5} MINUTES")
    print("=" * 70)

    if trades.empty:

        print("NO TRADES")
        return

    total = len(trades)

    wins = len(trades[trades["result"] == "WIN"])
    losses = len(trades[trades["result"] == "LOSS"])
    draws = len(trades[trades["result"] == "DRAW"])

    win_rate = (
        wins / (wins + losses) * 100
        if wins + losses > 0
        else 0
    )

    print()
    print("TOTAL TRADES:", total)
    print("WINS:", wins)
    print("LOSSES:", losses)
    print("DRAWS:", draws)
    print("WIN RATE:", round(win_rate, 2), "%")

    print()
    print("QUALITY BREAKDOWN")

    for quality in ["HIGH", "MEDIUM", "LOW"]:

        q = trades[trades["quality"] == quality]

        if q.empty:
            continue

        q_wins = len(q[q["result"] == "WIN"])
        q_losses = len(q[q["result"] == "LOSS"])

        q_rate = (
            q_wins / (q_wins + q_losses) * 100
            if q_wins + q_losses > 0
            else 0
        )

        print(
            f"{quality} -> Trades: {len(q)} | "
            f"Wins: {q_wins} | "
            f"Losses: {q_losses} | "
            f"Win Rate: {round(q_rate, 2)} %"
        )

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

        print("Candles received:", len(df))

        if len(df) < 100:
            print("Not enough candles.")
            return

        df = calculate_indicators(df)

        results = []

        for expiry in EXPIRIES:

            trades = run_backtest(df, expiry)

            result = print_results(trades, expiry)

            if result:
                results.append(result)

        print()
        print("=" * 70)
        print("FINAL COMPARISON")
        print("=" * 70)

        if results:

            comparison = pd.DataFrame(results)

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
                round(best["win_rate"], 2),
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
            "It does NOT reproduce Pocket Option execution, "
            "payout, spread or price feed."
        )

        print(
            "WIN RATE is not the same as profitability."
        )

        print(
            "Do not use real money based only on this backtest."
        )


    except Exception as e:

        print()
        print("ERROR:", e)


if __name__ == "__main__":
    main()
