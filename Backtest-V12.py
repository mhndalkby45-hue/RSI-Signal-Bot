import requests
import pandas as pd
import ta
from datetime import datetime

BOT_NAME = "Smart Trading Signal Bot V12"

SYMBOL = "XBTUSD"
INTERVAL = 5

EXPIRIES = [5, 10, 15]

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

    response = requests.get(
        url,
        params=params,
        timeout=20
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

    df["time"] = pd.to_datetime(
        df["time"],
        unit="s"
    )

    for column in [
        "open",
        "high",
        "low",
        "close",
        "vwap",
        "volume"
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    return (
        df.sort_values("time")
        .reset_index(drop=True)
    )


# ============================================================
# INDICATORS
# ============================================================

def add_indicators(df):

    df = df.copy()

    df["ema9"] = ta.trend.EMAIndicator(
        df["close"],
        window=9
    ).ema_indicator()

    df["ema21"] = ta.trend.EMAIndicator(
        df["close"],
        window=21
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

    df["volume_avg"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    df["volume_ratio"] = (
        df["volume"] /
        df["volume_avg"]
    )

    df["range"] = (
        df["high"] -
        df["low"]
    )

    df["body"] = (
        df["close"] -
        df["open"]
    )

    df["body_ratio"] = (
        df["body"].abs() /
        df["range"].replace(0, pd.NA)
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
# MARKET REGIME
# ============================================================

def market_regime(row):

    adx = row["adx"]

    if adx < 25:
        trend = "WEAK"

    elif adx < 30:
        trend = "MODERATE"

    else:
        trend = "STRONG"

    if row["di_plus"] > row["di_minus"]:
        direction = "BULLISH"

    elif row["di_minus"] > row["di_plus"]:
        direction = "BEARISH"

    else:
        direction = "NEUTRAL"

    return trend, direction


# ============================================================
# ADAPTIVE SIGNAL ENGINE
# ============================================================

def adaptive_signal(row):

    trend, direction = market_regime(row)

    call = 0
    put = 0

    # --------------------------------------------------------
    # WEAK MARKET
    # --------------------------------------------------------
    # In V11 weak markets showed the best historical result.
    # Here we use a more conservative mean-reversion style:
    # extreme RSI + candle reversal.
    # --------------------------------------------------------

    if trend == "WEAK":

        if row["rsi"] <= 35:
            call += 3

        elif row["rsi"] >= 65:
            put += 3

        if (
            row["candle_direction"] == 1
            and row["body_ratio"] >= 0.55
        ):
            call += 2

        elif (
            row["candle_direction"] == -1
            and row["body_ratio"] >= 0.55
        ):
            put += 2

        # MACD confirmation
        if row["macd_hist"] > 0:
            call += 1

        elif row["macd_hist"] < 0:
            put += 1

    # --------------------------------------------------------
    # MODERATE MARKET
    # --------------------------------------------------------
    # V11 showed weak performance here.
    # Require stronger confirmation.
    # --------------------------------------------------------

    elif trend == "MODERATE":

        if direction == "BULLISH":

            if row["close"] > row["ema9"]:
                call += 3

            if row["macd"] > row["macd_signal"]:
                call += 2

            if row["rsi"] >= 50:
                call += 2

            if row["di_plus"] > row["di_minus"]:
                call += 2

        elif direction == "BEARISH":

            if row["close"] < row["ema9"]:
                put += 3

            if row["macd"] < row["macd_signal"]:
                put += 2

            if row["rsi"] < 50:
                put += 2

            if row["di_minus"] > row["di_plus"]:
                put += 2

    # --------------------------------------------------------
    # STRONG MARKET
    # --------------------------------------------------------
    # Follow the trend, but require multiple confirmations.
    # --------------------------------------------------------

    else:

        if direction == "BULLISH":

            if row["ema9"] > row["ema21"]:
                call += 3

            if row["close"] > row["ema9"]:
                call += 2

            if row["di_plus"] > row["di_minus"]:
                call += 3

            if row["macd"] > row["macd_signal"]:
                call += 2

            if row["macd_hist"] > 0:
                call += 1

            if 50 <= row["rsi"] <= 70:
                call += 1

        elif direction == "BEARISH":

            if row["ema9"] < row["ema21"]:
                put += 3

            if row["close"] < row["ema9"]:
                put += 2

            if row["di_minus"] > row["di_plus"]:
                put += 3

            if row["macd"] < row["macd_signal"]:
                put += 2

            if row["macd_hist"] < 0:
                put += 1

            if 30 <= row["rsi"] <= 50:
                put += 1

    # --------------------------------------------------------
    # VOLUME CONFIRMATION
    # --------------------------------------------------------

    if row["volume_ratio"] >= 1.20:

        if call > put:
            call += 1

        elif put > call:
            put += 1

    # Low volume does NOT create a signal.
    # It only prevents an extra confirmation.

    # --------------------------------------------------------
    # FINAL FILTER
    # --------------------------------------------------------

    difference = abs(call - put)

    if (
        call >= 7
        and call > put
        and difference >= 3
    ):

        signal = "CALL"
        score = call

    elif (
        put >= 7
        and put > call
        and difference >= 3
    ):

        signal = "PUT"
        score = put

    else:

        signal = "WAIT"
        score = max(call, put)

    # --------------------------------------------------------
    # QUALITY
    # --------------------------------------------------------

    if signal == "WAIT":

        quality = "NONE"

    elif score >= 11:

        quality = "HIGH"

    elif score >= 9:

        quality = "MEDIUM"

    else:

        quality = "LOW"

    return signal, score, quality, trend, direction


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(
    df,
    start_index,
    end_index,
    expiry
):

    trades = []

    step = expiry // INTERVAL

    if step < 1:
        step = 1

    last_index = min(
        end_index,
        len(df) - step - 1
    )

    for i in range(
        start_index,
        last_index
    ):

        row = df.iloc[i]

        (
            signal,
            score,
            quality,
            trend,
            direction
        ) = adaptive_signal(row)

        if signal == "WAIT":
            continue

        future_index = i + step

        if future_index >= len(df):
            break

        entry = row["close"]

        exit_price = (
            df.iloc[future_index]["close"]
        )

        if signal == "CALL":

            result = (
                "WIN"
                if exit_price > entry
                else "LOSS"
            )

        else:

            result = (
                "WIN"
                if exit_price < entry
                else "LOSS"
            )

        trades.append({
            "time": row["time"],
            "signal": signal,
            "score": score,
            "quality": quality,
            "trend": trend,
            "direction": direction,
            "rsi": row["rsi"],
            "adx": row["adx"],
            "volume_ratio":
                row["volume_ratio"],
            "result": result
        })

    return pd.DataFrame(trades)


# ============================================================
# ANALYSIS
# ============================================================

def analyze_group(
    trades,
    column
):

    if trades.empty:
        print("No trades.")
        return

    for name, group in trades.groupby(column):

        total = len(group)

        wins = (
            group["result"] == "WIN"
        ).sum()

        losses = (
            group["result"] == "LOSS"
        ).sum()

        rate = (
            wins / total * 100
            if total
            else 0
        )

        print(
            str(name),
            "-> Trades:",
            total,
            "| Wins:",
            wins,
            "| Losses:",
            losses,
            "| Win Rate:",
            round(rate, 2),
            "%"
        )


def print_results(
    trades,
    title
):

    print()
    print("-" * 65)
    print(title)
    print("-" * 65)

    if trades.empty:

        print("No trades.")
        return

    total = len(trades)

    wins = (
        trades["result"] == "WIN"
    ).sum()

    losses = (
        trades["result"] == "LOSS"
    ).sum()

    rate = wins / total * 100

    print(
        "TOTAL TRADES:",
        total
    )

    print(
        "WINS:",
        wins
    )

    print(
        "LOSSES:",
        losses
    )

    print(
        "WIN RATE:",
        round(rate, 2),
        "%"
    )

    print(
        "AVERAGE SCORE:",
        round(
            trades["score"].mean(),
            2
        )
    )

    print()
    print("CALL vs PUT")

    analyze_group(
        trades,
        "signal"
    )

    print()
    print("MARKET REGIME")

    analyze_group(
        trades,
        "trend"
    )

    print()
    print("MARKET DIRECTION")

    analyze_group(
        trades,
        "direction"
    )

    print()
    print("SIGNAL QUALITY")

    analyze_group(
        trades,
        "quality"
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
        "V12 uses adaptive rules by market regime."
    )

    print(
        "Test data is NOT used to modify the rules."
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

        development = run_backtest(
            df,
            0,
            split_index,
            expiry
        )

        test = run_backtest(
            df,
            split_index,
            len(df),
            expiry
        )

        print_results(
            development,
            "DEVELOPMENT / IN-SAMPLE"
        )

        print_results(
            test,
            "OUT-OF-SAMPLE / TEST"
        )

    print()
    print("=" * 65)
    print("V12 BACKTEST FINISHED")
    print("=" * 65)

    print()
    print(
        "IMPORTANT:"
    )

    print(
        "Historical close-to-close test only."
    )

    print(
        "This does not reproduce Pocket Option"
        " execution, payout, latency or exact feed."
    )

    print(
        "No backtest guarantees future profitability."
    )


if __name__ == "__main__":
    main()
