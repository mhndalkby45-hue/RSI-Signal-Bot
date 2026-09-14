import requests
import pandas as pd
import ta

BOT_NAME = "MACD Direction Analysis V15"

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

    url = "https://api.exchange.coinbase.com/products/BTC-USD/candles"

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
        raise ValueError("No data received.")

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

    df = df.sort_values("timestamp")
    df = df.reset_index(drop=True)
    df = df.dropna()

    print("Symbol:", DISPLAY_SYMBOL)
    print("Timeframe:", INTERVAL)
    print("Candles received:", len(df))

    if len(df) > 0:
        print("From:", df["timestamp"].iloc[0])
        print("To:", df["timestamp"].iloc[-1])

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

    df = df.dropna()
    df = df.reset_index(drop=True)

    return df


def get_signal(df, index):
    if index < 1:
        return None

    previous_macd = df.loc[index - 1, "macd"]
    previous_signal = df.loc[index - 1, "macd_signal"]

    current_macd = df.loc[index, "macd"]
    current_signal = df.loc[index, "macd_signal"]

    if (
        previous_macd <= previous_signal
        and current_macd > current_signal
    ):
        return "CALL"

    if (
        previous_macd >= previous_signal
        and current_macd < current_signal
    ):
        return "PUT"

    return None


def run_test(df, direction, expiry):
    trades = 0
    wins = 0
    losses = 0

    balance = 0.0
    peak_balance = 0.0
    max_drawdown = 0.0

    current_loss_streak = 0
    max_loss_streak = 0

    total_move = 0.0

    last_index = len(df) - expiry

    for i in range(1, last_index):

        signal = get_signal(df, i)

        if signal is None:
            continue

        if direction != "ALL" and signal != direction:
            continue

        expiry_index = i + expiry

        if expiry_index >= len(df):
            continue

        entry_price = df.loc[i, "close"]
        exit_price = df.loc[expiry_index, "close"]

        if entry_price == 0:
            continue

        trades += 1

        price_change = (
            (exit_price - entry_price)
            / entry_price
        ) * 100

        if signal == "CALL":
            win = exit_price > entry_price
        else:
            win = exit_price < entry_price

        if signal == "CALL":
            total_move += price_change
        else:
            total_move -= price_change

        if win:
            wins += 1

            balance += PAYOUT * STAKE

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
        win_rate = wins / trades * 100
    else:
        win_rate = 0

    if losses > 0:
        profit_factor = (
            wins * PAYOUT
        ) / losses
    else:
        profit_factor = float("inf")

    if trades > 0:
        average_move = total_move / trades
    else:
        average_move = 0

    return {
        "direction": direction,
        "expiry": expiry,
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "balance": balance,
        "drawdown": max_drawdown,
        "loss_streak": max_loss_streak,
        "average_move": average_move
    }


def print_result(result):
    if result["profit_factor"] == float("inf"):
        pf = "INF"
    else:
        pf = f"{result['profit_factor']:.2f}"

    print(
        result["direction"],
        "| Expiry:", result["expiry"],
        "| Trades:", result["trades"],
        "| Wins:", result["wins"],
        "| Losses:", result["losses"],
        "| WR:", f"{result['win_rate']:.2f}%",
        "| PF:", pf,
        "| Balance:", f"{result['balance']:.2f}",
        "| DD:", f"{result['drawdown']:.2f}",
        "| Streak:", result["loss_streak"],
        "| Avg Move:", f"{result['average_move']:.4f}%"
    )


def main():
    try:
        df = download_data()

        df = calculate_indicators(df)

        print()
        print(
            "Candles after indicators:",
            len(df)
        )

        if len(df) < 100:
            print("ERROR: Not enough candles.")
            return

        print()
        print("=" * 90)
        print("MACD CROSS - DIRECTION ANALYSIS")
        print("=" * 90)

        break_even = 100 / (1 + PAYOUT)

        print(
            "Break-even Win Rate:",
            f"{break_even:.2f}%"
        )

        print()
        print("-" * 90)

        results = []

        directions = [
            "ALL",
            "CALL",
            "PUT"
        ]

        for direction in directions:

            for expiry in EXPIRIES:

                result = run_test(
                    df,
                    direction,
                    expiry
                )

                results.append(result)

                print_result(result)

        print()
        print("=" * 90)
        print("BEST RESULTS")
        print("=" * 90)

        profitable_results = []

        for result in results:

            if result["balance"] > 0:
                profitable_results.append(result)

        profitable_results.sort(
            key=lambda x: x["balance"],
            reverse=True
        )

        if profitable_results:

            for result in profitable_results:

                if result["profit_factor"] == float("inf"):
                    pf = "INF"
                else:
                    pf = f"{result['profit_factor']:.2f}"

                print(
                    result["direction"],
                    "| Expiry:",
                    result["expiry"],
                    "| Trades:",
                    result["trades"],
                    "| WR:",
                    f"{result['win_rate']:.2f}%",
                    "| PF:",
                    pf,
                    "| Balance:",
                    f"{result['balance']:.2f}"
                )

        else:
            print("No profitable configuration found.")

        print()
        print("=" * 90)
        print("IMPORTANT")
        print("=" * 90)

        print(
            "CALL and PUT are analyzed separately."
        )

        print(
            "The goal is to determine whether one direction "
            "has a repeatable advantage."
        )

        print(
            "A small number of trades does not prove "
            "that a strategy is reliable."
        )

        print(
            "This is historical backtesting only."
        )

        print(
            "No result guarantees future profitability."
        )

        print()
        print("Analysis completed successfully.")

    except Exception as e:

        print()
        print("=" * 70)
        print("ERROR")
        print("=" * 70)

        print(
            type(e).__name__,
            ":",
            str(e)
        )


if __name__ == "__main__":
    main()
