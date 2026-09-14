import requests
import pandas as pd
import ta
from datetime import datetime

BOT_NAME = "MACD Validation V15"

SYMBOL = "BTC-USD"
DISPLAY_SYMBOL = "BTCUSDT"
INTERVAL = "5m"
LIMIT = 1000

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

STAKE = 1.0
PAYOUT = 0.80

EXPIRIES = [1, 2, 3]


def download_data():
    print("=" * 70)
    print(BOT_NAME)
    print("=" * 70)
    print("Downloading BTC data...")

    url = f"https://api.exchange.coinbase.com/products/{SYMBOL}/candles"

    params = {
        "granularity": 300,
        "limit": LIMIT
    }

    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if not data:
        raise ValueError("No data received from Coinbase.")

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

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df.sort_values("timestamp")
    df = df.reset_index(drop=True)

    df = df.dropna()

    print("Symbol:", DISPLAY_SYMBOL)
    print("Timeframe:", INTERVAL)
    print("Candles received:", len(df))

    if len(df) > 0:
        print(
            "From:",
            df["timestamp"].iloc[0]
        )
        print(
            "To:",
            df["timestamp"].iloc[-1]
        )

    return df


def calculate_indicators(df):
    df = df.copy()

    macd = ta.trend.MACD(
        close=df["close"],
        window_fast=MACD_FAST,
        window_slow=MACD_SLOW,
        window_sign=MACD_SIGNAL
    )

    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    df = df.dropna().reset_index(drop=True)

    return df


def get_signal(df, index):
    if index < 1:
        return None

    current_macd = df.loc[index, "macd"]
    current_signal = df.loc[index, "macd_signal"]

    previous_macd = df.loc[index - 1, "macd"]
    previous_signal = df.loc[index - 1, "macd_signal"]

    # Bullish MACD crossover
    if (
        previous_macd <= previous_signal
        and current_macd > current_signal
    ):
        return "CALL"

    # Bearish MACD crossover
    if (
        previous_macd >= previous_signal
        and current_macd < current_signal
    ):
        return "PUT"

    return None


def calculate_profit(wins, losses):
    return (
        wins * PAYOUT * STAKE
        - losses * STAKE
    )


def calculate_profit_factor(wins, losses):
    if losses == 0:
        return float("inf")

    gross_profit = wins * PAYOUT * STAKE
    gross_loss = losses * STAKE

    return gross_profit / gross_loss


def backtest_segment(df, start_index, end_index, expiry):
    trades = 0
    wins = 0
    losses = 0

    calls = 0
    call_wins = 0

    puts = 0
    put_wins = 0

    balance = 0.0
    peak_balance = 0.0
    max_drawdown = 0.0

    current_loss_streak = 0
    max_loss_streak = 0

    start_trade_index = start_index
    final_trade_index = end_index - expiry

    if final_trade_index <= start_trade_index:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "profit_factor": 0,
            "balance": 0,
            "drawdown": 0,
            "loss_streak": 0,
            "calls": 0,
            "call_win_rate": 0,
            "puts": 0,
            "put_win_rate": 0
        }

    for i in range(
        start_trade_index,
        final_trade_index
    ):

        signal = get_signal(df, i)

        if signal is None:
            continue

        expiry_index = i + expiry

        if expiry_index >= end_index:
            continue

        entry_price = df.loc[i, "close"]
        exit_price = df.loc[expiry_index, "close"]

        trades += 1

        if signal == "CALL":
            calls += 1

            if exit_price > entry_price:
                win = True
            else:
                win = False

        else:
            puts += 1

            if exit_price < entry_price:
                win = True
            else:
                win = False

        if win:
            wins += 1

            balance += PAYOUT * STAKE

            current_loss_streak = 0

            if signal == "CALL":
                call_wins += 1
            else:
                put_wins += 1

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
        win_rate = (wins / trades) * 100
    else:
        win_rate = 0

    if calls > 0:
        call_win_rate = (call_wins / calls) * 100
    else:
        call_win_rate = 0

    if puts > 0:
        put_win_rate = (put_wins / puts) * 100
    else:
        put_win_rate = 0

    profit_factor = calculate_profit_factor(
        wins,
        losses
    )

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "balance": balance,
        "drawdown": max_drawdown,
        "loss_streak": max_loss_streak,
        "calls": calls,
        "call_win_rate": call_win_rate,
        "puts": puts,
        "put_win_rate": put_win_rate
    }


def print_result(
    segment_name,
    expiry,
    result
):
    pf = result["profit_factor"]

    if pf == float("inf"):
        pf_text = "INF"
    else:
        pf_text = f"{pf:.2f}"

    print(
        f"{segment_name:<12}"
        f"{expiry:<8}"
        f"{result['trades']:<8}"
        f"{result['wins']:<7}"
        f"{result['losses']:<
