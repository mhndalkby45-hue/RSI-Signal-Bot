import requests
import pandas as pd
import ta

from datetime import datetime, timedelta


BOT_NAME = "MACD + ADX35 CALL + EMA50 Validation"

SYMBOL = "BTC-USD"
GRANULARITY = 300

STAKE = 1.0
PAYOUT = 0.80

EXPIRIES = [1, 2, 3]

ADX_MIN = 35
EMA_PERIOD = 50

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
    # BASELINE
    #
    # MACD CALL + ADX >= 35
    # --------------------------------------------------------

    df["BASE_CALL"] = (
        macd_cross_up &
        (df["adx"] >= ADX_MIN)
    )

    # --------------------------------------------------------
    # EMA FILTER
    #
    # Price must be above EMA50
    # --------------------------------------------------------

    df["EMA_CALL"] = (
        df["BASE_CALL"] &
        (df["close"] > df["ema50"])
    )

    return df


# ============================================================
# BACKTEST
# ============================================================

def backtest(df, signal_column, expiry):

    wins = 0
    losses = 0

    balance = 0.0

    peak = 0.0
    max_drawdown = 0.0

    max_streak = 0
    current_streak = 0

    results = []

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

            result = "WIN"

            wins += 1

            profit = (
                STAKE * PAYOUT
            )

            current_streak = 0

        else:

            result = "LOSS"

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
# PRINT RESULT
# ============================================================

def print_result(name, result):

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

base_count = int(
    df["BASE_CALL"].sum()
)

ema_count = int(
    df["EMA_CALL"].sum()
)

removed = (
    base_count - ema_count
)

print()
print("=" * 70)
print("SIGNALS")
print("=" * 70)

print(
    f"BASE CALL signals: {base_count}"
)

print(
    f"EMA50 CALL signals: {ema_count}"
)

print(
    f"Signals removed by EMA50: {removed}"
)


# ============================================================
# TEST
# ============================================================

all_results = []

for expiry in EXPIRIES:

    print()
    print("=" * 70)
    print(
        f"EXPIRY {expiry}"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # BASELINE
    # --------------------------------------------------------

    base_result = backtest(
        df,
        "BASE_CALL",
        expiry
    )

    print_result(
        "MACD + ADX35",
        base_result
    )

    all_results.append({
        "strategy": "BASE",
        "expiry": expiry,
        **base_result
    })

    # --------------------------------------------------------
    # EMA50
    # --------------------------------------------------------

    ema_result = backtest(
        df,
        "EMA_CALL",
        expiry
    )

    print_result(
        "MACD + ADX35 + EMA50",
        ema_result
    )

    all_results.append({
        "strategy": "EMA50",
        "expiry": expiry,
        **ema_result
    })


# ============================================================
# DIRECT COMPARISON
# ============================================================

print()
print("=" * 70)
print("DIRECT COMPARISON - EXPIRY 2")
print("=" * 70)

base_exp2 = backtest(
    df,
    "BASE_CALL",
    2
)

ema_exp2 = backtest(
    df,
    "EMA_CALL",
    2
)

print()

print_result(
    "BASELINE",
    base_exp2
)

print_result(
    "WITH EMA50",
    ema_exp2
)

print()


# ============================================================
# DECISION
# ============================================================

print("=" * 70)
print("DECISION")
print("=" * 70)

print()

if (
    ema_exp2["trades"] > 0 and
    ema_exp2["pf"] > base_exp2["pf"] and
    ema_exp2["wr"] > base_exp2["wr"]
):

    print(
        "EMA50 IMPROVED BOTH WR AND PF."
    )

elif (
    ema_exp2["pf"] > base_exp2["pf"]
):

    print(
        "EMA50 IMPROVED PROFIT FACTOR."
    )

elif (
    ema_exp2["wr"] > base_exp2["wr"]
):

    print(
        "EMA50 IMPROVED WIN RATE."
    )

else:

    print(
        "EMA50 DID NOT IMPROVE THE BASELINE."
    )


print()

print("=" * 70)
print("VALIDATION COMPLETE")
print("=" * 70)

print()

print(
    "Historical backtest only."
)

print(
    "No guarantee of future profitability."
)

print(
    "Coinbase prices may differ from Pocket Option."
)
