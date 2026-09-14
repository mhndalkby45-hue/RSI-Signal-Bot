import requests
import pandas as pd
import ta


BOT_NAME = "MACD CALL Optimization V15"

SYMBOL = "BTC-USD"
DISPLAY_SYMBOL = "BTCUSDT"
INTERVAL = "5m"
LIMIT = 1000

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 50

RSI_PERIOD = 14

ADX_PERIOD = 14
ADX_MIN = 20

STAKE = 1.0
PAYOUT = 0.80

EXPIRIES = [1, 2, 3]


def download_data():

    print("=" * 75)
    print(BOT_NAME)
    print("=" * 75)

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

    ema_fast = ta.trend.EMAIndicator(
        close=df["close"],
        window=EMA_FAST
    )

    ema_slow = ta.trend.EMAIndicator(
        close=df["close"],
        window=EMA_SLOW
    )

    ema_trend = ta.trend.EMAIndicator(
        close=df["close"],
        window=EMA_TREND
    )

    df["ema_fast"] = ema_fast.ema_indicator()
    df["ema_slow"] = ema_slow.ema_indicator()
    df["ema_trend"] = ema_trend.ema_indicator()

    rsi = ta.momentum.RSIIndicator(
        close=df["close"],
        window=RSI_PERIOD
    )

    df["rsi"] = rsi.rsi()

    macd = ta.trend.MACD(
        close=df["close"],
        window_fast=MACD_FAST,
        window_slow=MACD_SLOW,
        window_sign=MACD_SIGNAL
    )

    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    adx = ta.trend.ADXIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=ADX_PERIOD
    )

    df["adx"] = adx.adx()
    df["plus_di"] = adx.adx_pos()
    df["minus_di"] = adx.adx_neg()

    df = df.dropna()
    df = df.reset_index(drop=True)

    return df


def macd_call_cross(df, index):

    if index < 1:
        return False

    previous_macd = df.loc[index - 1, "macd"]
    previous_signal = df.loc[index - 1, "macd_signal"]

    current_macd = df.loc[index, "macd"]
    current_signal = df.loc[index, "macd_signal"]

    return (
        previous_macd <= previous_signal
        and current_macd > current_signal
    )


def condition_passes(df, index, condition):

    if condition == "MACD ONLY":

        return True

    if condition == "MACD + EMA CROSS":

        return (
            df.loc[index, "ema_fast"]
            > df.loc[index, "ema_slow"]
        )

    if condition == "MACD + EMA50":

        return (
            df.loc[index, "close"]
            > df.loc[index, "ema_trend"]
        )

    if condition == "MACD + RSI":

        return (
            df.loc[index, "rsi"] > 50
            and df.loc[index, "rsi"] < 70
        )

    if condition == "MACD + ADX":

        return (
            df.loc[index, "adx"] >= ADX_MIN
            and df.loc[index, "plus_di"]
            > df.loc[index, "minus_di"]
        )

    if condition == "MACD + EMA CROSS + EMA50":

        return (
            df.loc[index, "ema_fast"]
            > df.loc[index, "ema_slow"]
            and
            df.loc[index, "close"]
            > df.loc[index, "ema_trend"]
        )

    if condition == "MACD + EMA CROSS + RSI":

        return (
            df.loc[index, "ema_fast"]
            > df.loc[index, "ema_slow"]
            and
            df.loc[index, "rsi"] > 50
            and
            df.loc[index, "rsi"] < 70
        )

    if condition == "MACD + EMA50 + RSI":

        return (
            df.loc[index, "close"]
            > df.loc[index, "ema_trend"]
            and
            df.loc[index, "rsi"] > 50
            and
            df.loc[index, "rsi"] < 70
        )

    if condition == "MACD + EMA + RSI + ADX":

        return (
            df.loc[index, "ema_fast"]
            > df.loc[index, "ema_slow"]
            and
            df.loc[index, "close"]
            > df.loc[index, "ema_trend"]
            and
            df.loc[index, "rsi"] > 50
            and
            df.loc[index, "rsi"] < 70
            and
            df.loc[index, "adx"] >= ADX_MIN
            and
            df.loc[index, "plus_di"]
            > df.loc[index, "minus_di"]
        )

    return False


def run_backtest(df, condition, expiry):

    trades = 0
    wins = 0
    losses = 0

    balance = 0.0

    peak_balance = 0.0
    max_drawdown = 0.0

    current_loss_streak = 0
    max_loss_streak = 0

    last_index = len(df) - expiry

    for i in range(1, last_index):

        if not macd_call_cross(df, i):
            continue

        if not condition_passes(
            df,
            i,
            condition
        ):
            continue

        expiry_index = i + expiry

        if expiry_index >= len(df):
            continue

        entry_price = df.loc[i, "close"]
        exit_price = df.loc[expiry_index, "close"]

        trades += 1

        win = exit_price > entry_price

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

        win_rate = (
            wins / trades
        ) * 100

    else:

        win_rate = 0

    if losses > 0:

        profit_factor = (
            wins * PAYOUT
        ) / losses

    else:

        profit_factor = float("inf")

    return {
        "condition": condition,
        "expiry": expiry,
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "balance": balance,
        "drawdown": max_drawdown,
        "loss_streak": max_loss_streak
    }


def print_result(result):

    if result["profit_factor"] == float("inf"):

        pf = "INF"

    else:

        pf = f"{result['profit_factor']:.2f}"

    print(
        result["condition"],
        "| Expiry:",
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
        f"{result['drawdown']:.2f}",
        "| Streak:",
        result["loss_streak"]
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

            print(
                "ERROR: Not enough candles."
            )

            return

        print()
        print("=" * 110)
        print("MACD CALL FILTER OPTIMIZATION")
        print("=" * 110)

        print(
            "Break-even Win Rate:",
            "55.56%"
        )

        print()

        conditions = [
            "MACD ONLY",
            "MACD + EMA CROSS",
            "MACD + EMA50",
            "MACD + RSI",
            "MACD + ADX",
            "MACD + EMA CROSS + EMA50",
            "MACD + EMA CROSS + RSI",
            "MACD + EMA50 + RSI",
            "MACD + EMA + RSI + ADX"
        ]

        results = []

        for condition in conditions:

            for expiry in EXPIRIES:

                result = run_backtest(
                    df,
                    condition,
                    expiry
                )

                results.append(result)

                print_result(result)

        print()
        print("=" * 110)
        print("BEST RESULTS")
        print("=" * 110)

        results_sorted = sorted(
            results,
            key=lambda x: x["balance"],
            reverse=True
        )

        for result in results_sorted[:10]:

            if result["profit_factor"] == float("inf"):

                pf = "INF"

            else:

                pf = f"{result['profit_factor']:.2f}"

            print(
                result["condition"],
                "| Expiry:",
                result["expiry"],
                "| Trades:",
                result["trades"],
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
        print("=" * 110)
        print("ANALYSIS RULE")
        print("=" * 110)

        print(
            "We are NOT selecting a strategy only because "
            "it has the highest win rate."
        )

        print(
            "We also need enough trades and reasonable "
            "drawdown."
        )

        print(
            "The current MACD CALL baseline has only "
            "13 trades."
        )

        print(
            "This remains historical research and does "
            "not guarantee future profitability."
        )

        print()
        print(
            "Optimization completed successfully."
        )

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
