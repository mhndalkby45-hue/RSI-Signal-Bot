import requests
import pandas as pd
import ta
import time
from datetime import datetime, timedelta, timezone
import math


# ============================================================
# MACD CALL EXTENDED VALIDATION
# ============================================================

BOT_NAME = "MACD CALL Extended Validation V15"

SYMBOL = "BTC-USD"
DISPLAY_SYMBOL = "BTCUSDT"

INTERVAL = "5m"
GRANULARITY = 300

DAYS_TO_TEST = 7

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

STAKE = 1.0
PAYOUT = 0.80

EXPIRIES = [1, 2, 3]

PARTS = 4


# ============================================================
# DOWNLOAD HISTORICAL DATA
# ============================================================

def download_data(days):
    print("Downloading historical data...")
    print("Period:", days, "days")
    print("Symbol:", SYMBOL)
    print("Timeframe:", INTERVAL)
    print()

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    all_rows = []

    current_end = end_time

    # Coinbase normally limits candles per request.
    # 290 candles gives us a small safety margin.
    candles_per_request = 290

    chunk_seconds = candles_per_request * GRANULARITY

    request_count = 0

    while current_end > start_time:

        current_start = current_end - timedelta(seconds=chunk_seconds)

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

            request_count += 1

            print(
                "Request",
                request_count,
                "| candles:",
                len(data)
            )

        except Exception as e:
            print("Download error:", e)

        current_end = current_start

        time.sleep(0.25)

    if len(all_rows) == 0:
        raise RuntimeError("No data received from Coinbase.")

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

    # Remove candles outside requested period
    df = df[
        (df["timestamp"] >= start_time)
        & (df["timestamp"] <= end_time)
    ]

    df = df.reset_index(
        drop=True
    )

    print()
    print("Total candles received:", len(df))

    if len(df) > 0:
        print("From:", df["timestamp"].iloc[0])
        print("To:", df["timestamp"].iloc[-1])

    return df


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    macd = ta.trend.MACD(
        close=df["close"],
        window_fast=MACD_FAST,
        window_slow=MACD_SLOW,
        window_sign=MACD_SIGNAL
    )

    df["macd"] = macd.macd()

    df["macd_signal"] = macd.macd_signal()

    df["macd_hist"] = macd.macd_diff()

    df["macd_prev"] = df["macd"].shift(1)

    df["macd_signal_prev"] = df[
        "macd_signal"
    ].shift(1)

    # MACD bullish crossover
    df["macd_bull_cross"] = (
        (df["macd_prev"] <= df["macd_signal_prev"])
        &
        (df["macd"] > df["macd_signal"])
    )

    # MACD bearish crossover
    df["macd_bear_cross"] = (
        (df["macd_prev"] >= df["macd_signal_prev"])
        &
        (df["macd"] < df["macd_signal"])
    )

    df = df.dropna()

    df = df.reset_index(
        drop=True
    )

    return df


# ============================================================
# WILSON CONFIDENCE INTERVAL
# ============================================================

def wilson_interval(wins, trades):

    if trades == 0:
        return 0.0, 0.0

    z = 1.96

    p = wins / trades

    denominator = 1 + (z * z / trades)

    centre = (
        p
        + (z * z / (2 * trades))
    ) / denominator

    margin = (
        z
        * math.sqrt(
            (
                p * (1 - p) / trades
            )
            + (
                z * z / (4 * trades * trades)
            )
        )
        / denominator
    )

    lower = max(
        0.0,
        centre - margin
    )

    upper = min(
        1.0,
        centre + margin
    )

    return lower * 100, upper * 100


# ============================================================
# BACKTEST
# ============================================================

def backtest(df, expiry):

    trades = []

    balance = 0.0

    wins = 0
    losses = 0

    current_loss_streak = 0
    max_loss_streak = 0

    max_drawdown = 0.0

    peak_balance = 0.0

    for i in range(1, len(df) - expiry):

        row = df.iloc[i]

        # ----------------------------------------------------
        # CALL ONLY
        # ----------------------------------------------------

        if not row["macd_bull_cross"]:
            continue

        entry_price = float(
            row["close"]
        )

        exit_row = df.iloc[
            i + expiry
        ]

        exit_price = float(
            exit_row["close"]
        )

        if exit_price > entry_price:

            result = "WIN"

            wins += 1

            balance += STAKE * PAYOUT

            current_loss_streak = 0

        else:

            result = "LOSS"

            losses += 1

            balance -= STAKE

            current_loss_streak += 1

            if current_loss_streak > max_loss_streak:
                max_loss_streak = current_loss_streak

        if balance > peak_balance:
            peak_balance = balance

        drawdown = peak_balance - balance

        if drawdown > max_drawdown:
            max_drawdown = drawdown

        movement = (
            (exit_price - entry_price)
            / entry_price
        ) * 100

        trades.append(
            {
                "entry_time": row["timestamp"],
                "exit_time": exit_row["timestamp"],
                "entry": entry_price,
                "exit": exit_price,
                "movement": movement,
                "result": result
            }
        )

    total_trades = wins + losses

    if total_trades > 0:

        win_rate = (
            wins / total_trades
        ) * 100

    else:

        win_rate = 0.0

    if losses > 0:

        profit_factor = (
            wins * PAYOUT
        ) / losses

    else:

        profit_factor = float("inf")

    if total_trades > 0:

        avg_move = sum(
            t["movement"]
            for t in trades
        ) / total_trades

    else:

        avg_move = 0.0

    ci_low, ci_high = wilson_interval(
        wins,
        total_trades
    )

    return {
        "trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "balance": balance,
        "drawdown": max_drawdown,
        "max_loss_streak": max_loss_streak,
        "avg_move": avg_move,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "trade_list": trades
    }


# ============================================================
# PRINT RESULT
# ============================================================

def print_result(name, result):

    pf = result["profit_factor"]

    if pf == float("inf"):
        pf_text = "INF"
    else:
        pf_text = "{:.2f}".format(pf)

    print()
    print("=" * 65)
    print(name)
    print("=" * 65)

    print(
        "Trades:",
        result["trades"]
    )

    print(
        "Wins:",
        result["wins"]
    )

    print(
        "Losses:",
        result["losses"]
    )

    print(
        "Win Rate:",
        "{:.2f}%".format(
            result["win_rate"]
        )
    )

    print(
        "95% WR Range:",
        "{:.2f}% - {:.2f}%".format(
            result["ci_low"],
            result["ci_high"]
        )
    )

    print(
        "Profit Factor:",
        pf_text
    )

    print(
        "Balance:",
        "{:+.2f}".format(
            result["balance"]
        )
    )

    print(
        "Max Drawdown:",
        "{:.2f}".format(
            result["drawdown"]
        )
    )

    print(
        "Max Loss Streak:",
        result["max_loss_streak"]
    )

    print(
        "Average Price Move:",
        "{:+.4f}%".format(
            result["avg_move"]
        )
    )


# ============================================================
# PRINT TRADES
# ============================================================

def print_trades(result, limit=20):

    trades = result["trade_list"]

    print()
    print("Trade details")
    print("-" * 65)

    if len(trades) == 0:

        print("No CALL trades found.")

        return

    shown = trades[-limit:]

    for number, trade in enumerate(
        shown,
        start=1
    ):

        print(
            number,
            "|",
            trade["entry_time"],
            "|",
            "Entry:",
            "{:.2f}".format(
                trade["entry"]
            ),
            "|",
            "Exit:",
            "{:.2f}".format(
                trade["exit"]
            ),
            "|",
            "{:+.4f}%".format(
                trade["movement"]
            ),
            "|",
            trade["result"]
        )


# ============================================================
# SPLIT DATA INTO 4 CHRONOLOGICAL PARTS
# ============================================================

def analyze_parts(df, expiry):

    print()
    print("#" * 70)
    print(
        "EXPIRY",
        expiry,
        "CANDLE(S)"
    )
    print("#" * 70)

    total_length = len(df)

    part_size = total_length // PARTS

    for part_number in range(1, PARTS + 1):

        start_index = (
            (part_number - 1)
            * part_size
        )

        if part_number == PARTS:

            end_index = total_length

        else:

            end_index = (
                part_number
                * part_size
            )

        part_df = df.iloc[
            start_index:end_index
        ].copy()

        result = backtest(
            part_df,
            expiry
        )

        print_result(
            "PART " + str(part_number),
            result
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(BOT_NAME)
    print("=" * 70)
    print(
        "Symbol:",
        DISPLAY_SYMBOL
    )
    print(
        "Timeframe:",
        INTERVAL
    )
    print(
        "Historical period:",
        DAYS_TO_TEST,
        "days"
    )
    print(
        "Strategy:",
        "MACD Bullish Cross -> CALL"
    )
    print(
        "Payout:",
        PAYOUT
    )
    print()

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    df = download_data(
        DAYS_TO_TEST
    )

    if len(df) < 100:

        raise RuntimeError(
            "Not enough candles for validation."
        )

    # --------------------------------------------------------
    # INDICATORS
    # --------------------------------------------------------

    df = calculate_indicators(
        df
    )

    print()
    print(
        "Candles after indicators:",
        len(df)
    )

    # --------------------------------------------------------
    # BREAK EVEN
    # --------------------------------------------------------

    break_even = (
        1
        / (1 + PAYOUT)
    ) * 100

    print(
        "Break-even Win Rate:",
        "{:.2f}%".format(
            break_even
        )
    )

    # --------------------------------------------------------
    # TEST EACH EXPIRY
    # --------------------------------------------------------

    full_results = {}

    for expiry in EXPIRIES:

        result = backtest(
            df,
            expiry
        )

        full_results[
            expiry
        ] = result

        print_result(
            "FULL DATA - EXPIRY "
            + str(expiry),
            result
        )

        analyze_parts(
            df,
            expiry
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print()
    print("=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)

    print(
        "Strategy: MACD Bullish Cross -> CALL"
    )

    print()

    for expiry in EXPIRIES:

        result = full_results[
            expiry
        ]

        print(
            "Expiry",
            expiry,
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
            ),
            "| DD:",
            "{:.2f}".format(
                result["drawdown"]
            )
        )

    # --------------------------------------------------------
    # BEST EXPIRY
    # --------------------------------------------------------

    best_expiry = max(
        EXPIRIES,
        key=lambda x: full_results[x]["balance"]
    )

    best_result = full_results[
        best_expiry
    ]

    print()
    print("=" * 70)
    print("BEST EXPIRY")
    print("=" * 70)

    print(
        "Expiry:",
        best_expiry,
        "candles"
    )

    print(
        "Trades:",
        best_result["trades"]
    )

    print(
        "Win Rate:",
        "{:.2f}%".format(
            best_result["win_rate"]
        )
    )

    print(
        "95% WR Range:",
        "{:.2f}% - {:.2f}%".format(
            best_result["ci_low"],
            best_result["ci_high"]
        )
    )

    print(
        "Profit Factor:",
        "{:.2f}".format(
            best_result["profit_factor"]
        )
        if best_result["profit_factor"]
        != float("inf")
        else "INF"
    )

    print(
        "Balance:",
        "{:+.2f}".format(
            best_result["balance"]
        )
    )

    print(
        "Max Drawdown:",
        "{:.2f}".format(
            best_result["drawdown"]
        )
    )

    print(
        "Max Loss Streak:",
        best_result["max_loss_streak"]
    )

    print()

    if best_result["trades"] < 30:

        print(
            "WARNING: Sample size is still small."
        )

    elif best_result["win_rate"] > break_even:

        print(
            "RESULT: Strategy is above break-even "
            "in this historical sample."
        )

    else:

        print(
            "RESULT: Strategy is below break-even "
            "in this historical sample."
        )

    print()
    print(
        "Important: Historical results do not guarantee "
        "future trading performance."
    )

    # --------------------------------------------------------
    # SHOW LAST TRADES
    # --------------------------------------------------------

    print()
    print_trades(
        best_result,
        limit=20
    )


if __name__ == "__main__":
    main()
