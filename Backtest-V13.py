import requests
import pandas as pd
import numpy as np

BOT_NAME = "Smart Trading Signal Bot V13"

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

EXPIRY_CANDLES = 1


def get_data():

    url = "https://api.exchange.coinbase.com/products/BTC-USD/candles"

    all_candles = []

    end_time = int(
        pd.Timestamp.now(tz="UTC").timestamp()
    )

    # 1000 شمعة = حوالي 3.5 أيام على إطار 5 دقائق
    candles_needed = LIMIT

    while len(all_candles) < candles_needed:

        start_time = end_time - (300 * 300)

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

        end_time = oldest_time - 300

        if len(batch) < 300:
            break

    all_candles = all_candles[:candles_needed]

    columns = [
        "time",
        "low",
        "high",
        "open",
        "close",
        "volume"
    ]

    df = pd.DataFrame(
        all_candles,
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
    ).drop_duplicates(
        subset="time"
    )

    df = df.tail(LIMIT).reset_index(
        drop=True
    )

    return df

def calculate_indicators(df):

    # EMA
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

    # RSI
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

    # MACD
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

    return df

def get_signal(df, index):

    row = df.iloc[index]
    previous = df.iloc[index - 1]

    if pd.isna(row["rsi"]):
        return "WAIT", 0

    buy_score = 0
    sell_score = 0

    # EMA direction
    if row["ema_fast"] > row["ema_slow"]:
        buy_score += 1

    if row["ema_fast"] < row["ema_slow"]:
        sell_score += 1

    # Trend filter
    if row["close"] > row["ema_trend"]:
        buy_score += 1

    if row["close"] < row["ema_trend"]:
        sell_score += 1

    # RSI
    if 50 <= row["rsi"] <= 70:
        buy_score += 1

    if 30 <= row["rsi"] <= 50:
        sell_score += 1

    # MACD
    if row["macd"] > row["macd_signal"]:
        buy_score += 1

    if row["macd"] < row["macd_signal"]:
        sell_score += 1

    # MACD momentum
    if row["macd_hist"] > previous["macd_hist"]:
        buy_score += 1

    if row["macd_hist"] < previous["macd_hist"]:
        sell_score += 1

    # CALL
    if buy_score >= 4 and buy_score > sell_score:

        confidence = buy_score * 20

        return "CALL", confidence

    # PUT
    if sell_score >= 4 and sell_score > buy_score:

        confidence = sell_score * 20

        return "PUT", confidence

    return "WAIT", 0

def run_backtest(df):

    trades = []

    start_index = max(
        EMA_TREND,
        MACD_SLOW,
        RSI_PERIOD
    ) + 2

    end_index = (
        len(df) -
        EXPIRY_CANDLES
    )

    for i in range(
        start_index,
        end_index
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

        exit_price = df.iloc[
            exit_index
        ]["close"]

        if signal == "CALL":

            if exit_price > entry_price:
                result = "WIN"
            else:
                result = "LOSS"

        else:

            if exit_price < entry_price:
                result = "WIN"
            else:
                result = "LOSS"

        trades.append({
            "time": df.iloc[i]["time"],
            "signal": signal,
            "confidence": confidence,
            "entry": entry_price,
            "exit": exit_price,
            "result": result
        })

    return pd.DataFrame(trades)

def analyze_results(trades):

    print("\n")
    print("=" * 55)
    print("BACKTEST RESULTS")
    print("=" * 55)

    if trades.empty:
        print("No trades found.")
        return

    total = len(trades)

    wins = len(
        trades[
            trades["result"] == "WIN"
        ]
    )

    losses = len(
        trades[
            trades["result"] == "LOSS"
        ]
    )

    win_rate = (
        wins / total
    ) * 100

    print("Total Trades :", total)
    print("Wins         :", wins)
    print("Losses       :", losses)
    print(
        "Win Rate     :",
        f"{win_rate:.2f}%"
    )

    print(
        "Avg Confidence :",
        f"{trades['confidence'].mean():.2f}%"
    )

    call_trades = trades[
        trades["signal"] == "CALL"
    ]

    put_trades = trades[
        trades["signal"] == "PUT"
    ]

    if len(call_trades) > 0:

        call_wins = len(
            call_trades[
                call_trades["result"] == "WIN"
            ]
        )

        call_rate = (
            call_wins /
            len(call_trades)
        ) * 100

        print(
            "CALL Trades  :",
            len(call_trades)
        )

        print(
            "CALL Win Rate:",
            f"{call_rate:.2f}%"
        )

    if len(put_trades) > 0:

        put_wins = len(
            put_trades[
                put_trades["result"] == "WIN"
            ]
        )

        put_rate = (
            put_wins /
            len(put_trades)
        ) * 100

        print(
            "PUT Trades   :",
            len(put_trades)
        )

        print(
            "PUT Win Rate :",
            f"{put_rate:.2f}%"
        )

    max_loss_streak = 0
    current_loss_streak = 0

    for result in trades["result"]:

        if result == "LOSS":

            current_loss_streak += 1

            max_loss_streak = max(
                max_loss_streak,
                current_loss_streak
            )

        else:

            current_loss_streak = 0

    print(
        "Max Loss Streak:",
        max_loss_streak
    )

    print("\n")
    print("=" * 55)
    print("V13 EVALUATION")
    print("=" * 55)

    if win_rate >= 65:
        print("STATUS: VERY STRONG")

    elif win_rate >= 58:
        print("STATUS: PROMISING")

    elif win_rate >= 52:
        print("STATUS: WEAK EDGE")

    else:
        print("STATUS: NOT PROFITABLE")

    print("=" * 55)


def main():

    print("=" * 55)
    print(BOT_NAME)
    print("=" * 55)

    print("Symbol   :", SYMBOL)
    print("Timeframe:", INTERVAL)
    print("Candles  :", LIMIT)

    try:

        print("\nDownloading market data...")

        df = get_data()

        print(
            "Downloaded:",
            len(df),
            "candles"
        )

        print(
            "\nCalculating indicators..."
        )

        df = calculate_indicators(df)

        print(
            "Running backtest..."
        )

        trades = run_backtest(df)

        analyze_results(trades)

        if not trades.empty:

            print("\n")
            print("=" * 55)
            print("LAST 10 TRADES")
            print("=" * 55)

            columns = [
                "time",
                "signal",
                "confidence",
                "entry",
                "exit",
                "result"
            ]

            print(
                trades[
                    columns
                ].tail(10).to_string(
                    index=False
                )
            )

    except requests.exceptions.RequestException as error:

        print(
            "\nDATA ERROR:",
            error
        )

    except Exception as error:

        print(
            "\nERROR:",
            type(error).__name__,
            "-",
            error
        )


if __name__ == "__main__":
    main()
