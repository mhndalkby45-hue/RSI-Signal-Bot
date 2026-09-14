import requests
import pandas as pd
import ta

from datetime import datetime, timedelta


BOT_NAME = "MACD + ADX35 + EMA50 + RSI Validation"

SYMBOL = "BTC-USD"
GRANULARITY = 300

STAKE = 1.0
PAYOUT = 0.80

EXPIRIES = [1, 2, 3]

ADX_MIN = 35
EMA_PERIOD = 50

RSI_THRESHOLDS = [50, 55, 60]

TEST_DAYS = 30


# ============================================================
# DOWNLOAD DATA
# ============================================================

def download_data(days):

    print("=" * 70)
    print(f"Downloading {days} days of data")
    print("=" * 70)

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=days)

    url = f"https://api.exchange.coinbase.com/products/{SYMBOL}/candles"

    all_data = []
    current_start = start_time

    while current_start < end_time:

        current_end = min(
            current_start + timedelta(seconds=300 * 300),
            end_time
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

        if response.status_code != 200:

            print(
                "Download error:",
                response.status_code
            )

            current_start = current_end
            continue

        data = response.json()

        if isinstance(data, list):
            all_data.extend(data)

        current_start = current_end

    if not all_data:
        raise RuntimeError(
            "No data downloaded."
        )

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

    numeric_columns = [
        "low",
        "high",
        "open",
        "close",
        "volume"
    ]

    for col in numeric_columns:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.drop_duplicates(
        subset=["timestamp"]
    )

    df = df.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    df = df.dropna()

    print(
        f"Downloaded candles: {len(df)}"
    )

    print(
        f"From: {df['timestamp'].iloc[0]}"
    )

    print(
        f"To:   {df['timestamp'].iloc[-1]}"
    )

    return df


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    macd = ta.trend.MACD(
        close=df["close"],
        window_slow=26,
        window_fast=12,
        window_sign=9
    )

    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    # --------------------------------------------------------
    # ADX
    # --------------------------------------------------------

    adx_indicator = ta.trend.ADXIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    )

    df["adx"] = adx_indicator.adx()

    # --------------------------------------------------------
    # EMA50
    # --------------------------------------------------------

    df["ema50"] = (
        df["close"]
        .ewm(
            span=EMA_PERIOD,
            adjust=False
        )
        .mean()
    )

    # --------------------------------------------------------
    # RSI14
    # --------------------------------------------------------

    rsi_indicator = ta.momentum.RSIIndicator(
        close=df["close"],
        window=14
    )

    df["rsi"] = rsi_indicator.rsi()

    df = df.dropna().reset_index(
        drop=True
    )

    return df


# ============================================================
# BASE CALL
# ============================================================

def generate_base_signal(df):

    df = df.copy()

    macd_cross_up = (
        (df["macd"] > df["macd_signal"]) &
        (
            df["macd"].shift(1)
            <=
            df["macd_signal"].shift(1)
        )
    )

    df["BASE_CALL"] = (
        macd_cross_up &
        (df["adx"] >= ADX_MIN) &
        (df["close"] > df["ema50"])
    )

    return df


# ============================================================
# RSI SIGNAL
# ============================================================

def add_rsi_signal(
    df,
    rsi_threshold
):

    df = df.copy()

    column_name = (
        f"RSI_{rsi_threshold}"
    )

    df[column_name] = (
        df["BASE_CALL"] &
        (df["rsi"] > rsi_threshold)
    )

    return df, column_name


# ============================================================
# BACKTEST
# ============================================================

def backtest(
    df,
    signal_column,
    expiry
):

    wins = 0
    losses = 0

    balance = 0.0

    peak = 0.0
    max_drawdown = 0.0

    max_streak = 0
    current_streak = 0

    for i in range(
        len(df) - expiry
    ):

        if not df[signal_column].iloc[i]:
            continue

        entry_price = df["close"].iloc[i]

        exit_price = df[
            "close"
        ].iloc[i + expiry]

        # CALL only
        if exit_price > entry_price:

            wins += 1

            profit = (
                STAKE * PAYOUT
            )

            current_streak = 0

        else:

            losses += 1

            profit = -STAKE

            current_streak += 1

            if current_streak > max_streak:
                max_streak = current_streak

        balance += profit

        if balance > peak:
            peak = balance

        drawdown = peak - balance

        if drawdown > max_drawdown:
            max_drawdown = drawdown

    trades = wins + losses

    if trades == 0:

        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "wr": 0,
            "pf": 0,
            "balance": 0,
            "drawdown": 0,
            "streak": 0
        }

    win_rate = (
        wins / trades
    ) * 100

    gross_profit = (
        wins * STAKE * PAYOUT
    )

    gross_loss = (
        losses * STAKE
    )

    if gross_loss > 0:

        profit_factor = (
            gross_profit /
            gross_loss
        )

    else:

        profit_factor = float("inf")

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "wr": win_rate,
        "pf": profit_factor,
        "balance": balance,
        "drawdown": max_drawdown,
        "streak": max_streak
    }


# ============================================================
# PARTS ANALYSIS
# ============================================================

def backtest_parts(
    df,
    signal_column,
    expiry,
    parts=4
):

    total_length = len(df)
    part_size = total_length // parts

    results = []

    for p in range(parts):

        start = p * part_size

        if p == parts - 1:
            end = total_length
        else:
            end = (p + 1) * part_size

        part_df = df.iloc[
            start:end
        ].copy()

        result = backtest(
            part_df,
            signal_column,
            expiry
        )

        results.append(result)

    return results


# ============================================================
# PRINT RESULT
# ============================================================

def print_result(
    name,
    result
):

    pf = result["pf"]

    if pf == float("inf"):
        pf_text = "inf"
    else:
        pf_text = f"{pf:.2f}"

    print(
        f"{name:<25}"
        f"Trades: {result['trades']:<4} "
        f"WR: {result['wr']:>6.2f}% "
        f"PF: {pf_text:>5} "
        f"Balance: {result['balance']:>7.2f} "
        f"DD: {result['drawdown']:>6.2f} "
        f"Streak: {result['streak']}"
    )


# ============================================================
# MAIN
# ============================================================

print()

print("=" * 70)
print(BOT_NAME)
print("=" * 70)

break_even = 100 / (
    1 + PAYOUT
)

print(
    f"Break-even WR: {break_even:.2f}%"
)

print(
    f"Symbol: {SYMBOL}"
)

print(
    f"Timeframe: {GRANULARITY // 60} minutes"
)

print(
    f"ADX minimum: {ADX_MIN}"
)

print(
    f"EMA period: {EMA_PERIOD}"
)

print(
    f"RSI thresholds: {RSI_THRESHOLDS}"
)

print(
    f"Test period: {TEST_DAYS} days"
)

print(
    f"Expiries: {EXPIRIES}"
)

print()


# ============================================================
# DATA
# ============================================================

df = download_data(
    TEST_DAYS
)

df = calculate_indicators(
    df
)

df = generate_base_signal(
    df
)


# ============================================================
# BASE SIGNAL COUNT
# ============================================================

base_count = int(
    df["BASE_CALL"].sum()
)

print()
print("=" * 70)
print("BASE SIGNAL")
print("=" * 70)

print(
    f"MACD + ADX35 + EMA50 CALL: {base_count}"
)


# ============================================================
# TEST RSI THRESHOLDS
# ============================================================

for threshold in RSI_THRESHOLDS:

    df, signal_column = add_rsi_signal(
        df,
        threshold
    )

    signal_count = int(
        df[signal_column].sum()
    )

    print()
    print("=" * 70)
    print(
        f"RSI > {threshold}"
    )
    print("=" * 70)

    print(
        f"Signals: {signal_count}"
    )

    for expiry in EXPIRIES:

        result = backtest(
            df,
            signal_column,
            expiry
        )

        print_result(
            f"Expiry {expiry}",
            result
        )

    # --------------------------------------------------------
    # Expiry 2 stability
    # --------------------------------------------------------

    print()
    print(
        f"Expiry 2 - 4 Parts "
        f"(RSI > {threshold})"
    )

    parts = backtest_parts(
        df,
        signal_column,
        2,
        4
    )

    for i, result in enumerate(
        parts,
        1
    ):

        print_result(
            f"Part {i}",
            result
        )


# ============================================================
# DIRECT COMPARISON - EXPIRY 2
# ============================================================

print()
print("=" * 70)
print("DIRECT COMPARISON - EXPIRY 2")
print("=" * 70)

base_result = backtest(
    df,
    "BASE_CALL",
    2
)

print()

print_result(
    "BASELINE",
    base_result
)

for threshold in RSI_THRESHOLDS:

    signal_column = (
        f"RSI_{threshold}"
    )

    result = backtest(
        df,
        signal_column,
        2
    )

    print_result(
        f"RSI > {threshold}",
        result
    )


# ============================================================
# FINAL
# ============================================================

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
