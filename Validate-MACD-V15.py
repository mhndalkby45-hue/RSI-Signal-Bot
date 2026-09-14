import requests
import pandas as pd
import ta

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

    last_index = end_index - expiry

    for i in range(start_index, last_index):

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

            win = exit_price > entry_price

            if win:
                call_wins += 1

        else:
            puts += 1

            win = exit_price < entry_price

            if win:
                put_wins += 1

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

    if calls > 0:
        call_win_rate = call_wins / calls * 100
    else:
        call_win_rate = 0

    if puts > 0:
        put_win_rate = put_wins / puts * 100
    else:
        put_win_rate = 0

    if losses > 0:
        profit_factor = (
            wins * PAYOUT
        ) / losses
    else:
        profit_factor = float("inf")

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


def print_result(segment, expiry, result):
    if result["profit_factor"] == float("inf"):
        pf = "INF"
    else:
        pf = f"{result['profit_factor']:.2f}"

    print(
        segment,
        "| Expiry:", expiry,
        "| Trades:", result["trades"],
        "| Wins:", result["wins"],
        "| Losses:", result["losses"],
        "| WR:", f"{result['win_rate']:.2f}%",
        "| PF:", pf,
        "| Balance:", f"{result['balance']:.2f}",
        "| DD:", f"{result['drawdown']:.2f}",
        "| Streak:", result["loss_streak"],
        "| CALL:", result["calls"],
        "| CALL WR:", f"{result['call_win_rate']:.2f}%",
        "| PUT:", result["puts"],
        "| PUT WR:", f"{result['put_win_rate']:.2f}%"
    )


def main():
    try:
        df = download_data()

        df = calculate_indicators(df)

        total = len(df)

        print()
        print("Candles after indicators:", total)

        if total < 100:
            print("ERROR: Not enough candles.")
            return

        break_even = 100 / (1 + PAYOUT)

        print()
        print("=" * 70)
        print("MACD CROSS VALIDATION")
        print("=" * 70)

        segment_size = total // 4

        segments = [
            ("PART 1", 0, segment_size),
            ("PART 2", segment_size, segment_size * 2),
            ("PART 3", segment_size * 2, segment_size * 3),
            ("PART 4", segment_size * 3, total),
            ("FULL", 0, total)
        ]

        all_results = []

        for segment_name, start, end in segments:

            for expiry in EXPIRIES:

                result = backtest_segment(
                    df,
                    start,
                    end,
                    expiry
                )

                print_result(
                    segment_name,
                    expiry,
                    result
                )

                all_results.append({
                    "segment": segment_name,
                    "expiry": expiry,
                    **result
                })

        print()
        print("=" * 70)
        print("BREAK-EVEN")
        print("=" * 70)

        print(
            "Payout:",
            PAYOUT
        )

        print(
            "Required Win Rate:",
            f"{break_even:.2f}%"
        )

        print()
        print("=" * 70)
        print("FULL SAMPLE - BEST RESULTS")
        print("=" * 70)

        full_results = []

        for result in all_results:
            if result["segment"] == "FULL":
                full_results.append(result)

        full_results.sort(
            key=lambda x: x["balance"],
            reverse=True
        )

        for result in full_results:

            if result["profit_factor"] == float("inf"):
                pf = "INF"
            else:
                pf = f"{result['profit_factor']:.2f}"

            print(
                "Expiry",
                result["expiry"],
                "| Trades:",
                result["trades"],
                "| Wins:",
                result["wins"],
                "| Losses:",
                result["losses"],
                "| WR:",
                f"{result['win_rate']:.2f}%",
                "| PF:",
                pf,
                "| Balance:",
                f"{result['balance']:.2f}",
                "| DD:",
                f"{result['drawdown']:.2f}"
            )

        print()
        print("=" * 70)
        print("WHAT WE ARE LOOKING FOR")
        print("=" * 70)

        print(
            "1. Win rate above",
            f"{break_even:.2f}%",
            "is required to overcome the payout."
        )

        print(
            "2. We want the result to remain positive "
            "in more than one time segment."
        )

        print(
            "3. We will compare CALL and PUT separately."
        )

        print(
            "4. A small number of trades does not prove "
            "that the strategy is reliable."
        )

        print(
            "5. This is historical testing only and "
            "does not guarantee future profit."
        )

        print()
        print("Validation completed successfully.")

    except Exception as e:
        print()
        print("=" * 70)
        print("ERROR")
        print("=" * 70)
        print(type(e).__name__, ":", str(e))


if __name__ == "__main__":
    main()
