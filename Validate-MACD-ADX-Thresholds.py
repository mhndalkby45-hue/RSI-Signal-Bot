import requests
import pandas as pd
import ta

from datetime import datetime, timedelta


BOT_NAME = "MACD + ADX Threshold Validation"

SYMBOL = "BTC-USD"
GRANULARITY = 300

STAKE = 1.0
PAYOUT = 0.80

EXPIRIES = [1, 2, 3]
ADX_THRESHOLDS = [20, 25, 30, 35, 40]

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

        response = requests.get(url, params=params, timeout=30)

        if response.status_code != 200:
            print("Download error:", response.status_code)
            current_start = current_end
            continue

        data = response.json()

        if isinstance(data, list):
            all_data.extend(data)

        current_start = current_end

    if not all_data:
        raise RuntimeError("No data downloaded.")

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
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.drop_duplicates(
        subset=["timestamp"]
    )

    df = df.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    df = df.dropna()

    print(f"Downloaded candles: {len(df)}")
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

    df = df.dropna().reset_index(drop=True)

    return df


# ============================================================
# SIGNAL
# ============================================================

def generate_signal(df, adx_threshold):
    df = df.copy()

    macd_cross_up = (
        (df["macd"] > df["macd_signal"]) &
        (
            df["macd"].shift(1)
            <=
            df["macd_signal"].shift(1)
        )
    )

    df["signal"] = (
        macd_cross_up &
        (df["adx"] >= adx_threshold)
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

    results = []

    for i in range(len(df) - expiry):

        if not df["signal"].iloc[i]:
            continue

        entry_price = df["close"].iloc[i]
        exit_price = df["close"].iloc[i + expiry]

        if exit_price > entry_price:
            result = "WIN"
            profit = STAKE * PAYOUT
            wins += 1

        else:
            result = "LOSS"
            profit = -STAKE
            losses += 1

        balance += profit

        if balance > peak:
            peak = balance

        drawdown = peak - balance

        if drawdown > max_drawdown:
            max_drawdown = drawdown

        results.append({
            "index": i,
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
            gross_profit / gross_loss
        )
    else:
        profit_factor = float("inf")

    # Maximum losing streak
    max_streak = 0
    current_streak = 0

    for r in results:
        if r["result"] == "LOSS":
            current_streak += 1

            if current_streak > max_streak:
                max_streak = current_streak
        else:
            current_streak = 0

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

def backtest_parts(df, expiry, parts=4):
    total_length = len(df)

    part_size = total_length // parts

    output = []

    for p in range(parts):

        start = p * part_size

        if p == parts - 1:
            end = total_length
        else:
            end = (p + 1) * part_size

        part_df = df.iloc[start:end].copy()

        result = backtest(
            part_df,
            expiry
        )

        output.append(result)

    return output


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
        f"{name:<28} "
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

break_even = 100 / (1 + PAYOUT)

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
    f"Test period: {TEST_DAYS} days"
)

print(
    f"ADX thresholds: {ADX_THRESHOLDS}"
)

print(
    f"Expiries: {EXPIRIES}"
)

print()


# ============================================================
# DATA
# ============================================================

df = download_data(TEST_DAYS)

df = calculate_indicators(df)


# ============================================================
# TEST
# ============================================================

all_results = []

for threshold in ADX_THRESHOLDS:

    print()
    print("=" * 70)
    print(
        f"MACD + ADX >= {threshold}"
    )
    print("=" * 70)

    test_df = generate_signal(
        df,
        threshold
    )

    signal_count = int(
        test_df["signal"].sum()
    )

    print(
        f"Signals: {signal_count}"
    )

    for expiry in EXPIRIES:

        result = backtest(
            test_df,
            expiry
        )

        print_result(
            f"Expiry {expiry}",
            result
        )

        all_results.append({
            "threshold": threshold,
            "expiry": expiry,
            **result
        })

    # --------------------------------------------------------
    # Parts analysis for Expiry 2
    # --------------------------------------------------------

    print()
    print(
        f"Expiry 2 - 4 Parts Stability "
        f"(ADX >= {threshold})"
    )

    parts = backtest_parts(
        test_df,
        2,
        4
    )

    for i, result in enumerate(parts, 1):

        print_result(
            f"Part {i}",
            result
        )


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)

print()

print(
    f"{'ADX':<8}"
    f"{'Expiry':<10}"
    f"{'Trades':<10}"
    f"{'WR':<10}"
    f"{'PF':<10}"
    f"{'Balance':<12}"
)

print("-" * 70)

for r in all_results:

    pf = r["pf"]

    if pf == float("inf"):
        pf_text = "inf"
    else:
        pf_text = f"{pf:.2f}"

    print(
        f"{r['threshold']:<8}"
        f"{r['expiry']:<10}"
        f"{r['trades']:<10}"
        f"{r['wr']:<10.2f}"
        f"{pf_text:<10}"
        f"{r['balance']:<12.2f}"
    )


# ============================================================
# BEST RESULTS
# ============================================================

print()
print("=" * 70)
print("BEST RESULTS")
print("=" * 70)

valid_results = [
    r for r in all_results
    if r["trades"] >= 20
]

if valid_results:

    best_pf = max(
        valid_results,
        key=lambda x: x["pf"]
    )

    best_balance = max(
        valid_results,
        key=lambda x: x["balance"]
    )

    best_wr = max(
        valid_results,
        key=lambda x: x["wr"]
    )

    print()
    print("Best Profit Factor:")
    print_result(
        f"ADX {best_pf['threshold']} "
        f"Exp {best_pf['expiry']}",
        best_pf
    )

    print()
    print("Best Balance:")
    print_result(
        f"ADX {best_balance['threshold']} "
        f"Exp {best_balance['expiry']}",
        best_balance
    )

    print()
    print("Best Win Rate:")
    print_result(
        f"ADX {best_wr['threshold']} "
        f"Exp {best_wr['expiry']}",
        best_wr
    )

else:

    print(
        "Not enough trades for a reliable comparison."
    )


print()
print("=" * 70)
print("VALIDATION COMPLETE")
print("=" * 70)
