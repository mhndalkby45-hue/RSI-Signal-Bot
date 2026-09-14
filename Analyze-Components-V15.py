import requests
import pandas as pd
import numpy as np

BOT_NAME = "Smart Trading Signal Bot V15 - Component Analyzer"

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
ADX_MIN = 20

EXPIRY_CANDLES = 1

STAKE = 1.0
PAYOUT = 0.80


# ============================================================
# DOWNLOAD DATA
# ============================================================

def get_data():

    url = (
        f"https://api.exchange.coinbase.com/products/"
        f"{DATA_SYMBOL}/candles"
    )

    params = {
        "granularity": 300,
        "limit": LIMIT
    }

    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()

    data = response.json()

    df = pd.DataFrame(
        data,
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
        unit="s"
    )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]

    for col in numeric_columns:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.sort_values("timestamp")
    df = df.reset_index(drop=True)

    return df


# ============================================================
# INDICATORS
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    # EMA
    df["ema_fast"] = (
        df["close"]
        .ewm(span=EMA_FAST, adjust=False)
        .mean()
    )

    df["ema_slow"] = (
        df["close"]
        .ewm(span=EMA_SLOW, adjust=False)
        .mean()
    )

    df["ema_trend"] = (
        df["close"]
        .ewm(span=EMA_TREND, adjust=False)
        .mean()
    )

    # RSI
    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = (
        gain.ewm(
            alpha=1 / RSI_PERIOD,
            adjust=False
        ).mean()
    )

    avg_loss = (
        loss.ewm(
            alpha=1 / RSI_PERIOD,
            adjust=False
        ).mean()
    )

    rs = avg_gain / avg_loss.replace(0, np.nan)

    df["rsi"] = 100 - (
        100 / (1 + rs)
    )

    # MACD
    ema_macd_fast = (
        df["close"]
        .ewm(span=MACD_FAST, adjust=False)
        .mean()
    )

    ema_macd_slow = (
        df["close"]
        .ewm(span=MACD_SLOW, adjust=False)
        .mean()
    )

    df["macd"] = (
        ema_macd_fast -
        ema_macd_slow
    )

    df["macd_signal"] = (
        df["macd"]
        .ewm(
            span=MACD_SIGNAL,
            adjust=False
        )
        .mean()
    )

    df["macd_hist"] = (
        df["macd"] -
        df["macd_signal"]
    )

    # ADX
    high = df["high"]
    low = df["low"]
    close = df["close"]

    previous_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - previous_close).abs()
    tr3 = (low - previous_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where(
        (up_move > down_move) &
        (up_move > 0),
        up_move,
        0
    )

    minus_dm = np.where(
        (down_move > up_move) &
        (down_move > 0),
        down_move,
        0
    )

    tr_smooth = (
        pd.Series(true_range)
        .ewm(
            alpha=1 / ADX_PERIOD,
            adjust=False
        )
        .mean()
    )

    plus_dm_smooth = (
        pd.Series(plus_dm)
        .ewm(
            alpha=1 / ADX_PERIOD,
            adjust=False
        )
        .mean()
    )

    minus_dm_smooth = (
        pd.Series(minus_dm)
        .ewm(
            alpha=1 / ADX_PERIOD,
            adjust=False
        )
        .mean()
    )

    plus_di = (
        100 *
        plus_dm_smooth /
        tr_smooth.replace(0, np.nan)
    )

    minus_di = (
        100 *
        minus_dm_smooth /
        tr_smooth.replace(0, np.nan)
    )

    dx = (
        100 *
        (plus_di - minus_di).abs() /
        (plus_di + minus_di)
        .replace(0, np.nan)
    )

    df["adx"] = (
        dx
        .ewm(
            alpha=1 / ADX_PERIOD,
            adjust=False
        )
        .mean()
    )

    df["+di"] = plus_di
    df["-di"] = minus_di

    # Candle
    df["body"] = (
        df["close"] -
        df["open"]
    ).abs()

    df["range"] = (
        df["high"] -
        df["low"]
    )

    df["body_ratio"] = (
        df["body"] /
        df["range"].replace(0, np.nan)
    )

    df["bullish_candle"] = (
        (df["close"] > df["open"]) &
        (df["body_ratio"] >= 0.50)
    )

    df["bearish_candle"] = (
        (df["close"] < df["open"]) &
        (df["body_ratio"] >= 0.50)
    )

    return df


# ============================================================
# SIGNAL TEST
# ============================================================

def get_signal(
    row,
    use_ema=True,
    use_rsi=True,
    use_macd=True,
    use_adx=True,
    use_candle=True
):

    if pd.isna(row["close"]):
        return None

    # ADX is only used as a filter when enabled
    if use_adx:

        if pd.isna(row["adx"]):
            return None

        if row["adx"] < ADX_MIN:
            return None

    buy_score = 0
    sell_score = 0

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    if use_ema:

        if (
            row["ema_fast"] >
            row["ema_slow"]
        ):
            buy_score += 2

        elif (
            row["ema_fast"] <
            row["ema_slow"]
        ):
            sell_score += 2

        if row["close"] > row["ema_trend"]:
            buy_score += 1

        elif row["close"] < row["ema_trend"]:
            sell_score += 1

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    if use_rsi:

        if pd.isna(row["rsi"]):
            return None

        if 52 <= row["rsi"] <= 68:
            buy_score += 1

        elif 32 <= row["rsi"] <= 48:
            sell_score += 1

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    if use_macd:

        if pd.isna(row["macd_hist"]):
            return None

        if (
            row["macd"] > row["macd_signal"] and
            row["macd_hist"] > 0
        ):
            buy_score += 2

        elif (
            row["macd"] < row["macd_signal"] and
            row["macd_hist"] < 0
        ):
            sell_score += 2

    # --------------------------------------------------------
    # ADX DIRECTION
    # --------------------------------------------------------

    if use_adx:

        if (
            row["+di"] >
            row["-di"]
        ):
            buy_score += 1

        elif (
            row["-di"] >
            row["+di"]
        ):
            sell_score += 1

    # --------------------------------------------------------
    # CANDLE
    # --------------------------------------------------------

    if use_candle:

        if row["bullish_candle"]:
            buy_score += 1

        elif row["bearish_candle"]:
            sell_score += 1

    # --------------------------------------------------------
    # Dynamic minimum score
    # --------------------------------------------------------

    enabled_components = sum([
        use_ema,
        use_rsi,
        use_macd,
        use_adx,
        use_candle
    ])

    # EMA contributes up to 3
    # RSI contributes up to 1
    # MACD contributes up to 2
    # ADX contributes up to 1
    # Candle contributes up to 1
    #
    # We use approximately 60% of available points.

    if enabled_components == 1:
        minimum_score = 1

    elif enabled_components == 2:
        minimum_score = 2

    elif enabled_components == 3:
        minimum_score = 3

    elif enabled_components == 4:
        minimum_score = 4

    else:
        minimum_score = 5

    if (
        buy_score >= minimum_score and
        buy_score > sell_score
    ):
        return "CALL"

    if (
        sell_score >= minimum_score and
        sell_score > buy_score
    ):
        return "PUT"

    return None


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(
    df,
    use_ema=True,
    use_rsi=True,
    use_macd=True,
    use_adx=True,
    use_candle=True
):

    balance = 0.0

    trades = 0
    wins = 0
    losses = 0

    call_trades = 0
    call_wins = 0

    put_trades = 0
    put_wins = 0

    peak_balance = 0.0
    max_drawdown = 0.0

    current_loss_streak = 0
    max_loss_streak = 0

    for i in range(len(df) - EXPIRY_CANDLES):

        row = df.iloc[i]

        signal = get_signal(
            row,
            use_ema=use_ema,
            use_rsi=use_rsi,
            use_macd=use_macd,
            use_adx=use_adx,
            use_candle=use_candle
        )

        if signal is None:
            continue

        entry_price = row["close"]

        exit_price = df.iloc[
            i + EXPIRY_CANDLES
        ]["close"]

        trades += 1

        if signal == "CALL":

            call_trades += 1

            if exit_price > entry_price:

                wins += 1
                call_wins += 1

                balance += STAKE * PAYOUT

                current_loss_streak = 0

            else:

                losses += 1

                balance -= STAKE

                current_loss_streak += 1

        elif signal == "PUT":

            put_trades += 1

            if exit_price < entry_price:

                wins += 1
                put_wins += 1

                balance += STAKE * PAYOUT

                current_loss_streak = 0

            else:

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

    if trades > 0:
        win_rate = (
            wins /
            trades *
            100
        )
    else:
        win_rate = 0.0

    if losses > 0:
        profit_factor = (
            wins * PAYOUT
        ) / losses
    else:
        profit_factor = 0.0

    if call_trades > 0:
        call_win_rate = (
            call_wins /
            call_trades *
            100
        )
    else:
        call_win_rate = 0.0

    if put_trades > 0:
        put_win_rate = (
            put_wins /
            put_trades *
            100
        )
    else:
        put_win_rate = 0.0

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "balance": balance,
        "drawdown": max_drawdown,
        "loss_streak": max_loss_streak,
        "calls": call_trades,
        "call_win_rate": call_win_rate,
        "puts": put_trades,
        "put_win_rate": put_win_rate
    }


# ============================================================
# COMPONENT TESTS
# ============================================================

def run_component_analysis(df):

    tests = [

        (
            "EMA ONLY",
            True,
            False,
            False,
            False,
            False
        ),

        (
            "RSI ONLY",
            False,
            True,
            False,
            False,
            False
        ),

        (
            "MACD ONLY",
            False,
            False,
            True,
            False,
            False
        ),

        (
            "ADX ONLY",
            False,
            False,
            False,
            True,
            False
        ),

        (
            "CANDLE ONLY",
            False,
            False,
            False,
            False,
            True
        ),

        (
            "EMA + RSI",
            True,
            True,
            False,
            False,
            False
        ),

        (
            "EMA + MACD",
            True,
            False,
            True,
            False,
            False
        ),

        (
            "EMA + ADX",
            True,
            False,
            False,
            True,
            False
        ),

        (
            "EMA + CANDLE",
            True,
            False,
            False,
            False,
            True
        ),

        (
            "RSI + MACD",
            False,
            True,
            True,
            False,
            False
        ),

        (
            "RSI + ADX",
            False,
            True,
            False,
            True,
            False
        ),

        (
            "RSI + CANDLE",
            False,
            True,
            False,
            False,
            True
        ),

        (
            "MACD + ADX",
            False,
            False,
            True,
            True,
            False
        ),

        (
            "MACD + CANDLE",
            False,
            False,
            True,
            False,
            True
        ),

        (
            "ADX + CANDLE",
            False,
            False,
            False,
            True,
            True
        ),

        (
            "EMA + RSI + MACD",
            True,
            True,
            True,
            False,
            False
        ),

        (
            "EMA + RSI + ADX",
            True,
            True,
            False,
            True,
            False
        ),

        (
            "EMA + MACD + ADX",
            True,
            False,
            True,
            True,
            False
        ),

        (
            "EMA + MACD + CANDLE",
            True,
            False,
            True,
            False,
            True
        ),

        (
            "EMA + ADX + CANDLE",
            True,
            False,
            False,
            True,
            True
        ),

        (
            "RSI + MACD + ADX",
            False,
            True,
            True,
            True,
            False
        ),

        (
            "RSI + MACD + CANDLE",
            False,
            True,
            True,
            False,
            True
        ),

        (
            "RSI + ADX + CANDLE",
            False,
            True,
            False,
            True,
            True
        ),

        (
            "MACD + ADX + CANDLE",
            False,
            False,
            True,
            True,
            True
        ),

        (
            "ALL COMPONENTS",
            True,
            True,
            True,
            True,
            True
        )
    ]

    results = []

    for test in tests:

        name = test[0]

        result = run_backtest(
            df,
            use_ema=test[1],
            use_rsi=test[2],
            use_macd=test[3],
            use_adx=test[4],
            use_candle=test[5]
        )

        results.append({
            "CONFIG": name,
            "TRADES": result["trades"],
            "WINS": result["wins"],
            "LOSSES": result["losses"],
            "WIN_RATE": round(
                result["win_rate"],
                2
            ),
            "PROFIT_FACTOR": round(
                result["profit_factor"],
                2
            ),
            "BALANCE": round(
                result["balance"],
                2
            ),
            "DRAWDOWN": round(
                result["drawdown"],
                2
            ),
            "LOSS_STREAK": result["loss_streak"],
            "CALLS": result["calls"],
            "CALL_WIN_RATE": round(
                result["call_win_rate"],
                2
            ),
            "PUTS": result["puts"],
            "PUT_WIN_RATE": round(
                result["put_win_rate"],
                2
            )
        })

    return pd.DataFrame(results)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 65)
    print(BOT_NAME)
    print("=" * 65)

    print()
    print("Downloading market data...")

    df = get_data()

    print(
        "Downloaded:",
        len(df),
        "candles"
    )

    print()
    print("Calculating indicators...")

    df = calculate_indicators(df)

    print()
    print("=" * 65)
    print("COMPONENT ANALYSIS")
    print("=" * 65)

    results = run_component_analysis(df)

    pd.set_option(
        "display.max_rows",
        100
    )

    pd.set_option(
        "display.width",
        200
    )

    print()
    print(results.to_string(index=False))

    print()
    print("=" * 65)
    print("BEST CONFIGURATIONS")
    print("=" * 65)

    profitable = results[
        results["TRADES"] > 0
    ].copy()

    if len(profitable) == 0:

        print("No valid trades found.")

        return

    print()
    print("BEST BALANCE:")

    best_balance = profitable.sort_values(
        "BALANCE",
        ascending=False
    ).iloc[0]

    print(best_balance.to_string())

    print()
    print("BEST PROFIT FACTOR:")

    best_pf = profitable.sort_values(
        "PROFIT_FACTOR",
        ascending=False
    ).iloc[0]

    print(best_pf.to_string())

    print()
    print("BEST WIN RATE:")

    best_wr = profitable.sort_values(
        "WIN_RATE",
        ascending=False
    ).iloc[0]

    print(best_wr.to_string())

    print()
    print("LOWEST DRAWDOWN:")

    best_dd = profitable.sort_values(
        "DRAWDOWN",
        ascending=True
    ).iloc[0]

    print(best_dd.to_string())

    print()
    print("=" * 65)
    print("BREAK-EVEN INFORMATION")
    print("=" * 65)

    breakeven = (
        1 /
        (1 + PAYOUT)
    ) * 100

    print(
        "Payout:",
        PAYOUT
    )

    print(
        "Break-even Win Rate:",
        round(breakeven, 2),
        "%"
    )

    print()
    print("=" * 65)
    print("IMPORTANT")
    print("=" * 65)

    print(
        "This analysis is for strategy research only."
    )

    print(
        "A high win rate on a small number of trades "
        "does not prove profitability."
    )

    print(
        "Do not use these results as a guarantee "
        "of future trading performance."
    )

    print()
    print("ANALYSIS COMPLETE")


if __name__ == "__main__":
    main()
