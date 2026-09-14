import requests
import pandas as pd
import numpy as np

BOT_NAME = "Smart Trading Signal Bot V15 - Strategy Analyzer"

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

    response = requests.get(
        url,
        params=params,
        timeout=20
    )

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

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    df["ema_fast"] = (
        df["close"]
        .ewm(
            span=EMA_FAST,
            adjust=False
        )
        .mean()
    )

    df["ema_slow"] = (
        df["close"]
        .ewm(
            span=EMA_SLOW,
            adjust=False
        )
        .mean()
    )

    df["ema_trend"] = (
        df["close"]
        .ewm(
            span=EMA_TREND,
            adjust=False
        )
        .mean()
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = (
        gain
        .ewm(
            alpha=1 / RSI_PERIOD,
            adjust=False
        )
        .mean()
    )

    avg_loss = (
        loss
        .ewm(
            alpha=1 / RSI_PERIOD,
            adjust=False
        )
        .mean()
    )

    rs = (
        avg_gain /
        avg_loss.replace(0, np.nan)
    )

    df["rsi"] = (
        100 -
        (100 / (1 + rs))
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    macd_fast = (
        df["close"]
        .ewm(
            span=MACD_FAST,
            adjust=False
        )
        .mean()
    )

    macd_slow = (
        df["close"]
        .ewm(
            span=MACD_SLOW,
            adjust=False
        )
        .mean()
    )

    df["macd"] = (
        macd_fast -
        macd_slow
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

    # --------------------------------------------------------
    # ADX / DI
    # --------------------------------------------------------

    high = df["high"]
    low = df["low"]
    close = df["close"]

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
        [
            tr1,
            tr2,
            tr3
        ],
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
        tr_smooth.replace(
            0,
            np.nan
        )
    )

    minus_di = (
        100 *
        minus_dm_smooth /
        tr_smooth.replace(
            0,
            np.nan
        )
    )

    dx = (
        100 *
        (plus_di - minus_di).abs() /
        (plus_di + minus_di)
        .replace(
            0,
            np.nan
        )
    )

    df["adx"] = (
        dx
        .ewm(
            alpha=1 / ADX_PERIOD,
            adjust=False
        )
        .mean()
    )

    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    # --------------------------------------------------------
    # Candle
    # --------------------------------------------------------

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
        df["range"].replace(
            0,
            np.nan
        )
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
# STRATEGIES
# ============================================================

def strategy_ema_trend(row):

    if (
        row["ema_fast"] >
        row["ema_slow"] >
        row["ema_trend"]
    ):
        return "CALL"

    if (
        row["ema_fast"] <
        row["ema_slow"] <
        row["ema_trend"]
    ):
        return "PUT"

    return None


def strategy_ema_cross(row):

    if (
        pd.isna(row["ema_fast"]) or
        pd.isna(row["ema_slow"])
    ):
        return None

    if row["ema_fast_prev"] <= row["ema_slow_prev"]:

        if row["ema_fast"] > row["ema_slow"]:
            return "CALL"

    if row["ema_fast_prev"] >= row["ema_slow_prev"]:

        if row["ema_fast"] < row["ema_slow"]:
            return "PUT"

    return None


def strategy_rsi_zone(row):

    if pd.isna(row["rsi"]):
        return None

    if 30 <= row["rsi"] <= 40:
        return "CALL"

    if 60 <= row["rsi"] <= 70:
        return "PUT"

    return None


def strategy_rsi_momentum(row):

    if (
        pd.isna(row["rsi"]) or
        pd.isna(row["rsi_prev"])
    ):
        return None

    if (
        row["rsi"] > 50 and
        row["rsi"] > row["rsi_prev"]
    ):
        return "CALL"

    if (
        row["rsi"] < 50 and
        row["rsi"] < row["rsi_prev"]
    ):
        return "PUT"

    return None


def strategy_macd_cross(row):

    if (
        pd.isna(row["macd"]) or
        pd.isna(row["macd_signal"]) or
        pd.isna(row["macd_prev"]) or
        pd.isna(row["macd_signal_prev"])
    ):
        return None

    if (
        row["macd_prev"] <=
        row["macd_signal_prev"] and
        row["macd"] >
        row["macd_signal"]
    ):
        return "CALL"

    if (
        row["macd_prev"] >=
        row["macd_signal_prev"] and
        row["macd"] <
        row["macd_signal"]
    ):
        return "PUT"

    return None


def strategy_macd_histogram(row):

    if pd.isna(row["macd_hist"]):
        return None

    if (
        row["macd_hist"] > 0 and
        row["macd_hist"] >
        row["macd_hist_prev"]
    ):
        return "CALL"

    if (
        row["macd_hist"] < 0 and
        row["macd_hist"] <
        row["macd_hist_prev"]
    ):
        return "PUT"

    return None


def strategy_adx_direction(row):

    if (
        pd.isna(row["adx"]) or
        pd.isna(row["plus_di"]) or
        pd.isna(row["minus_di"])
    ):
        return None

    if row["adx"] < ADX_MIN:
        return None

    if row["plus_di"] > row["minus_di"]:
        return "CALL"

    if row["minus_di"] > row["plus_di"]:
        return "PUT"

    return None


def strategy_candle(row):

    if row["bullish_candle"]:
        return "CALL"

    if row["bearish_candle"]:
        return "PUT"

    return None


def strategy_ema_rsi(row):

    if pd.isna(row["rsi"]):
        return None

    if (
        row["ema_fast"] >
        row["ema_slow"] and
        row["close"] >
        row["ema_trend"] and
        row["rsi"] > 50
    ):
        return "CALL"

    if (
        row["ema_fast"] <
        row["ema_slow"] and
        row["close"] <
        row["ema_trend"] and
        row["rsi"] < 50
    ):
        return "PUT"

    return None


def strategy_ema_macd(row):

    if pd.isna(row["macd_hist"]):
        return None

    if (
        row["ema_fast"] >
        row["ema_slow"] and
        row["close"] >
        row["ema_trend"] and
        row["macd_hist"] > 0
    ):
        return "CALL"

    if (
        row["ema_fast"] <
        row["ema_slow"] and
        row["close"] <
        row["ema_trend"] and
        row["macd_hist"] < 0
    ):
        return "PUT"

    return None


def strategy_ema_macd_adx(row):

    if (
        pd.isna(row["macd_hist"]) or
        pd.isna(row["adx"])
    ):
        return None

    if (
        row["adx"] < ADX_MIN
    ):
        return None

    if (
        row["ema_fast"] >
        row["ema_slow"] and
        row["close"] >
        row["ema_trend"] and
        row["macd_hist"] > 0 and
        row["plus_di"] >
        row["minus_di"]
    ):
        return "CALL"

    if (
        row["ema_fast"] <
        row["ema_slow"] and
        row["close"] <
        row["ema_trend"] and
        row["macd_hist"] < 0 and
        row["minus_di"] >
        row["plus_di"]
    ):
        return "PUT"

    return None


def strategy_ema_macd_rsi(row):

    if (
        pd.isna(row["macd_hist"]) or
        pd.isna(row["rsi"])
    ):
        return None

    if (
        row["ema_fast"] >
        row["ema_slow"] and
        row["close"] >
        row["ema_trend"] and
        row["macd_hist"] > 0 and
        row["rsi"] > 50
    ):
        return "CALL"

    if (
        row["ema_fast"] <
        row["ema_slow"] and
        row["close"] <
        row["ema_trend"] and
        row["macd_hist"] < 0 and
        row["rsi"] < 50
    ):
        return "PUT"

    return None


def strategy_all(row):

    if (
        pd.isna(row["macd_hist"]) or
        pd.isna(row["rsi"]) or
        pd.isna(row["adx"])
    ):
        return None

    if row["adx"] < ADX_MIN:
        return None

    if (
        row["ema_fast"] >
        row["ema_slow"] and
        row["close"] >
        row["ema_trend"] and
        row["rsi"] > 50 and
        row["macd_hist"] > 0 and
        row["plus_di"] >
        row["minus_di"] and
        row["bullish_candle"]
    ):
        return "CALL"

    if (
        row["ema_fast"] <
        row["ema_slow"] and
        row["close"] <
        row["ema_trend"] and
        row["rsi"] < 50 and
        row["macd_hist"] < 0 and
        row["minus_di"] >
        row["plus_di"] and
        row["bearish_candle"]
    ):
        return "PUT"

    return None


# ============================================================
# BACKTEST ENGINE
# ============================================================

def backtest(
    df,
    strategy_function,
    expiry
):

    trades = 0
    wins = 0
    losses = 0

    call_trades = 0
    call_wins = 0

    put_trades = 0
    put_wins = 0

    balance = 0.0
    peak_balance = 0.0
    max_drawdown = 0.0

    current_loss_streak = 0
    max_loss_streak = 0

    for i in range(1, len(df) - expiry):

        row = df.iloc[i]

        signal = strategy_function(row)

        if signal is None:
            continue

        entry = row["close"]

        exit_price = df.iloc[
            i + expiry
        ]["close"]

        trades += 1

        if signal == "CALL":

            call_trades += 1

            if exit_price > entry:

                wins += 1
                call_wins += 1

                balance += (
                    STAKE *
                    PAYOUT
                )

                current_loss_streak = 0

            else:

                losses += 1

                balance -= STAKE

                current_loss_streak += 1

        elif signal == "PUT":

            put_trades += 1

            if exit_price < entry:

                wins += 1
                put_wins += 1

                balance += (
                    STAKE *
                    PAYOUT
                )

                current_loss_streak = 0

            else:

                losses += 1

                balance -= STAKE

                current_loss_streak += 1

        if current_loss_streak > max_loss_streak:
            max_loss_streak = current_loss_streak

        if balance > peak_balance:
            peak_balance = balance

        drawdown = (
            peak_balance -
            balance
        )

        if drawdown > max_drawdown:
            max_drawdown = drawdown

    if trades > 0:

        win_rate = (
            wins /
            trades *
            100
        )

    else:

        win_rate = 0

    if losses > 0:

        profit_factor = (
            wins *
            PAYOUT
        ) / losses

    else:

        profit_factor = 0

    if call_trades > 0:

        call_win_rate = (
            call_wins /
            call_trades *
            100
        )

    else:

        call_win_rate = 0

    if put_trades > 0:

        put_win_rate = (
            put_wins /
            put_trades *
            100
        )

    else:

        put_win_rate = 0

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
# ANALYSIS
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

    # Previous values
    df["ema_fast_prev"] = df["ema_fast"].shift(1)
    df["ema_slow_prev"] = df["ema_slow"].shift(1)

    df["rsi_prev"] = df["rsi"].shift(1)

    df["macd_prev"] = df["macd"].shift(1)
    df["macd_signal_prev"] = (
        df["macd_signal"].shift(1)
    )

    df["macd_hist_prev"] = (
        df["macd_hist"].shift(1)
    )

    strategies = [

        (
            "EMA TREND",
            strategy_ema_trend
        ),

        (
            "EMA CROSS",
            strategy_ema_cross
        ),

        (
            "RSI ZONE",
            strategy_rsi_zone
        ),

        (
            "RSI MOMENTUM",
            strategy_rsi_momentum
        ),

        (
            "MACD CROSS",
            strategy_macd_cross
        ),

        (
            "MACD HISTOGRAM",
            strategy_macd_histogram
        ),

        (
            "ADX DIRECTION",
            strategy_adx_direction
        ),

        (
            "CANDLE",
            strategy_candle
        ),

        (
            "EMA + RSI",
            strategy_ema_rsi
        ),

        (
            "EMA + MACD",
            strategy_ema_macd
        ),

        (
            "EMA + MACD + ADX",
            strategy_ema_macd_adx
        ),

        (
            "EMA + MACD + RSI",
            strategy_ema_macd_rsi
        ),

        (
            "ALL CONDITIONS",
            strategy_all
        )
    ]

    results = []

    print()
    print("=" * 65)
    print("STRATEGY + EXPIRY ANALYSIS")
    print("=" * 65)

    for name, function in strategies:

        for expiry in [1, 2, 3]:

            result = backtest(
                df,
                function,
                expiry
            )

            results.append({
                "STRATEGY": name,
                "EXPIRY": expiry,
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
                "LOSS_STREAK": result[
                    "loss_streak"
                ],
                "CALLS": result["calls"],
                "CALL_WR": round(
                    result["call_win_rate"],
                    2
                ),
                "PUTS": result["puts"],
                "PUT_WR": round(
                    result["put_win_rate"],
                    2
                )
            })

    results_df = pd.DataFrame(results)

    pd.set_option(
        "display.max_rows",
        200
    )

    pd.set_option(
        "display.width",
        220
    )

    print()
    print(
        results_df.to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # Best balance
    # --------------------------------------------------------

    valid = results_df[
        results_df["TRADES"] >= 20
    ].copy()

    print()
    print("=" * 65)
    print("BEST RESULTS")
    print("=" * 65)

    if len(valid) == 0:

        print(
            "Not enough trades for a meaningful comparison."
        )

    else:

        print()
        print("BEST BALANCE:")

        print(
            valid.sort_values(
                "BALANCE",
                ascending=False
            ).head(5).to_string(
                index=False
            )
        )

        print()
        print("BEST WIN RATE:")

        print(
            valid.sort_values(
                "WIN_RATE",
                ascending=False
            ).head(5).to_string(
                index=False
            )
        )

        print()
        print("BEST PROFIT FACTOR:")

        print(
            valid.sort_values(
                "PROFIT_FACTOR",
                ascending=False
            ).head(5).to_string(
                index=False
            )
        )

        print()
        print("LOWEST DRAWDOWN:")

        print(
            valid.sort_values(
                "DRAWDOWN",
                ascending=True
            ).head(5).to_string(
                index=False
            )
        )

    # --------------------------------------------------------
    # Break-even
    # --------------------------------------------------------

    breakeven = (
        1 /
        (1 + PAYOUT)
    ) * 100

    print()
    print("=" * 65)
    print("BREAK-EVEN")
    print("=" * 65)

    print(
        "Payout:",
        PAYOUT
    )

    print(
        "Required Win Rate:",
        round(
            breakeven,
            2
        ),
        "%"
    )

    print()
    print("=" * 65)
    print("IMPORTANT")
    print("=" * 65)

    print(
        "This is historical backtesting only."
    )

    print(
        "No strategy here is guaranteed to be profitable."
    )

    print(
        "Do not use the results as a guarantee "
        "for future trades or real-money trading."
    )

    print()
    print("ANALYSIS COMPLETE")


if __name__ == "__main__":
    main()
