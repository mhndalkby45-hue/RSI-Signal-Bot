import requests
import pandas as pd
import numpy as np


# ============================================================
# V15 STRATEGY ANALYZER
# ============================================================

DATA_SYMBOL = "BTC-USD"
INTERVAL = "5m"
LIMIT = 1000

EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 50

RSI_PERIOD = 14

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

ADX_PERIOD = 14

EXPIRY_CANDLES = 1

STAKE = 1.0
PAYOUT = 0.80


# ============================================================
# DOWNLOAD DATA
# ============================================================

def get_data():

    print("Downloading market data...")

    url = (
        "https://api.exchange.coinbase.com/"
        "products/"
        + DATA_SYMBOL
        + "/candles"
    )

    all_candles = []

    end_time = int(
        pd.Timestamp.now(
            tz="UTC"
        ).timestamp()
    )

    while len(all_candles) < LIMIT:

        start_time = (
            end_time -
            (300 * 300)
        )

        params = {
            "start": start_time,
            "end": end_time,
            "granularity": 300
        }

        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        response.raise_for_status()

        batch = response.json()

        if not batch:
            break

        all_candles.extend(batch)

        oldest_time = min(
            candle[0]
            for candle in batch
        )

        end_time = oldest_time - 300

        if len(batch) < 300:
            break

    columns = [
        "time",
        "low",
        "high",
        "open",
        "close",
        "volume"
    ]

    df = pd.DataFrame(
        all_candles[:LIMIT],
        columns=columns
    )

    df["time"] = pd.to_datetime(
        df["time"],
        unit="s",
        utc=True
    )

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df.sort_values("time")

    df = df.drop_duplicates(
        subset="time"
    )

    df = df.tail(
        LIMIT
    ).reset_index(
        drop=True
    )

    print(
        "Downloaded:",
        len(df),
        "candles"
    )

    return df


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(df):

    # EMA

    df["ema_fast"] = df["close"].ewm(
        span=EMA_FAST,
        adjust=False
    ).mean()

    df["ema_slow"] = df["close"].ewm(
        span=EMA_SLOW,
        adjust=False
    ).mean()

    df["ema_trend"] = df["close"].ewm(
        span=EMA_TREND,
        adjust=False
    ).mean()

    # RSI

    delta = df["close"].diff()

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / RSI_PERIOD,
        min_periods=RSI_PERIOD,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / RSI_PERIOD,
        min_periods=RSI_PERIOD,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss

    df["rsi"] = (
        100 -
        (100 / (1 + rs))
    )

    # MACD

    ema12 = df["close"].ewm(
        span=MACD_FAST,
        adjust=False
    ).mean()

    ema26 = df["close"].ewm(
        span=MACD_SLOW,
        adjust=False
    ).mean()

    df["macd"] = (
        ema12 -
        ema26
    )

    df["macd_signal"] = df["macd"].ewm(
        span=MACD_SIGNAL,
        adjust=False
    ).mean()

    df["macd_hist"] = (
        df["macd"] -
        df["macd_signal"]
    )

    # ADX

    high = df["high"]

    low = df["low"]

    close = df["close"]

    previous_high = high.shift(1)

    previous_low = low.shift(1)

    previous_close = close.shift(1)

    tr1 = high - low

    tr2 = (
        high -
        previous_close
    ).abs()

    tr3 = (
        low -
        previous_close
    ).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    up_move = (
        high -
        previous_high
    )

    down_move = (
        previous_low -
        low
    )

    plus_dm = np.where(
        (up_move > down_move)
        &
        (up_move > 0),
        up_move,
        0
    )

    minus_dm = np.where(
        (down_move > up_move)
        &
        (down_move > 0),
        down_move,
        0
    )

    atr = true_range.ewm(
        alpha=1 / ADX_PERIOD,
        min_periods=ADX_PERIOD,
        adjust=False
    ).mean()

    plus_dm = pd.Series(
        plus_dm,
        index=df.index
    )

    minus_dm = pd.Series(
        minus_dm,
        index=df.index
    )

    plus_di = (
        100
        *
        plus_dm.ewm(
            alpha=1 / ADX_PERIOD,
            min_periods=ADX_PERIOD,
            adjust=False
        ).mean()
        /
        atr
    )

    minus_di = (
        100
        *
        minus_dm.ewm(
            alpha=1 / ADX_PERIOD,
            min_periods=ADX_PERIOD,
            adjust=False
        ).mean()
        /
        atr
    )

    dx = (
        100
        *
        (plus_di - minus_di).abs()
        /
        (plus_di + minus_di)
    )

    df["adx"] = dx.ewm(
        alpha=1 / ADX_PERIOD,
        min_periods=ADX_PERIOD,
        adjust=False
    ).mean()

    df["plus_di"] = plus_di

    df["minus_di"] = minus_di

    # Candle

    df["body"] = (
        df["close"] -
        df["open"]
    ).abs()

    df["range"] = (
        df["high"] -
        df["low"]
    )

    df["body_ratio"] = np.where(
        df["range"] > 0,
        df["body"] / df["range"],
        0
    )

    df["bullish_candle"] = (
        (df["close"] > df["open"])
        &
        (df["body_ratio"] >= 0.50)
    )

    df["bearish_candle"] = (
        (df["close"] < df["open"])
        &
        (df["body_ratio"] >= 0.50)
    )

    return df


# ============================================================
# SIGNAL
# ============================================================

def get_signal(
    df,
    index,
    min_score,
    adx_min
):

    row = df.iloc[index]

    previous = df.iloc[index - 1]

    required = [
        "rsi",
        "adx",
        "macd",
        "macd_signal",
        "macd_hist",
        "plus_di",
        "minus_di"
    ]

    for column in required:

        if pd.isna(row[column]):

            return "WAIT"

    if row["adx"] < adx_min:

        return "WAIT"

    buy_score = 0

    sell_score = 0

    # EMA

    if (
        row["ema_fast"]
        >
        row["ema_slow"]
        >
        row["ema_trend"]
    ):

        buy_score += 2

    if (
        row["ema_fast"]
        <
        row["ema_slow"]
        <
        row["ema_trend"]
    ):

        sell_score += 2

    # PRICE

    if row["close"] > row["ema_trend"]:

        buy_score += 1

    if row["close"] < row["ema_trend"]:

        sell_score += 1

    # RSI

    if 52 <= row["rsi"] <= 68:

        buy_score += 1

    if 32 <= row["rsi"] <= 48:

        sell_score += 1

    # MACD

    if (
        row["macd"]
        >
        row["macd_signal"]
        and
        row["macd_hist"]
        >
        previous["macd_hist"]
    ):

        buy_score += 2

    if (
        row["macd"]
        <
        row["macd_signal"]
        and
        row["macd_hist"]
        <
        previous["macd_hist"]
    ):

        sell_score += 2

    # DI

    if row["plus_di"] > row["minus_di"]:

        buy_score += 1

    if row["minus_di"] > row["plus_di"]:

        sell_score += 1

    # CANDLE

    if row["bullish_candle"]:

        buy_score += 1

    if row["bearish_candle"]:

        sell_score += 1

    # SIGNAL

    if (
        buy_score >= min_score
        and
        buy_score > sell_score
    ):

        return "CALL"

    if (
        sell_score >= min_score
        and
        sell_score > buy_score
    ):

        return "PUT"

    return "WAIT"


# ============================================================
# TEST ONE CONFIGURATION
# ============================================================

def test_configuration(
    df,
    min_score,
    adx_min
):

    wins = 0

    losses = 0

    calls = 0

    puts = 0

    balance = 0.0

    peak_balance = 0.0

    max_drawdown = 0.0

    current_loss_streak = 0

    max_loss_streak = 0

    for i in range(
        1,
        len(df) - EXPIRY_CANDLES
    ):

        signal = get_signal(
            df,
            i,
            min_score,
            adx_min
        )

        if signal == "WAIT":

            continue

        entry = df.iloc[i]["close"]

        exit_index = (
            i +
            EXPIRY_CANDLES
        )

        exit_price = df.iloc[
            exit_index
        ]["close"]

        if signal == "CALL":

            calls += 1

            win = (
                exit_price >
                entry
            )

        else:

            puts += 1

            win = (
                exit_price <
                entry
            )

        if win:

            wins += 1

            balance += (
                STAKE *
                PAYOUT
            )

            current_loss_streak = 0

        else:

            losses += 1

            balance -= STAKE

            current_loss_streak += 1

            max_loss_streak = max(
                max_loss_streak,
                current_loss_streak
            )

        peak_balance = max(
            peak_balance,
            balance
        )

        drawdown = (
            peak_balance -
            balance
        )

        max_drawdown = max(
            max_drawdown,
            drawdown
        )

    total_trades = (
        wins +
        losses
    )

    if total_trades == 0:

        return {
            "MIN_SCORE": min_score,
            "ADX_MIN": adx_min,
            "TRADES": 0,
            "WIN_RATE": 0,
            "PROFIT_FACTOR": 0,
            "BALANCE": 0,
            "DRAWDOWN": 0,
            "LOSS_STREAK": 0,
            "CALLS": 0,
            "PUTS": 0
        }

    win_rate = (
        wins /
        total_trades
    ) * 100

    total_profit = (
        wins *
        STAKE *
        PAYOUT
    )

    total_loss = (
        losses *
        STAKE
    )

    if total_loss > 0:

        profit_factor = (
            total_profit /
            total_loss
        )

    else:

        profit_factor = float("inf")

    return {
        "MIN_SCORE": min_score,
        "ADX_MIN": adx_min,
        "TRADES": total_trades,
        "WIN_RATE": round(win_rate, 2),
        "PROFIT_FACTOR": round(
            profit_factor,
            2
        ),
        "BALANCE": round(
            balance,
            2
        ),
        "DRAWDOWN": round(
            max_drawdown,
            2
        ),
        "LOSS_STREAK": max_loss_streak,
        "CALLS": calls,
        "PUTS": puts
    }


# ============================================================
# ANALYZE RSI
# ============================================================

def analyze_rsi(df):

    print()
    print("==================================================")
    print("RSI ANALYSIS")
    print("==================================================")

    ranges = [
        ("RSI < 30", df["rsi"] < 30),
        ("30-40", (df["rsi"] >= 30) & (df["rsi"] < 40)),
        ("40-50", (df["rsi"] >= 40) & (df["rsi"] < 50)),
        ("50-60", (df["rsi"] >= 50) & (df["rsi"] < 60)),
        ("60-70", (df["rsi"] >= 60) & (df["rsi"] < 70)),
        ("RSI >= 70", df["rsi"] >= 70)
    ]

    for name, condition in ranges:

        count = int(
            condition.sum()
        )

        if count > 0:

            print(
                f"{name:<12} :",
                count,
                "candles"
            )

        else:

            print(
                f"{name:<12} :",
                "0 candles"
            )


# ============================================================
# MAIN ANALYSIS
# ============================================================

def main():

    print("==================================================")
    print("SMART TRADING SIGNAL BOT V15")
    print("STRATEGY ANALYZER")
    print("==================================================")

    print()

    df = get_data()

    print()

    print(
        "Calculating indicators..."
    )

    df = calculate_indicators(df)

    # RSI information

    analyze_rsi(df)

    # Configurations

    score_values = [
        5,
        6,
        7,
        8,
        9
    ]

    adx_values = [
        15,
        20,
        25,
        30,
        35
    ]

    results = []

    print()
    print("==================================================")
    print("TESTING CONFIGURATIONS")
    print("==================================================")

    for min_score in score_values:

        for adx_min in adx_values:

            result = test_configuration(
                df,
                min_score,
                adx_min
            )

            results.append(result)

    results_df = pd.DataFrame(
        results
    )

    # Sort by balance

    results_df = results_df.sort_values(
        by=[
            "BALANCE",
            "PROFIT_FACTOR"
        ],
        ascending=False
    )

    print()
    print("==================================================")
    print("BEST CONFIGURATIONS")
    print("==================================================")

    print()

    print(
        results_df.head(10).to_string(
            index=False
        )
    )

    # Best by profit factor

    valid_pf = results_df[
        results_df["TRADES"] > 0
    ]

    if not valid_pf.empty:

        best_pf = valid_pf.sort_values(
            by="PROFIT_FACTOR",
            ascending=False
        ).iloc[0]

        print()
        print("==================================================")
        print("BEST PROFIT FACTOR")
        print("==================================================")

        print(
            best_pf.to_string()
        )

    # Best win rate

    if not valid_pf.empty:

        best_wr = valid_pf.sort_values(
            by="WIN_RATE",
            ascending=False
        ).iloc[0]

        print()
        print("==================================================")
        print("BEST WIN RATE")
        print("==================================================")

        print(
            best_wr.to_string()
        )

    # Best drawdown

    if not valid_pf.empty:

        best_dd = valid_pf.sort_values(
            by="DRAWDOWN",
            ascending=True
        ).iloc[0]

        print()
        print("==================================================")
        print("LOWEST DRAWDOWN")
        print("==================================================")

        print(
            best_dd.to_string()
        )

    print()
    print("==================================================")
    print("BREAK-EVEN INFORMATION")
    print("==================================================")

    break_even = (
        1 /
        (1 + PAYOUT)
    ) * 100

    print(
        "Payout:",
        PAYOUT
    )

    print(
        "Break-even Win Rate:",
        round(
            break_even,
            2
        ),
        "%"
    )

    print()
    print("==================================================")
    print("ANALYSIS COMPLETE")
    print("==================================================")


if __name__ == "__main__":

    main()
