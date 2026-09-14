import requests
import pandas as pd
import numpy as np
from ta.trend import MACD, ADXIndicator, EMAIndicator


# ============================================================
# CONFIG
# ============================================================

SYMBOL = "BTC-USD"
GRANULARITY = 300          # 5 minutes
DAYS = 30

ADX_MIN = 35
EMA_PERIOD = 50

EXPIRIES = [1, 2, 3]
PAYOUT = 0.80
STAKE = 1.0


# ADX strength zones
ADX_ZONES = [
    ("ADX 35-40", 35, 40),
    ("ADX 40-45", 40, 45),
    ("ADX 45+", 45, float("inf")),
]


# ============================================================
# DOWNLOAD DATA
# ============================================================

def download_coinbase(days=30):

    print("=" * 70)
    print(f"Downloading {days} days of data")
    print("=" * 70)

    url = "https://api.exchange.coinbase.com/products/BTC-USD/candles"

    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(days=days)

    all_data = []

    current_start = start

    while current_start < end:

        current_end = min(
            current_start + pd.Timedelta(hours=24),
            end
        )

        params = {
            "granularity": GRANULARITY,
            "start": current_start.isoformat(),
            "end": current_end.isoformat()
        }

        response = requests.get(
            url,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        if data:
            all_data.extend(data)

        current_start = current_end

    if not all_data:
        raise RuntimeError("No data downloaded")

    df = pd.DataFrame(
        all_data,
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

    df = df.sort_values("timestamp")
    df = df.drop_duplicates("timestamp")

    df = df.set_index("timestamp")

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

    df = df.dropna()

    print(f"Downloaded candles: {len(df)}")
    print(f"From: {df.index.min()}")
    print(f"To:   {df.index.max()}")
    print()

    return df


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    macd = MACD(
        close=df["close"],
        window_slow=26,
        window_fast=12,
        window_sign=9
    )

    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    adx = ADXIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    )

    df["adx"] = adx.adx()

    ema = EMAIndicator(
        close=df["close"],
        window=EMA_PERIOD
    )

    df["ema50"] = ema.ema_indicator()

    return df


# ============================================================
# BASE SIGNAL
# ============================================================

def create_base_signal(df):

    bullish_cross = (
        (df["macd"] > df["macd_signal"]) &
        (df["macd"].shift(1) <= df["macd_signal"].shift(1))
    )

    base = (
        bullish_cross &
        (df["adx"] >= ADX_MIN) &
        (df["close"] > df["ema50"])
    )

    return base


# ============================================================
# BACKTEST
# ============================================================

def backtest_call(df, signals, expiry):

    trades = []

    signal_indices = np.where(signals.values)[0]

    for i in signal_indices:

        exit_index = i + expiry

        if exit_index >= len(df):
            continue

        entry_price = df["close"].iloc[i]
        exit_price = df["close"].iloc[exit_index]

        win = exit_price > entry_price

        profit = PAYOUT * STAKE if win else -STAKE

        trades.append({
            "index": i,
            "entry": entry_price,
            "exit": exit_price,
            "win": win,
            "profit": profit
        })

    if not trades:
        return None

    wins = sum(t["win"] for t in trades)
    losses = len(trades) - wins

    win_rate = wins / len(trades) * 100

    gross_profit = wins * PAYOUT * STAKE
    gross_loss = losses * STAKE

    if gross_loss == 0:
        profit_factor = float("inf")
    else:
        profit_factor = gross_profit / gross_loss

    balance = sum(t["profit"] for t in trades)

    equity = 0
    peak = 0
    max_dd = 0

    for trade in trades:

        equity += trade["profit"]

        if equity > peak:
            peak = equity

        drawdown = peak - equity

        if drawdown > max_dd:
            max_dd = drawdown

    max_streak = 0
    current_streak = 0

    for trade in trades:

        if not trade["win"]:
            current_streak += 1
            max_streak = max(
                max_streak,
                current_streak
            )
        else:
            current_streak = 0

    return {
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "wr": win_rate,
        "pf": profit_factor,
        "balance": balance,
        "dd": max_dd,
        "streak": max_streak
    }


# ============================================================
# PRINT RESULT
# ============================================================

def print_result(label, result):

    if result is None:

        print(
            f"{label:<24} No trades"
        )

        return

    pf_text = (
        "inf"
        if result["pf"] == float("inf")
        else f"{result['pf']:.2f}"
    )

    print(
        f"{label:<24}"
        f"Trades: {result['trades']:<4} "
        f"WR: {result['wr']:6.2f}% "
        f"PF: {pf_text:>5} "
        f"Balance: {result['balance']:7.2f} "
        f"DD: {result['dd']:6.2f} "
        f"Streak: {result['streak']}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("MACD + ADX35 + EMA50 + ADX STRENGTH VALIDATION")
    print("=" * 70)

    breakeven = 1 / (1 + PAYOUT) * 100

    print(f"Break-even WR: {breakeven:.2f}%")
    print(f"Symbol: {SYMBOL}")
    print("Timeframe: 5 minutes")
    print(f"ADX minimum: {ADX_MIN}")
    print(f"EMA period: {EMA_PERIOD}")
    print("ADX zones: 35-40 / 40-45 / 45+")
    print(f"Test period: {DAYS} days")
    print(f"Expiries: {EXPIRIES}")
    print()

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    df = download_coinbase(DAYS)

    # --------------------------------------------------------
    # INDICATORS
    # --------------------------------------------------------

    df = calculate_indicators(df)

    # --------------------------------------------------------
    # BASE SIGNAL
    # --------------------------------------------------------

    base_signal = create_base_signal(df)

    print("=" * 70)
    print("BASE SIGNAL")
    print("=" * 70)

    print(
        f"MACD + ADX35 + EMA50 CALL: "
        f"{base_signal.sum()}"
    )

    print()

    # --------------------------------------------------------
    # ADX ZONES
    # --------------------------------------------------------

    for zone_name, lower, upper in ADX_ZONES:

        print("=" * 70)
        print(zone_name)
        print("=" * 70)

        zone_signal = (
            base_signal &
            (df["adx"] >= lower) &
            (df["adx"] < upper)
        )

        signal_count = int(zone_signal.sum())

        print(f"Signals: {signal_count}")

        for expiry in EXPIRIES:

            result = backtest_call(
                df,
                zone_signal,
                expiry
            )

            print_result(
                f"Expiry {expiry}",
                result
            )

        print()

        # ----------------------------------------------------
        # EXPIRY 2 - FOUR PARTS
        # ----------------------------------------------------

        print(
            f"Expiry 2 - 4 Parts ({zone_name})"
        )

        indices = np.where(
            zone_signal.values
        )[0]

        if len(indices) > 0:

            parts = np.array_split(
                indices,
                4
            )

            for part_number, part_indices in enumerate(
                parts,
                start=1
            ):

                part_signal = pd.Series(
                    False,
                    index=df.index
                )

                for idx in part_indices:
                    part_signal.iloc[idx] = True

                result = backtest_call(
                    df,
                    part_signal,
                    2
                )

                print_result(
                    f"Part {part_number}",
                    result
                )

        else:

            print("No trades")

        print()

    # --------------------------------------------------------
    # DIRECT COMPARISON
    # --------------------------------------------------------

    print("=" * 70)
    print("DIRECT COMPARISON - EXPIRY 2")
    print("=" * 70)

    baseline_result = backtest_call(
        df,
        base_signal,
        2
    )

    print_result(
        "BASELINE",
        baseline_result
    )

    print()

    for zone_name, lower, upper in ADX_ZONES:

        zone_signal = (
            base_signal &
            (df["adx"] >= lower) &
            (df["adx"] < upper)
        )

        result = backtest_call(
            df,
            zone_signal,
            2
        )

        print_result(
            zone_name,
            result
        )

    print()

    print("=" * 70)
    print("VALIDATION COMPLETE")
    print("=" * 70)

    print()
    print(
        "Break-even assumes 80% payout."
    )
    print(
        "Historical backtest only."
    )
    print(
        "No guarantee of future profitability."
    )
    print(
        "Coinbase prices may differ from Pocket Option."
    )


if __name__ == "__main__":
    main()
