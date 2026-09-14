import requests
import pandas as pd
import numpy as np

BOT_NAME = "Smart Trading Signal Bot V14"

SYMBOL = "BTCUSDT"
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


def get_data():

    url = "https://api.exchange.coinbase.com/products/BTC-USD/candles"

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
    # EMA
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

    plus_di = (
        100 *
        pd.Series(plus_dm).ewm(
            alpha=1 / ADX_PERIOD,
            min_periods=ADX_PERIOD,
            adjust=False
        ).mean() /
        atr
    )

    minus_di = (
        100 *
        pd.Series(minus_dm).ewm(
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
    # Candle confirmation
    # ==================================================

    df["bullish_candle"] = (
        df["close"] > df["open"]
    )

    df["bearish_candle"] = (
        df["close"] < df["open"]
    )

    return df

def get_signal(df, index):

    row = df.iloc[index]
    previous = df.iloc[index - 1]

    if (
        pd.isna(row["rsi"]) or
        pd.isna(row["adx"]) or
        pd.isna(row["macd_signal"])
    ):
        return "WAIT", 0

    # السوق يجب أن يكون فيه اتجاه
    if row["adx"] < ADX_MIN:
        return "WAIT", 0

    buy_score = 0
    sell_score = 0

    # ==================================================
    # TREND
    # ==================================================

    if row["ema_fast"] > row["ema_slow"]:
        buy_score += 1

    if row["ema_fast"] < row["ema_slow"]:
        sell_score += 1

    if row["close"] > row["ema_trend"]:
        buy_score += 1

    if row["close"] < row["ema_trend"]:
        sell_score += 1

    # ==================================================
    # RSI
    # ==================================================

    if 52 <= row["rsi"] <= 68:
        buy_score += 1

    if 32 <= row["rsi"] <= 48:
        sell_score += 1

    # ==================================================
    # MACD CROSS / MOMENTUM
    # ==================================================

    bullish_macd_cross = (
        previous["macd"] <= previous["macd_signal"]
        and
        row["macd"] > row["macd_signal"]
    )

    bearish_macd_cross = (
        previous["macd"] >= previous["macd_signal"]
        and
        row["macd"] < row["macd_signal"]
    )

    if bullish_macd_cross:
        buy_score += 2

    elif (
        row["macd"] > row["macd_signal"]
        and
        row["macd_hist"] > previous["macd_hist"]
    ):
        buy_score += 1

    if bearish_macd_cross:
        sell_score += 2

    elif (
        row["macd"] < row["macd_signal"]
        and
        row["macd_hist"] < previous["macd_hist"]
    ):
        sell_score += 1

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
        buy_score >= 6
        and
        buy_score > sell_score
    ):

        confidence = min(
            100,
            buy_score * 12
        )

        return "CALL", confidence

    if (
        sell_score >= 6
        and
        sell_score > buy_score
    ):

        confidence = min(
            100,
            sell_score * 12
        )

        return "PUT", confidence

    return "WAIT", 0

def run_backtest(df):

    trades = []

    current_streak = 0
    max_loss_streak = 0

    for i in range(1, len(df) - EXPIRY_CANDLES):

        signal, confidence = get_signal(
            df,
            i
        )

        if signal == "WAIT":
            continue

        entry_price = df.iloc[i]["close"]

        exit_index = i + EXPIRY_CANDLES

        exit_price = df.iloc[exit_index]["close"]

        if signal == "CALL":
            win = exit_price > entry_price

        else:
            win = exit_price < entry_price

        if win:
            result = "WIN"
            current_streak = 0

        else:
            result = "LOSS"
            current_streak += 1

            if current_streak > max_loss_streak:
                max_loss_streak = current_streak

        trades.append({
            "time": df.iloc[i]["time"],
            "signal": signal,
            "confidence": confidence,
            "entry": entry_price,
            "exit": exit_price,
            "result": result
        })

    return trades, max_loss_streak

def analyze_results(trades, max_loss_streak):

    print()
    print("==================================================")
    print("V14 BACKTEST RESULTS")
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

    losses = total_trades - wins

    win_rate = (
        wins / total_trades
    ) * 100

    avg_confidence = sum(
        trade["confidence"]
        for trade in trades
    ) / total_trades

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
        call_wins / len(call_trades) * 100
        if call_trades
        else 0
    )

    put_win_rate = (
        put_wins / len(put_trades) * 100
        if put_trades
        else 0
    )

    # ==================================================
    # PROFIT FACTOR
    # ==================================================

    profit = 0
    loss = 0

    for trade in trades:

        movement = (
            trade["exit"] -
            trade["entry"]
        )

        if trade["signal"] == "PUT":
            movement = -movement

        if movement > 0:
            profit += movement
        else:
            loss += abs(movement)

    if loss > 0:
        profit_factor = profit / loss
    else:
        profit_factor = float("inf")

    # ==================================================
    # EQUITY / DRAWDOWN
    # ==================================================

    equity = 0
    peak = 0
    max_drawdown = 0

    for trade in trades:

        movement = (
            trade["exit"] -
            trade["entry"]
        )

        if trade["signal"] == "PUT":
            movement = -movement

        equity += movement

        if equity > peak:
            peak = equity

        drawdown = peak - equity

        if drawdown > max_drawdown:
            max_drawdown = drawdown

    # ==================================================
    # PRINT RESULTS
    # ==================================================

    print("Total Trades      :", total_trades)
    print("Wins              :", wins)
    print("Losses            :", losses)

    print(
        "Win Rate          :",
        round(win_rate, 2),
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
        "Max Drawdown      :",
        round(max_drawdown, 2)
    )

    print(
        "Max Loss Streak   :",
        max_loss_streak
    )

    print()
    print("CALL TRADES       :", len(call_trades))
    print(
        "CALL Win Rate     :",
        round(call_win_rate, 2),
        "%"
    )

    print()
    print("PUT TRADES        :", len(put_trades))
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
    print("V14 EVALUATION")
    print("==================================================")

    if (
        win_rate >= 55
        and
        profit_factor > 1
    ):
        print("STATUS: PROMISING")

    elif (
        win_rate >= 50
        and
        profit_factor >= 1
    ):
        print("STATUS: NEEDS IMPROVEMENT")

    else:
        print("STATUS: NOT PROFITABLE")

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
            trade["result"]
        )


def main():

    print("==================================================")
    print(BOT_NAME)
    print("==================================================")

    print("Symbol   :", SYMBOL)
    print("Timeframe:", INTERVAL)
    print("Candles  :", LIMIT)

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
    print("Running V14 backtest...")

    trades, max_loss_streak = run_backtest(df)

    analyze_results(
        trades,
        max_loss_streak
    )


if __name__ == "__main__":
    main()
