import requests
import pandas as pd
import ta

from datetime import datetime, timedelta


BOT_NAME = "MACD + ADX35 CALL/PUT Validation"

SYMBOL = "BTC-USD"
GRANULARITY = 300

STAKE = 1.0
PAYOUT = 0.80

EXPIRIES = [1, 2, 3]
ADX_MIN = 35

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

    macd = ta.trend.MACD(
        close=df["close"],
        window_slow=26,
        window_fast=12,
        window_sign=9
    )

    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    adx_indicator = ta.trend.ADXIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    )

    df["adx"] = adx_indicator.adx()

    df = df.dropna().reset_index(
        drop=True
    )

    return df


# ============================================================
# SIGNALS
# ============================================================

def generate_signals(df):

    df = df.copy()

    # --------------------------------------------------------
    # MACD bullish crossover
    # --------------------------------------------------------

    macd_cross_up = (
        (df["macd"] > df["macd_signal"]) &
        (
            df["macd"].shift(1)
            <=
            df["macd_signal"].shift(1)
        )
    )

    # --------------------------------------------------------
    # MACD bearish crossover
    # --------------------------------------------------------

    macd_cross_down = (
        (df["macd"] < df["macd_signal"]) &
        (
            df["macd"].shift(1)
            >=
            df["macd_signal"].shift(1)
        )
    )

    # --------------------------------------------------------
    # CALL / PUT
    # --------------------------------------------------------

    df["CALL"] = (
        macd_cross_up &
        (df["adx"] >= ADX_MIN)
    )

    df["PUT"] = (
        macd_cross_down &
        (df["adx"] >= ADX_MIN)
    )

    # Combined signal
    df["signal"] = (
        df["CALL"] |
        df["PUT"]
    )

    return df


# ============================================================
# BACKTEST
# ============================================================

def backtest(df, expiry):

    wins = 0
    losses = 0

    balance = 0.0

    peak = 0.0
    max_drawdown = 0.0

    max_streak = 0
    current_streak = 0

    results = []

    for i in range(len(df) - expiry):

        signal = None

        if df["CALL"].iloc[i]:
            signal = "CALL"

        elif df["PUT"].iloc[i]:
            signal = "PUT"

        if signal is None:
            continue

        entry_price = df["close"].iloc[i]

        exit_price = df[
            "close"
        ].iloc[i + expiry]

        # ----------------------------------------------------
        # CALL
        # ----------------------------------------------------

        if signal == "CALL":

            if exit_price > entry_price:
                result = "WIN"
            else:
                result = "LOSS"

        # ----------------------------------------------------
        # PUT
        # ----------------------------------------------------

        else:

            if exit_price < entry_price:
                result = "WIN"
            else:
                result = "LOSS"

        # ----------------------------------------------------
        # Profit
        # ----------------------------------------------------

        if result == "WIN":

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

        results.append({
            "signal": signal,
            "result": result,
            "profit": profit
        })

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
            "streak": 0,
            "calls": 0,
            "puts": 0
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

    calls = sum(
        1
        for r in results
        if r["signal"] == "CALL"
    )

    puts = sum(
        1
        for r in results
        if r["signal"] == "PUT"
    )

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "wr": win_rate,
        "pf": profit_factor,
        "balance": balance,
        "drawdown": max_drawdown,
        "streak": max_streak,
        "calls": calls,
        "puts": puts
    }


# ============================================================
# DIRECTION BACKTEST
# ============================================================

def backtest_direction(
    df,
    expiry,
    direction
):

    temp = df.copy()

    if direction == "CALL":

        temp["PUT"] = False

    elif direction == "PUT":

        temp["CALL"] = False

    return backtest(
        temp,
        expiry
    )


# ============================================================
# PRINT RESULT
# ============================================================

def print_result(name, result):

    pf = result["pf"]

    if pf == float("inf"):
        pf_text = "inf"
    else:
        pf_text = f"{pf:.2f}"

    print(
        f"{name:<24}"
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

df = generate_signals(
    df
)


# ============================================================
# SIGNAL COUNTS
# ============================================================

call_count = int(
    df["CALL"].sum()
)

put_count = int(
    df["PUT"].sum()
)

total_count = call_count + put_count

print()
print("=" * 70)
print("SIGNALS")
print("=" * 70)

print(
    f"CALL signals: {call_count}"
)

print(
    f"PUT signals:  {put_count}"
)

print(
    f"TOTAL signals: {total_count}"
)


# ============================================================
# TEST ALL EXPIRIES
# ============================================================

for expiry in EXPIRIES:

    print()
    print("=" * 70)
    print(
        f"EXPIRY {expiry}"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # CALL
    # --------------------------------------------------------

    call_result = backtest_direction(
        df,
        expiry,
        "CALL"
    )

    print_result(
        "CALL",
        call_result
    )

    # --------------------------------------------------------
    # PUT
    # --------------------------------------------------------

    put_result = backtest_direction(
        df,
        expiry,
        "PUT"
    )

    print_result(
        "PUT",
        put_result
    )

    # --------------------------------------------------------
    # CALL + PUT
    # --------------------------------------------------------

    combined_result = backtest(
        df,
        expiry
    )

    print_result(
        "CALL + PUT",
        combined_result
    )


# ============================================================
# DIRECTION COMPARISON
# ============================================================

print()
print("=" * 70)
print("DIRECTION COMPARISON - EXPIRY 2")
print("=" * 70)

call_result = backtest_direction(
    df,
    2,
    "CALL"
)

put_result = backtest_direction(
    df,
    2,
    "PUT"
)

combined_result = backtest(
    df,
    2
)

print()

print_result(
    "CALL",
    call_result
)

print_result(
    "PUT",
    put_result
)

print_result(
    "CALL + PUT",
    combined_result
)


# ============================================================
# FINAL ANALYSIS
# ============================================================

print()
print("=" * 70)
print("VALIDATION COMPLETE")
print("=" * 70)

print()

print(
    "Important:"
)

print(
    "This is historical backtesting only."
)

print(
    "It does NOT guarantee future profitability."
)

print(
    "Pocket Option prices may differ from Coinbase."
)

print()
