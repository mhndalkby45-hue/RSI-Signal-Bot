import requests
import pandas as pd
import ta
import time
from datetime import datetime, timedelta, timezone
import math


# ============================================================
# MACD CALL FILTER ANALYSIS V15
# ============================================================

BOT_NAME = "MACD CALL Filter Analysis V15"

SYMBOL = "BTC-USD"
DISPLAY_SYMBOL = "BTCUSDT"

INTERVAL = "5m"
GRANULARITY = 300

DAYS_TO_TEST = 7

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

RSI_PERIOD = 14
ADX_PERIOD = 14

EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 50

STAKE = 1.0
PAYOUT = 0.80

EXPIRY = 2


# ============================================================
# DOWNLOAD DATA
# ============================================================

def download_data(days):

    print("Downloading historical data...")
    print("Period:", days, "days")
    print("Symbol:", SYMBOL)
    print("Timeframe:", INTERVAL)
    print()

    end_time = datetime.now(timezone.utc)

    start_time = (
        end_time
        - timedelta(days=days)
    )

    all_rows = []

    current_end = end_time

    candles_per_request = 290

    chunk_seconds = (
        candles_per_request
        * GRANULARITY
    )

    request_number = 0

    while current_end > start_time:

        current_start = (
            current_end
            - timedelta(seconds=chunk_seconds)
        )

        if current_start < start_time:
            current_start = start_time

        url = (
            "https://api.exchange.coinbase.com/products/"
            + SYMBOL
            + "/candles"
        )

        params = {
            "granularity": GRANULARITY,
            "start": current_start.isoformat(),
            "end": current_end.isoformat()
        }

        try:

            response = requests.get(
                url,
                params=params,
                timeout=20
            )

            response.raise_for_status()

            data = response.json()

            if isinstance(data, list):

                all_rows.extend(data)

            request_number += 1

            print(
                "Request",
                request_number,
                "| candles:",
                len(data)
            )

        except Exception as e:

            print(
                "Download error:",
                e
            )

        current_end = current_start

        time.sleep(0.25)

    if len(all_rows) == 0:

        raise RuntimeError(
            "No data received."
        )

    df = pd.DataFrame(
        all_rows,
        columns=[
            "timestamp",
            "low",
            "high",
            "open",
            "close",
            "volume"
        ]
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        unit="s",
        utc=True
    )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df.dropna()

    df = df.drop_duplicates(
        subset=["timestamp"]
    )

    df = df.sort_values(
        "timestamp"
    )

    df = df.reset_index(
        drop=True
    )

    df = df[
        (df["timestamp"] >= start_time)
        &
        (df["timestamp"] <= end_time)
    ]

    df = df.reset_index(
        drop=True
    )

    print()
    print(
        "Total candles:",
        len(df)
    )

    print(
        "From:",
        df["timestamp"].iloc[0]
    )

    print(
        "To:",
        df["timestamp"].iloc[-1]
    )

    return df


# ============================================================
# CALCULATE INDICATORS
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    # EMA
    df["ema9"] = (
        ta.trend.EMAIndicator(
            close=df["close"],
            window=EMA_FAST
        ).ema_indicator()
    )

    df["ema21"] = (
        ta.trend.EMAIndicator(
            close=df["close"],
            window=EMA_SLOW
        ).ema_indicator()
    )

    df["ema50"] = (
        ta.trend.EMAIndicator(
            close=df["close"],
            window=EMA_TREND
        ).ema_indicator()
    )

    # RSI
    df["rsi"] = (
        ta.momentum.RSIIndicator(
            close=df["close"],
            window=RSI_PERIOD
        ).rsi()
    )

    # MACD
    macd = ta.trend.MACD(
        close=df["close"],
        window_fast=MACD_FAST,
        window_slow=MACD_SLOW,
        window_sign=MACD_SIGNAL
    )

    df["macd"] = macd.macd()

    df["macd_signal"] = (
        macd.macd_signal()
    )

    df["macd_hist"] = (
        macd.macd_diff()
    )

    df["macd_prev"] = (
        df["macd"].shift(1)
    )

    df["macd_signal_prev"] = (
        df["macd_signal"].shift(1)
    )

    df["hist_prev"] = (
        df["macd_hist"].shift(1)
    )

    # ADX
    adx_indicator = (
        ta.trend.ADXIndicator(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=ADX_PERIOD
        )
    )

    df["adx"] = (
        adx_indicator.adx()
    )

    df["plus_di"] = (
        adx_indicator.adx_pos()
    )

    df["minus_di"] = (
        adx_indicator.adx_neg()
    )

    # Candle
    df["body"] = (
        df["close"]
        - df["open"]
    ).abs()

    df["range"] = (
        df["high"]
        - df["low"]
    )

    df["body_ratio"] = (
        df["body"]
        / df["range"]
        .replace(0, pd.NA)
    )

    # MACD bullish cross
    df["macd_cross"] = (
        (df["macd_prev"] <= df["macd_signal_prev"])
        &
        (df["macd"] > df["macd_signal"])
    )

    # MACD histogram increasing
    df["hist_increasing"] = (
        df["macd_hist"]
        > df["hist_prev"]
    )

    # EMA trend
    df["ema_bull"] = (
        (df["ema9"] > df["ema21"])
        &
        (df["ema21"] > df["ema50"])
    )

    # Price above EMA50
    df["above_ema50"] = (
        df["close"]
        > df["ema50"]
    )

    # RSI zones
    df["rsi_50_70"] = (
        (df["rsi"] >= 50)
        &
        (df["rsi"] <= 70)
    )

    df["rsi_55_65"] = (
        (df["rsi"] >= 55)
        &
        (df["rsi"] <= 65)
    )

    # ADX filters
    df["adx20"] = (
        df["adx"] >= 20
    )

    df["adx25"] = (
        df["adx"] >= 25
    )

    df["adx30"] = (
        df["adx"] >= 30
    )

    # DI direction
    df["di_bull"] = (
        df["plus_di"]
        > df["minus_di"]
    )

    # Bullish candle
    df["bull_candle"] = (
        df["close"]
        > df["open"]
    )

    # Strong bullish candle
    df["strong_candle"] = (
        (df["close"] > df["open"])
        &
        (df["body_ratio"] >= 0.50)
    )

    # MACD histogram positive
    df["hist_positive"] = (
        df["macd_hist"] > 0
    )

    df = df.dropna()

    df = df.reset_index(
        drop=True
    )

    return df


# ============================================================
# BACKTEST
# ============================================================

def backtest(
    df,
    filter_column=None
):

    wins = 0
    losses = 0

    balance = 0.0

    peak = 0.0

    max_drawdown = 0.0

    loss_streak = 0
    max_loss_streak = 0

    trades = []

    for i in range(
        1,
        len(df) - EXPIRY
    ):

        row = df.iloc[i]

        # Base signal
        if not row["macd_cross"]:
            continue

        # Optional filter
        if filter_column is not None:

            if not row[filter_column]:
                continue

        entry_price = float(
            row["close"]
        )

        exit_row = df.iloc[
            i + EXPIRY
        ]

        exit_price = float(
            exit_row["close"]
        )

        movement = (
            (exit_price - entry_price)
            / entry_price
        ) * 100

        if exit_price > entry_price:

            result = "WIN"

            wins += 1

            losses_streak_before = (
                loss_streak
            )

            loss_streak = 0

            balance += (
                STAKE * PAYOUT
            )

        else:

            result = "LOSS"

            losses += 1

            loss_streak += 1

            if loss_streak > max_loss_streak:

                max_loss_streak = (
                    loss_streak
                )

            losses_streak_before = (
                loss_streak
            )

            balance -= STAKE

        if balance > peak:

            peak = balance

        drawdown = (
            peak - balance
        )

        if drawdown > max_drawdown:

            max_drawdown = drawdown

        trades.append(
            {
                "time": row["timestamp"],
                "entry": entry_price,
                "exit": exit_price,
                "movement": movement,
                "result": result,
                "rsi": row["rsi"],
                "adx": row["adx"],
                "macd_hist": row["macd_hist"]
            }
        )

    total = (
        wins + losses
    )

    if total > 0:

        win_rate = (
            wins / total
        ) * 100

    else:

        win_rate = 0.0

    if losses > 0:

        profit_factor = (
            wins * PAYOUT
        ) / losses

    else:

        profit_factor = float("inf")

    if total > 0:

        avg_move = sum(
            t["movement"]
            for t in trades
        ) / total

    else:

        avg_move = 0.0

    return {
        "trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "balance": balance,
        "drawdown": max_drawdown,
        "max_loss_streak": max_loss_streak,
        "avg_move": avg_move,
        "trade_list": trades
    }


# ============================================================
# PRINT RESULT
# ============================================================

def print_result(
    name,
    result
):

    if result["profit_factor"] == float("inf"):

        pf = "INF"

    else:

        pf = "{:.2f}".format(
            result["profit_factor"]
        )

    print(
        "{:<32}".format(name),
        "| Trades:",
        "{:>3}".format(
            result["trades"]
        ),
        "| WR:",
        "{:>6}".format(
            "{:.2f}%".format(
                result["win_rate"]
            )
        ),
        "| PF:",
        "{:>5}".format(
            pf
        ),
        "| Balance:",
        "{:+.2f}".format(
            result["balance"]
        ),
        "| DD:",
        "{:.2f}".format(
            result["drawdown"]
        )
    )


# ============================================================
# ANALYZE TIME PARTS
# ============================================================

def analyze_parts(
    df,
    filter_column
):

    total = len(df)

    part_size = (
        total // 4
    )

    results = []

    for part in range(1, 5):

        start = (
            (part - 1)
            * part_size
        )

        if part == 4:

            end = total

        else:

            end = (
                part
                * part_size
            )

        part_df = df.iloc[
            start:end
        ].copy()

        result = backtest(
            part_df,
            filter_column
        )

        results.append(
            result
        )

    return results


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(BOT_NAME)
    print("=" * 70)
    print()

    df = download_data(
        DAYS_TO_TEST
    )

    df = calculate_indicators(
        df
    )

    print()
    print(
        "Candles after indicators:",
        len(df)
    )

    print()
    print("=" * 70)
    print("BASE STRATEGY")
    print("=" * 70)

    base = backtest(
        df,
        None
    )

    print_result(
        "MACD CROSS -> CALL",
        base
    )

    # ========================================================
    # FILTERS
    # ========================================================

    filters = [
        ("No Filter", None),

        ("EMA Bullish",
         "ema_bull"),

        ("Above EMA50",
         "above_ema50"),

        ("EMA Bullish + EMA50",
         "ema_bull"),

        ("RSI 50-70",
         "rsi_50_70"),

        ("RSI 55-65",
         "rsi_55_65"),

        ("ADX >= 20",
         "adx20"),

        ("ADX >= 25",
         "adx25"),

        ("ADX >= 30",
         "adx30"),

        ("DI Bullish",
         "di_bull"),

        ("Bull Candle",
         "bull_candle"),

        ("Strong Bull Candle",
         "strong_candle"),

        ("Histogram Increasing",
         "hist_increasing"),

        ("Histogram Positive",
         "hist_positive")
    ]

    print()
    print("=" * 70)
    print("FILTER COMPARISON")
    print("=" * 70)

    print(
        "Break-even:",
        "{:.2f}%".format(
            100 / (1 + PAYOUT)
        )
    )

    print()

    all_results = []

    for name, column in filters:

        result = backtest(
            df,
            column
        )

        all_results.append(
            (
                name,
                column,
                result
            )
        )

        print_result(
            name,
            result
        )

    # ========================================================
    # RANK FILTERS
    # ========================================================

    valid_results = [
        x for x in all_results
        if x[2]["trades"] >= 20
    ]

    valid_results.sort(
        key=lambda x: (
            x[2]["profit_factor"],
            x[2]["win_rate"]
        ),
        reverse=True
    )

    print()
    print("=" * 70)
    print("BEST FILTERS - MINIMUM 20 TRADES")
    print("=" * 70)

    for number, item in enumerate(
        valid_results[:10],
        start=1
    ):

        name = item[0]
        result = item[2]

        print(
            number,
            ".",
            name,
            "| Trades:",
            result["trades"],
            "| WR:",
            "{:.2f}%".format(
                result["win_rate"]
            ),
            "| PF:",
            "{:.2f}".format(
                result["profit_factor"]
            )
            if result["profit_factor"]
            != float("inf")
            else "INF",
            "| Balance:",
            "{:+.2f}".format(
                result["balance"]
            )
        )

    # ========================================================
    # PART ANALYSIS
    # ========================================================

    print()
    print("=" * 70)
    print("TIME-PART ANALYSIS")
    print("=" * 70)

    # Top filters
    top_filters = valid_results[:5]

    for item in top_filters:

        name = item[0]
        column = item[1]

        print()
        print(
            "FILTER:",
            name
        )

        parts = analyze_parts(
            df,
            column
        )

        for index, result in enumerate(
            parts,
            start=1
        ):

            print_result(
                "Part " + str(index),
                result
            )

    # ========================================================
    # IMPORTANT COMBINATIONS
    # ========================================================

    combinations = []

    # MACD + EMA50 + RSI
    combination_1 = (
        df["macd_cross"]
        &
        df["above_ema50"]
        &
        df["rsi_50_70"]
    )

    df["filter_combo_1"] = (
        combination_1
    )

    combinations.append(
        (
            "MACD + EMA50 + RSI50-70",
            "filter_combo_1"
        )
    )

    # MACD + EMA50 + ADX
    combination_2 = (
        df["macd_cross"]
        &
        df["above_ema50"]
        &
        df["adx25"]
    )

    df["filter_combo_2"] = (
        combination_2
    )

    combinations.append(
        (
            "MACD + EMA50 + ADX25",
            "filter_combo_2"
        )
    )

    # MACD + EMA50 + Histogram
    combination_3 = (
        df["macd_cross"]
        &
        df["above_ema50"]
        &
        df["hist_increasing"]
    )

    df["filter_combo_3"] = (
        combination_3
    )

    combinations.append(
        (
            "MACD + EMA50 + Histogram",
            "filter_combo_3"
        )
    )

    # MACD + RSI + Histogram
    combination_4 = (
        df["macd_cross"]
        &
        df["rsi_50_70"]
        &
        df["hist_increasing"]
    )

    df["filter_combo_4"] = (
        combination_4
    )

    combinations.append(
        (
            "MACD + RSI + Histogram",
            "filter_combo_4"
        )
    )

    # MACD + EMA50 + RSI + Histogram
    combination_5 = (
        df["macd_cross"]
        &
        df["above_ema50"]
        &
        df["rsi_50_70"]
        &
        df["hist_increasing"]
    )

    df["filter_combo_5"] = (
        combination_5
    )

    combinations.append(
        (
            "MACD + EMA50 + RSI + Histogram",
            "filter_combo_5"
        )
    )

    print()
    print("=" * 70)
    print("FILTER COMBINATIONS")
    print("=" * 70)

    for name, column in combinations:

        result = backtest(
            df,
            column
        )

        print_result(
            name,
            result
        )

    # ========================================================
    # FINAL
    # ========================================================

    print()
    print("=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)

    print()
    print(
        "Do not select a filter based on one period only."
    )

    print(
        "A useful filter should remain reasonably stable "
        "across multiple periods."
    )

    print()
    print(
        "Historical testing only - no guarantee of future results."
    )


if __name__ == "__main__":

    main()
