import requests
import pandas as pd
import ta
from datetime import datetime

BOT_NAME = "Smart Trading Signal Bot V10"

SYMBOL = "XBTUSD"
INTERVAL = 5

EXPIRIES = [5, 10, 15]

# تقسيم البيانات:
# 60% للتطوير
# 40% اختبار خارج العينة
DEVELOPMENT_RATIO = 0.60

# ============================================================
# DATA
# ============================================================

def get_data():
    url = "https://api.kraken.com/0/public/OHLC"

    params = {
        "pair": SYMBOL,
        "interval": INTERVAL
    }

    response = requests.get(url, params=params, timeout=20)
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

    df["time"] = pd.to_datetime(df["time"], unit="s")

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "vwap",
        "volume"
    ]

    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("time").reset_index(drop=True)

    return df


# ============================================================
# INDICATORS
# ============================================================

def add_indicators(df):

    df = df.copy()

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

    df["volume_avg"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    df["volume_ratio"] = (
        df["volume"] /
        df["volume_avg"]
    )

    # Candle body
    df["body"] = (
        df["close"] -
        df["open"]
    )

    df["candle_range"] = (
        df["high"] -
        df["low"]
    )

    df["body_ratio"] = (
        df["body"].abs() /
        df["candle_range"].replace(0, pd.NA)
    )

    df["candle_direction"] = 0

    df.loc[
        df["close"] > df["open"],
        "candle_direction"
    ] = 1

    df.loc[
        df["close"] < df["open"],
        "candle_direction"
    ] = -1

    df = df.dropna().reset_index(drop=True)

    return df


# ============================================================
# SIGNAL ENGINE
# ============================================================

def generate_signal(row):

    call_score = 0
    put_score = 0

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    if row["ema9"] > row["ema21"]:
        call_score += 3
    elif row["ema9"] < row["ema21"]:
        put_score += 3

    if row["close"] > row["ema9"]:
        call_score += 2
    elif row["close"] < row["ema9"]:
        put_score += 2

    # --------------------------------------------------------
    # ADX DIRECTION
    # --------------------------------------------------------

    if row["adx"] >= 25:

        if row["di_plus"] > row["di_minus"]:
            call_score += 3

        elif row["di_minus"] > row["di_plus"]:
            put_score += 3

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    if 50 <= row["rsi"] <= 70:
        call_score += 2

    elif 30 <= row["rsi"] < 50:
        put_score += 2

    # Avoid extreme RSI
    if row["rsi"] >= 75:
        call_score -= 2

    if row["rsi"] <= 25:
        put_score -= 2

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    if row["macd"] > row["macd_signal"]:
        call_score += 2
    else:
        put_score += 2

    # --------------------------------------------------------
    # MACD HISTOGRAM
    # --------------------------------------------------------

    if row["macd_hist"] > 0:
        call_score += 1
    elif row["macd_hist"] < 0:
        put_score += 1

    # --------------------------------------------------------
    # CANDLE
    # --------------------------------------------------------

    if row["body_ratio"] >= 0.55:

        if row["candle_direction"] == 1:
            call_score += 2

        elif row["candle_direction"] == -1:
            put_score += 2

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    volume_ratio = row["volume_ratio"]

    if volume_ratio >= 1.20:

        if call_score > put_score:
            call_score += 1

        elif put_score > call_score:
            put_score += 1

    elif volume_ratio < 0.80:

        # Low volume reduces confidence
        if call_score > put_score:
            call_score -= 1

        elif put_score > call_score:
            put_score -= 1

    # --------------------------------------------------------
    # FINAL DECISION
    # --------------------------------------------------------

    difference = abs(call_score - put_score)

    # Minimum edge required
    if call_score >= 10 and call_score > put_score and difference >= 3:

        signal = "CALL"
        score = call_score

    elif put_score >= 10 and put_score > call_score and difference >= 3:

        signal = "PUT"
        score = put_score

    else:

        signal = "WAIT"
        score = max(call_score, put_score)

    # --------------------------------------------------------
    # QUALITY
    # --------------------------------------------------------

    if signal == "WAIT":
        quality = "NONE"

    elif score >= 14:
        quality = "HIGH"

    elif score >= 11:
        quality = "MEDIUM"

    else:
        quality = "LOW"

    return signal, score, quality


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(df, start_index, end_index, expiry_minutes):

    trades = []

    wins = 0
    losses = 0

    max_losing_streak = 0
    losing_streak = 0

    call_trades = 0
    call_wins = 0

    put_trades = 0
    put_wins = 0

    high_trades = 0
    high_wins = 0

    medium_trades = 0
    medium_wins = 0

    low_trades = 0
    low_wins = 0

    score_values = []

    step = expiry_minutes // INTERVAL

    if step < 1:
        step = 1

    # Leave enough candles for the future expiry
    last_index = min(
        end_index,
        len(df) - step - 1
    )

    for i in range(start_index, last_index):

        row = df.iloc[i]

        signal, score, quality = generate_signal(row)

        if signal == "WAIT":
            continue

        future_index = i + step

        if future_index >= len(df):
            break

        entry_price = row["close"]
        exit_price = df.iloc[future_index]["close"]

        if signal == "CALL":

            result = (
                "WIN"
                if exit_price > entry_price
                else "LOSS"
            )

        else:

            result = (
                "WIN"
                if exit_price < entry_price
                else "LOSS"
            )

        trades.append({
            "time": row["time"],
            "signal": signal,
            "score": score,
            "quality": quality,
            "entry": entry_price,
            "exit": exit_price,
            "result": result
        })

        score_values.append(score)

        if result == "WIN":

            wins += 1
            losing_streak = 0

        else:

            losses += 1
            losing_streak += 1

            max_losing_streak = max(
                max_losing_streak,
                losing_streak
            )

        # Direction
        if signal == "CALL":

            call_trades += 1

            if result == "WIN":
                call_wins += 1

        else:

            put_trades += 1

            if result == "WIN":
                put_wins += 1

        # Quality
        if quality == "HIGH":

            high_trades += 1

            if result == "WIN":
                high_wins += 1

        elif quality == "MEDIUM":

            medium_trades += 1

            if result == "WIN":
                medium_wins += 1

        elif quality == "LOW":

            low_trades += 1

            if result == "WIN":
                low_wins += 1

    total = wins + losses

    win_rate = (
        wins / total * 100
        if total > 0
        else 0
    )

    call_rate = (
        call_wins / call_trades * 100
        if call_trades > 0
        else 0
    )

    put_rate = (
        put_wins / put_trades * 100
        if put_trades > 0
        else 0
    )

    high_rate = (
        high_wins / high_trades * 100
        if high_trades > 0
        else 0
    )

    medium_rate = (
        medium_wins / medium_trades * 100
        if medium_trades > 0
        else 0
    )

    low_rate = (
        low_wins / low_trades * 100
        if low_trades > 0
        else 0
    )

    average_score = (
        sum(score_values) / len(score_values)
        if score_values
        else 0
    )

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "max_losing_streak": max_losing_streak,

        "call_trades": call_trades,
        "call_wins": call_wins,
        "call_rate": call_rate,

        "put_trades": put_trades,
        "put_wins": put_wins,
        "put_rate": put_rate,

        "high_trades": high_trades,
        "high_wins": high_wins,
        "high_rate": high_rate,

        "medium_trades": medium_trades,
        "medium_wins": medium_wins,
        "medium_rate": medium_rate,

        "low_trades": low_trades,
        "low_wins": low_wins,
        "low_rate": low_rate,

        "average_score": average_score
    }


# ============================================================
# PRINT RESULTS
# ============================================================

def print_results(label, results):

    print()
    print("-" * 65)
    print(label)
    print("-" * 65)

    print(
        "TOTAL TRADES:",
        results["total"]
    )

    print(
        "WINS:",
        results["wins"]
    )

    print(
        "LOSSES:",
        results["losses"]
    )

    print(
        "WIN RATE:",
        round(results["win_rate"], 2),
        "%"
    )

    print(
        "MAX LOSING STREAK:",
        results["max_losing_streak"]
    )

    print(
        "AVERAGE SCORE:",
        round(results["average_score"], 2)
    )

    print()
    print("DIRECTION")

    print(
        "CALL -> Trades:",
        results["call_trades"],
        "| Wins:",
        results["call_wins"],
        "| Win Rate:",
        round(results["call_rate"], 2),
        "%"
    )

    print(
        "PUT  -> Trades:",
        results["put_trades"],
        "| Wins:",
        results["put_wins"],
        "| Win Rate:",
        round(results["put_rate"], 2),
        "%"
    )

    print()
    print("QUALITY")

    print(
        "HIGH -> Trades:",
        results["high_trades"],
        "| Wins:",
        results["high_wins"],
        "| Win Rate:",
        round(results["high_rate"], 2),
        "%"
    )

    print(
        "MEDIUM -> Trades:",
        results["medium_trades"],
        "| Wins:",
        results["medium_wins"],
        "| Win Rate:",
        round(results["medium_rate"], 2),
        "%"
    )

    print(
        "LOW -> Trades:",
        results["low_trades"],
        "| Wins:",
        results["low_wins"],
        "| Win Rate:",
        round(results["low_rate"], 2),
        "%"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 65)
    print(BOT_NAME)
    print("=" * 65)

    print(
        "Symbol:",
        SYMBOL
    )

    print(
        "Timeframe:",
        str(INTERVAL) + "m"
    )

    print(
        "Started:",
        datetime.now()
    )

    print()

    df = get_data()

    print(
        "Candles received:",
        len(df)
    )

    df = add_indicators(df)

    print(
        "Candles after indicators:",
        len(df)
    )

    split_index = int(
        len(df) * DEVELOPMENT_RATIO
    )

    print()
    print(
        "Development candles:",
        split_index
    )

    print(
        "Out-of-sample candles:",
        len(df) - split_index
    )

    print()
    print(
        "IMPORTANT: Out-of-sample data is NOT used to modify rules."
    )

    for expiry in EXPIRIES:

        print()
        print("=" * 65)
        print(
            "EXPIRY:",
            expiry,
            "MINUTES"
        )
        print("=" * 65)

        development_results = run_backtest(
            df,
            0,
            split_index,
            expiry
        )

        test_results = run_backtest(
            df,
            split_index,
            len(df),
            expiry
        )

        print_results(
            "DEVELOPMENT / IN-SAMPLE",
            development_results
        )

        print_results(
            "OUT-OF-SAMPLE / TEST",
            test_results
        )

        # ----------------------------------------------------
        # Stability check
        # ----------------------------------------------------

        difference = abs(
            development_results["win_rate"]
            -
            test_results["win_rate"]
        )

        print()
        print("STABILITY CHECK")
        print(
            "Win Rate Difference:",
            round(difference, 2),
            "percentage points"
        )

        if (
            test_results["total"] >= 20
            and
            test_results["win_rate"] >= 55
            and
            difference <= 7
        ):

            print(
                "STATUS: PROMISING - NEEDS MORE DATA"
            )

        elif test_results["total"] < 20:

            print(
                "STATUS: INSUFFICIENT TEST SAMPLE"
            )

        else:

            print(
                "STATUS: NO CLEAR EDGE"
            )

    print()
    print("=" * 65)
    print("V10 BACKTEST FINISHED")
    print("=" * 65)

    print()
    print(
        "WARNING: This is a historical close-to-close test."
    )

    print(
        "It does not reproduce Pocket Option execution,"
        " payout, spread, latency or price feed."
    )

    print(
        "Do NOT use the result alone for real-money trading."
    )


if __name__ == "__main__":
    main()
