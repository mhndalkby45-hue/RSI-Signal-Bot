import requests
import pandas as pd
import numpy as np

BOT_NAME = "Smart Trading Signal Bot V15"

# ==================================================
# MARKET
# ==================================================

DATA_SYMBOL = "BTC-USD"
DISPLAY_SYMBOL = "BTCUSDT"

INTERVAL = "5m"
LIMIT = 1000

# ==================================================
# INDICATORS
# ==================================================

EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 50

RSI_PERIOD = 14

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

ADX_PERIOD = 14
ADX_MIN = 20

# ==================================================
# SIGNAL SETTINGS
# ==================================================

MIN_SCORE = 6

EXPIRY_CANDLES = 1

# ==================================================
# POCKET OPTION SIMULATION
# ==================================================

STAKE = 1.0

PAYOUT = 0.80


def get_data():

    url = (
        "https://api.exchange.coinbase.com/"
        "products/"
        + DATA_SYMBOL +
        "/candles"
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

        end_time = (
            oldest_time -
            300
        )

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

    df = df.sort_values(
        "time"
    )

    df = df.drop_duplicates(
        subset="time"
    )

    df = df.tail(
        LIMIT
    ).reset_index(
        drop=True
    )

    return df

  def calculate_indicators(df):

    # ==================================================
    # EMA TREND
    # ==================================================

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

    # ==================================================
    # RSI
    # ==================================================

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

    df["rsi"] = 100 - (
        100 / (1 + rs)
    )

    # ==================================================
    # MACD
    # ==================================================

    ema12 = df["close"].ewm(
        span=MACD_FAST,
        adjust=False
    ).mean()

    ema26 = df["close"].ewm(
        span=MACD_SLOW,
        adjust=False
    ).mean()

    df["macd"] = ema12 - ema26

    df["macd_signal"] = df["macd"].ewm(
        span=MACD_SIGNAL,
        adjust=False
    ).mean()

    df["macd_hist"] = (
        df["macd"] -
        df["macd_signal"]
    )

    # ==================================================
    # ADX
    # ==================================================

    high = df["high"]
    low = df["low"]
    close = df["close"]

    previous_high = high.shift(1)
    previous_low = low.shift(1)
    previous_close = close.shift(1)

    tr1 = high - low

    tr2 = (
        high - previous_close
    ).abs()

    tr3 = (
        low - previous_close
    ).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    up_move = (
        high - previous_high
    )

    down_move = (
        previous_low - low
    )

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
        100 *
        plus_dm.ewm(
            alpha=1 / ADX_PERIOD,
            min_periods=ADX_PERIOD,
            adjust=False
        ).mean() /
        atr
    )

    minus_di = (
        100 *
        minus_dm.ewm(
            alpha=1 / ADX_PERIOD,
            min_periods=ADX_PERIOD,
            adjust=False
        ).mean() /
        atr
    )

    dx = (
        100 *
        (plus_di - minus_di).abs() /
        (plus_di + minus_di)
    )

    df["adx"] = dx.ewm(
        alpha=1 / ADX_PERIOD,
        min_periods=ADX_PERIOD,
        adjust=False
    ).mean()

    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    # ==================================================
    # CANDLE STRENGTH
    # ==================================================

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
        (df["close"] > df["open"]) &
        (df["body_ratio"] >= 0.50)
    )

    df["bearish_candle"] = (
        (df["close"] < df["open"]) &
        (df["body_ratio"] >= 0.50)
    )

    return df

def get_signal(df, index):

    row = df.iloc[index]
    previous = df.iloc[index - 1]

    # ==================================================
    # DATA CHECK
    # ==================================================

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

            return "WAIT", 0

    # ==================================================
    # TREND STRENGTH
    # ==================================================

    if row["adx"] < ADX_MIN:

        return "WAIT", 0

    buy_score = 0
    sell_score = 0

    # ==================================================
    # EMA TREND
    # ==================================================

    bullish_trend = (
        row["ema_fast"] >
        row["ema_slow"] >
        row["ema_trend"]
    )

    bearish_trend = (
        row["ema_fast"] <
        row["ema_slow"] <
        row["ema_trend"]
    )

    if bullish_trend:

        buy_score += 2

    if bearish_trend:

        sell_score += 2

    # ==================================================
    # PRICE POSITION
    # ==================================================

    if row["close"] > row["ema_trend"]:

        buy_score += 1

    if row["close"] < row["ema_trend"]:

        sell_score += 1

    # ==================================================
    # RSI MOMENTUM
    # ==================================================

    if 52 <= row["rsi"] <= 68:

        buy_score += 1

    if 32 <= row["rsi"] <= 48:

        sell_score += 1

    # ==================================================
    # MACD MOMENTUM
    # ==================================================

    if (
        row["macd"] > row["macd_signal"]
        and
        row["macd_hist"] > previous["macd_hist"]
    ):

        buy_score += 2

    if (
        row["macd"] < row["macd_signal"]
        and
        row["macd_hist"] < previous["macd_hist"]
    ):

        sell_score += 2

    # ==================================================
    # DIRECTIONAL MOVEMENT
    # ==================================================

    if row["plus_di"] > row["minus_di"]:

        buy_score += 1

    if row["minus_di"] > row["plus_di"]:

        sell_score += 1

    # ==================================================
    # CANDLE CONFIRMATION
    # ==================================================

    if row["bullish_candle"]:

        buy_score += 1

    if row["bearish_candle"]:

        sell_score += 1

    # ==================================================
    # FINAL SIGNAL
    # ==================================================

    if (
        buy_score >= MIN_SCORE
        and
        buy_score > sell_score
    ):

        confidence = min(
            100,
            50 + (
                buy_score - 5
            ) * 10
        )

        return "CALL", confidence

    if (
        sell_score >= MIN_SCORE
        and
        sell_score > buy_score
    ):

        confidence = min(
            100,
            50 + (
                sell_score - 5
            ) * 10
        )

        return "PUT", confidence

    return "WAIT", 0

def run_backtest(df):

    trades = []

    balance = 0.0

    peak_balance = 0.0

    max_drawdown = 0.0

    current_loss_streak = 0

    max_loss_streak = 0

    for i in range(
        1,
        len(df) - EXPIRY_CANDLES
    ):

        signal, confidence = get_signal(
            df,
            i
        )

        if signal == "WAIT":
            continue

        entry_price = df.iloc[i]["close"]

        exit_index = (
            i +
            EXPIRY_CANDLES
        )

        exit_price = df.iloc[exit_index]["close"]

        # ==================================================
        # RESULT
        # ==================================================

        if signal == "CALL":

            win = (
                exit_price >
                entry_price
            )

        else:

            win = (
                exit_price <
                entry_price
            )

        # ==================================================
        # PAYOUT
        # ==================================================

        if win:

            result = "WIN"

            profit = (
                STAKE *
                PAYOUT
            )

            balance += profit

            current_loss_streak = 0

        else:

            result = "LOSS"

            profit = -STAKE

            balance += profit

            current_loss_streak += 1

            if (
                current_loss_streak >
                max_loss_streak
            ):

                max_loss_streak = (
                    current_loss_streak
                )

        # ==================================================
        # DRAWDOWN
        # ==================================================

        if balance > peak_balance:

            peak_balance = balance

        drawdown = (
            peak_balance -
            balance
        )

        if drawdown > max_drawdown:

            max_drawdown = drawdown

        # ==================================================
        # SAVE TRADE
        # ==================================================

        trades.append({

            "time":
                df.iloc[i]["time"],

            "signal":
                signal,

            "confidence":
                confidence,

            "entry":
                entry_price,

            "exit":
                exit_price,

            "result":
                result,

            "profit":
                profit,

            "balance":
                balance
        })

    return (
        trades,
        balance,
        max_drawdown,
        max_loss_streak
    )

def analyze_results(
    trades,
    final_balance,
    max_drawdown,
    max_loss_streak
):

    print()
    print("==================================================")
    print("V15 BACKTEST RESULTS")
    print("==================================================")

    if not trades:

        print("No valid trades found.")

        return

    total_trades = len(trades)

    wins = sum(
        1
        for trade in trades
        if trade["result"] == "WIN"
    )

    losses = (
        total_trades -
        wins
    )

    win_rate = (
        wins /
        total_trades
    ) * 100

    avg_confidence = (
        sum(
            trade["confidence"]
            for trade in trades
        ) /
        total_trades
    )

    # ==================================================
    # CALL / PUT
    # ==================================================

    call_trades = [
        trade
        for trade in trades
        if trade["signal"] == "CALL"
    ]

    put_trades = [
        trade
        for trade in trades
        if trade["signal"] == "PUT"
    ]

    call_wins = sum(
        1
        for trade in call_trades
        if trade["result"] == "WIN"
    )

    put_wins = sum(
        1
        for trade in put_trades
        if trade["result"] == "WIN"
    )

    call_win_rate = (
        call_wins /
        len(call_trades) *
        100
        if call_trades
        else 0
    )

    put_win_rate = (
        put_wins /
        len(put_trades) *
        100
        if put_trades
        else 0
    )

    # ==================================================
    # PROFIT / LOSS
    # ==================================================

    total_profit = sum(
        trade["profit"]
        for trade in trades
        if trade["profit"] > 0
    )

    total_loss = abs(
        sum(
            trade["profit"]
            for trade in trades
            if trade["profit"] < 0
        )
    )

    if total_loss > 0:

        profit_factor = (
            total_profit /
            total_loss
        )

    else:

        profit_factor = float("inf")

    # ==================================================
    # BREAK-EVEN WIN RATE
    # ==================================================

    break_even_rate = (
        1 /
        (1 + PAYOUT)
    ) * 100

    # ==================================================
    # PRINT
    # ==================================================

    print(
        "Total Trades      :",
        total_trades
    )

    print(
        "Wins              :",
        wins
    )

    print(
        "Losses            :",
        losses
    )

    print(
        "Win Rate          :",
        round(win_rate, 2),
        "%"
    )

    print(
        "Break-even Rate   :",
        round(break_even_rate, 2),
        "%"
    )

    print(
        "Avg Confidence    :",
        round(avg_confidence, 2),
        "%"
    )

    print(
        "Profit Factor     :",
        round(profit_factor, 2)
        if profit_factor != float("inf")
        else "INF"
    )

    print(
        "Final Balance     :",
        round(final_balance, 2)
    )

    print(
        "Max Drawdown      :",
        round(max_drawdown, 2)
    )

    print(
        "Max Loss Streak   :",
        max_loss_streak
    )

    print()
    print(
        "CALL Trades       :",
        len(call_trades)
    )

    print(
        "CALL Win Rate     :",
        round(call_win_rate, 2),
        "%"
    )

    print()
    print(
        "PUT Trades        :",
        len(put_trades)
    )

    print(
        "PUT Win Rate      :",
        round(put_win_rate, 2),
        "%"
    )

    # ==================================================
    # EVALUATION
    # ==================================================

    print()
    print("==================================================")
    print("V15 EVALUATION")
    print("==================================================")

    if (
        win_rate >
        break_even_rate
        and
        profit_factor > 1
    ):

        print(
            "STATUS: POSITIVE EDGE"
        )

    elif (
        win_rate >= 50
        and
        profit_factor >= 1
    ):

        print(
            "STATUS: CLOSE TO BREAK-EVEN"
        )

    else:

        print(
            "STATUS: NOT PROFITABLE"
        )

    # ==================================================
    # LAST TRADES
    # ==================================================

    print()
    print("LAST 10 TRADES:")
    print()

    for trade in trades[-10:]:

        print(
            trade["time"],
            trade["signal"],
            trade["confidence"],
            round(trade["entry"], 2),
            round(trade["exit"], 2),
            trade["result"],
            "P/L:",
            round(trade["profit"], 2)
        )


def main():

    print("==================================================")
    print(BOT_NAME)
    print("==================================================")

    print(
        "Data Symbol :",
        DATA_SYMBOL
    )

    print(
        "Display     :",
        DISPLAY_SYMBOL
    )

    print(
        "Timeframe   :",
        INTERVAL
    )

    print(
        "Candles     :",
        LIMIT
    )

    print(
        "Payout      :",
        PAYOUT
    )

    print()
    print("Downloading market data...")

    df = get_data()

    print(
        "Downloaded:",
        len(df),
        "candles"
    )

    print()
    print(
        "Calculating indicators..."
    )

    df = calculate_indicators(df)

    print()
    print(
        "Running V15 backtest..."
    )

    (
        trades,
        final_balance,
        max_drawdown,
        max_loss_streak
    ) = run_backtest(df)

    analyze_results(
        trades,
        final_balance,
        max_drawdown,
        max_loss_streak
    )


if __name__ == "__main__":

    main()
