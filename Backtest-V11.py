import requests
import pandas as pd
import ta
from datetime import datetime

BOT_NAME = "Smart Trading Signal Bot V11"

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

    df["time"] = pd.to_datetime(
        df["time"],
        unit="s"
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

    df = df.sort_values(
        "time"
    ).reset_index(drop=True)

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

    df["macd_signal"] = (
        macd.macd_signal()
    )

    df["macd_hist"] = (
        macd.macd_diff()
    )

    adx = ta.trend.ADXIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    )

    df["adx"] = adx.adx()

    df["di_plus"] = (
        adx.adx_pos()
    )

    df["di_minus"] = (
        adx.adx_neg()
    )

    df["volume_avg"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    df["volume_ratio"] = (
        df["volume"] /
        df["volume_avg"]
    )

    df["candle_range"] = (
        df["high"] -
        df["low"]
    )

    df["body"] = (
        df["close"] -
        df["open"]
    )

    df["body_ratio"] = (
        df["body"].abs() /
        df["candle_range"].replace(
            0,
            pd.NA
        )
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

    df = df.dropna().reset_index(
        drop=True
    )

    return df


# ============================================================
# SIGNAL
# ============================================================

def generate_signal(row):

    call_score = 0
    put_score = 0

    # -----------------------------
    # EMA TREND
    # -----------------------------

    if row["ema9"] > row["ema21"]:
        call_score += 3

    elif row["ema9"] < row["ema21"]:
        put_score += 3

    # -----------------------------
    # PRICE VS EMA9
    # -----------------------------

    if row["close"] > row["ema9"]:
        call_score += 2

    elif row["close"] < row["ema9"]:
        put_score += 2

    # -----------------------------
    # ADX + DI
    # -----------------------------

    if row["adx"] >= 25:

        if row["di_plus"] > row["di_minus"]:
            call_score += 3

        elif row["di_minus"] > row["di_plus"]:
            put_score += 3

    # -----------------------------
    # RSI
    # -----------------------------

    if 50 <= row["rsi"] <= 70:
        call_score += 2

    elif 30 <= row["rsi"] < 50:
        put_score += 2

    # Extreme RSI penalty

    if row["rsi"] >= 75:
        call_score -= 2

    if row["rsi"] <= 25:
        put_score -= 2

    # -----------------------------
    # MACD
    # -----------------------------

    if row["macd"] > row["macd_signal"]:
        call_score += 2

    else:
        put_score += 2

    # -----------------------------
    # MACD HISTOGRAM
    # -----------------------------

    if row["macd_hist"] > 0:
        call_score += 1

    elif row["macd_hist"] < 0:
        put_score += 1

    # -----------------------------
    # CANDLE
    # -----------------------------

    if row["body_ratio"] >= 0.55:

        if row["candle_direction"] == 1:
            call_score += 2

        elif row["candle_direction"] == -1:
            put_score += 2

    # -----------------------------
    # VOLUME
    # -----------------------------

    if row["volume_ratio"] >= 1.20:

        if call_score > put_score:
            call_score += 1

        elif put_score > call_score:
            put_score += 1

    elif row["volume_ratio"] < 0.80:

        if call_score > put_score:
            call_score -= 1

        elif put_score > call_score:
            put_score -= 1

    # -----------------------------
    # SIGNAL
    # -----------------------------

    difference = abs(
        call_score - put_score
    )

    if (
        call_score >= 10
        and
        call_score > put_score
        and
        difference >= 3
    ):

        signal = "CALL"
        score = call_score

    elif (
        put_score >= 10
        and
        put_score > call_score
        and
        difference >= 3
    ):

        signal = "PUT"
        score = put_score

    else:

        signal = "WAIT"
        score = max(
            call_score,
            put_score
        )

    # -----------------------------
    # QUALITY
    # -----------------------------

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
# MARKET REGIME
# ============================================================

def get_regime(row):

    adx = row["adx"]
    volume = row["volume_ratio"]

    # Trend strength

    if adx >= 30:
        trend_strength = "STRONG"

    elif adx >= 25:
        trend_strength = "MODERATE"

    else:
        trend_strength = "WEAK"

    # Direction

    if row["di_plus"] > row["di_minus"]:
        direction = "BULLISH"

    elif row["di_minus"] > row["di_plus"]:
        direction = "BEARISH"

    else:
        direction = "NEUTRAL"

    # Volume

    if volume >= 1.20:
        volume_state = "HIGH_VOLUME"

    elif volume < 0.80:
        volume_state = "LOW_VOLUME"

    else:
        volume_state = "NORMAL_VOLUME"

    # RSI zone

    if row["rsi"] >= 70:
        rsi_zone = "OVERBOUGHT"

    elif row["rsi"] <= 30:
        rsi_zone = "OVERSOLD"

    elif row["rsi"] >= 50:
        rsi_zone = "BULLISH_RSI"

    else:
        rsi_zone = "BEARISH_RSI"

    # EMA regime

    if row["ema9"] > row["ema21"]:
        ema_regime = "EMA_BULLISH"

    else:
        ema_regime = "EMA_BEARISH"

    return {
        "trend_strength": trend_strength,
        "direction": direction,
        "volume_state": volume_state,
        "rsi_zone": rsi_zone,
        "ema_regime": ema_regime
    }


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(
    df,
    start_index,
    end_index,
    expiry_minutes
):

    trades = []

    step = expiry_minutes // INTERVAL

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

        signal, score, quality = (
            generate_signal(row)
        )

        if signal == "WAIT":
            continue

        future_index = i + step

        if future_index >= len(df):
            break

        entry_price = row["close"]

        exit_price = (
            df.iloc[future_index]["close"]
        )

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

        regime = get_regime(row)

        trades.append({
            "time": row["time"],
            "signal": signal,
            "score": score,
            "quality": quality,
            "result": result,
            "adx": row["adx"],
            "rsi": row["rsi"],
            "volume_ratio": row[
                "volume_ratio"
            ],
            "trend_strength":
                regime["trend_strength"],
            "direction":
                regime["direction"],
            "volume_state":
                regime["volume_state"],
            "rsi_zone":
                regime["rsi_zone"],
            "ema_regime":
                regime["ema_regime"]
        })

    return pd.DataFrame(trades)


# ============================================================
# GROUP ANALYSIS
# ============================================================

def analyze_group(
    trades,
    column,
    title
):

    print()
    print(
        "###",
        title,
        "###"
    )

    if trades.empty:
        print("No trades.")
        return

    groups = trades.groupby(column)

    for name, group in groups:

        total = len(group)

        wins = (
            group["result"] == "WIN"
        ).sum()

        losses = (
            group["result"] == "LOSS"
        ).sum()

        win_rate = (
            wins / total * 100
            if total > 0
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
            round(
                win_rate,
                2
            ),
            "%"
        )


# ============================================================
# OVERALL RESULTS
# ============================================================

def print_overall(
    trades,
    label
):

    print()
    print("-" * 65)
    print(label)
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

    win_rate = (
        wins / total * 100
    )

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
        round(win_rate, 2),
        "%"
    )

    print(
        "AVERAGE SCORE:",
        round(
            trades["score"].mean(),
            2
        )
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
        "V11 analyzes market conditions."
    )

    print(
        "Rules are NOT optimized using test data."
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

        development_trades = run_backtest(
            df,
            0,
            split_index,
            expiry
        )

        test_trades = run_backtest(
            df,
            split_index,
            len(df),
            expiry
        )

        print_overall(
            development_trades,
            "DEVELOPMENT / IN-SAMPLE"
        )

        print_overall(
            test_trades,
            "OUT-OF-SAMPLE / TEST"
        )

        # ====================================================
        # OUT-OF-SAMPLE REGIME ANALYSIS
        # ====================================================

        print()
        print(
            "OUT-OF-SAMPLE MARKET REGIME ANALYSIS"
        )

        analyze_group(
            test_trades,
            "trend_strength",
            "TREND STRENGTH"
        )

        analyze_group(
            test_trades,
            "direction",
            "MARKET DIRECTION"
        )

        analyze_group(
            test_trades,
            "volume_state",
            "VOLUME CONDITION"
        )

        analyze_group(
            test_trades,
            "rsi_zone",
            "RSI ZONE"
        )

        analyze_group(
            test_trades,
            "ema_regime",
            "EMA REGIME"
        )

        analyze_group(
            test_trades,
            "signal",
            "CALL vs PUT"
        )

        analyze_group(
            test_trades,
            "quality",
            "SIGNAL QUALITY"
        )

    print()
    print("=" * 65)
    print("V11 BACKTEST FINISHED")
    print("=" * 65)

    print()
    print(
        "IMPORTANT:"
    )

    print(
        "These results are historical close-to-close results."
    )

    print(
        "They do NOT reproduce Pocket Option execution,"
        " payout, spread, latency or its exact price feed."
    )

    print(
        "No result here guarantees future profitability."
    )


if __name__ == "__main__":
    main()
