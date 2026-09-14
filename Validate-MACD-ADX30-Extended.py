import requests
import pandas as pd
import numpy as np
import time

BOT_NAME = "MACD + ADX30 Extended Validation"

SYMBOL = "BTC-USD"
INTERVAL = 300

EXPIRIES = [1, 2, 3]
DAYS_LIST = [7, 14, 30]

ADX_PERIOD = 14
ADX_MIN = 30

STAKE = 1.0
PAYOUT = 0.80

BREAK_EVEN = 1 / (1 + PAYOUT)


def download_candles(days):
    print("")
    print("=" * 70)
    print("Downloading", days, "days of data...")
    print("=" * 70)

    end_time = int(time.time())
    start_time = end_time - (days * 24 * 60 * 60)

    all_candles = []

    current_end = end_time

    while current_end > start_time:

        current_start = max(
            start_time,
            current_end - (290 * INTERVAL)
        )

        url = (
            "https://api.exchange.coinbase.com/products/"
            + SYMBOL
            + "/candles"
        )

        params = {
            "granularity": INTERVAL,
            "start": current_start,
            "end": current_end
        }

        success = False

        for attempt in range(3):

            try:
                response = requests.get(
                    url,
                    params=params,
                    timeout=20
                )

                response.raise_for_status()

                data = response.json()

                if isinstance(data, list) and len(data) > 0:
                    all_candles.extend(data)
                    success = True
                    break

            except Exception as e:
                print(
                    "Download error:",
                    str(e),
                    "attempt",
                    attempt + 1
                )

                time.sleep(1)

        if not success:
            print("Failed to download this section.")
            break

        current_end = current_start

        print(
            "Downloaded candles:",
            len(all_candles)
        )

        time.sleep(0.3)

    if len(all_candles) == 0:
        return pd.DataFrame()

    df = pd.DataFrame(
        all_candles,
        columns=[
            "timestamp",
            "low",
            "high",
            "open",
            "close",
            "volume"
        ]
    )

    df = df.drop_duplicates(
        subset=["timestamp"]
    )

    df = df.sort_values("timestamp")

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        unit="s",
        utc=True
    )

    for col in [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.reset_index(drop=True)

    return df


def calculate_indicators(df):

    df = df.copy()

    # =========================
    # MACD
    # =========================

    ema12 = df["close"].ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = df["close"].ewm(
        span=26,
        adjust=False
    ).mean()

    df["macd"] = ema12 - ema26

    df["macd_signal"] = df["macd"].ewm(
        span=9,
        adjust=False
    ).mean()

    # =========================
    # ADX / DI
    # =========================

    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    up_move = high - prev_high
    down_move = prev_low - low

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

    tr_series = pd.Series(
        tr,
        index=df.index
    )

    plus_dm = pd.Series(
        plus_dm,
        index=df.index
    )

    minus_dm = pd.Series(
        minus_dm,
        index=df.index
    )

    atr = tr_series.ewm(
        alpha=1 / ADX_PERIOD,
        adjust=False
    ).mean()

    plus_di = (
        100 *
        plus_dm.ewm(
            alpha=1 / ADX_PERIOD,
            adjust=False
        ).mean()
        / atr
    )

    minus_di = (
        100 *
        minus_dm.ewm(
            alpha=1 / ADX_PERIOD,
            adjust=False
        ).mean()
        / atr
    )

    dx = (
        100 *
        (plus_di - minus_di).abs()
        / (plus_di + minus_di)
    )

    adx = dx.ewm(
        alpha=1 / ADX_PERIOD,
        adjust=False
    ).mean()

    df["plus_di"] = plus_di
    df["minus_di"] = minus_di
    df["adx"] = adx

    return df


def generate_signals(df, use_adx):

    df = df.copy()

    df["signal"] = ""

    macd_cross_up = (
        (df["macd"] > df["macd_signal"]) &
        (
            df["macd"].shift(1)
            <=
            df["macd_signal"].shift(1)
        )
    )

    if use_adx:

        df.loc[
            macd_cross_up &
            (df["adx"] >= ADX_MIN),
            "signal"
        ] = "CALL"

    else:

        df.loc[
            macd_cross_up,
            "signal"
        ] = "CALL"

    return df


def backtest(df, expiry):

    trades = []

    for i in range(len(df) - expiry):

        if df.iloc[i]["signal"] != "CALL":
            continue

        entry = df.iloc[i]["close"]
        exit_price = df.iloc[i + expiry]["close"]

        if exit_price > entry:
            result = "WIN"
            profit = STAKE * PAYOUT
        else:
            result = "LOSS"
            profit = -STAKE

        move = (
            (exit_price - entry)
            / entry
        ) * 100

        trades.append(
            {
                "index": i,
                "result": result,
                "profit": profit,
                "move": move
            }
        )

    if len(trades) == 0:
        return None

    wins = sum(
        1 for x in trades
        if x["result"] == "WIN"
    )

    losses = sum(
        1 for x in trades
        if x["result"] == "LOSS"
    )

    total = wins + losses

    win_rate = wins / total

    gross_profit = (
        wins * STAKE * PAYOUT
    )

    gross_loss = losses * STAKE

    if gross_loss > 0:
        profit_factor = (
            gross_profit / gross_loss
        )
    else:
        profit_factor = float("inf")

    balance = sum(
        x["profit"] for x in trades
    )

    equity = 0
    peak = 0
    max_dd = 0

    for trade in trades:

        equity += trade["profit"]

        if equity > peak:
            peak = equity

        dd = peak - equity

        if dd > max_dd:
            max_dd = dd

    max_streak = 0
    current_streak = 0

    for trade in trades:

        if trade["result"] == "LOSS":

            current_streak += 1

            if current_streak > max_streak:
                max_streak = current_streak

        else:
            current_streak = 0

    avg_move = np.mean(
        [x["move"] for x in trades]
    )

    return {
        "trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "balance": balance,
        "max_dd": max_dd,
        "max_streak": max_streak,
        "avg_move": avg_move
    }


def print_result(name, expiry, result):

    if result is None:

        print(
            name,
            "| Expiry",
            expiry,
            "| NO TRADES"
        )

        return

    pf = result["profit_factor"]

    if np.isinf(pf):
        pf_text = "INF"
    else:
        pf_text = "{:.2f}".format(pf)

    print(
        "{:<25}".format(name),
        "| Expiry", expiry,
        "| Trades", result["trades"],
        "| WR {:.2f}%".format(
            result["win_rate"] * 100
        ),
        "| PF", pf_text,
        "| Balance {:+.2f}".format(
            result["balance"]
        ),
        "| DD {:.2f}".format(
            result["max_dd"]
        ),
        "| Streak",
        result["max_streak"]
    )


def print_parts(df, expiry):

    total = len(df)

    part_size = total // 4

    print("")
    print("Chronological Parts:")

    for part in range(4):

        start = part * part_size

        if part == 3:
            end = total
        else:
            end = (part + 1) * part_size

        part_df = df.iloc[start:end].copy()

        result = backtest(
            part_df,
            expiry
        )

        if result is None:

            print(
                "P{}".format(part + 1),
                "| NO TRADES"
            )

        else:

            print(
                "P{}".format(part + 1),
                "| Trades",
                result["trades"],
                "| WR {:.2f}%".format(
                    result["win_rate"] * 100
                ),
                "| PF {:.2f}".format(
                    result["profit_factor"]
                ),
                "| Balance {:+.2f}".format(
                    result["balance"]
                ),
                "| DD {:.2f}".format(
                    result["max_dd"]
                )
            )


def run_strategy(
    df,
    strategy_name,
    use_adx
):

    strategy_df = generate_signals(
        df,
        use_adx
    )

    print("")
    print("")
    print("#" * 70)
    print(strategy_name)
    print("#" * 70)

    for expiry in EXPIRIES:

        result = backtest(
            strategy_df,
            expiry
        )

        print_result(
            strategy_name,
            expiry,
            result
        )

        if result is not None:

            print_parts(
                strategy_df,
                expiry
            )


def main():

    print("")
    print("=" * 70)
    print(BOT_NAME)
    print("=" * 70)

    print(
        "Break-even WR:",
        "{:.2f}%".format(
            BREAK_EVEN * 100
        )
    )

    print(
        "Testing:",
        "MACD CALL vs MACD CALL + ADX >= 30"
    )

    for days in DAYS_LIST:

        print("")
        print("")
        print("=" * 70)
        print(
            "TEST PERIOD:",
            days,
            "DAYS"
        )
        print("=" * 70)

        df = download_candles(days)

        if df.empty:

            print(
                "No data for",
                days,
                "days."
            )

            continue

        print("")
        print(
            "Candles downloaded:",
            len(df)
        )

        print(
            "Start:",
            df["timestamp"].iloc[0]
        )

        print(
            "End:",
            df["timestamp"].iloc[-1]
        )

        df = calculate_indicators(df)

        df = df.dropna().reset_index(
            drop=True
        )

        print(
            "Candles after indicators:",
            len(df)
        )

        run_strategy(
            df,
            "MACD CALL ONLY",
            False
        )

        run_strategy(
            df,
            "MACD CALL + ADX30",
            True
        )

    print("")
    print("=" * 70)
    print("VALIDATION COMPLETE")
    print("=" * 70)

    print("")
    print(
        "Important:",
        "This is historical backtesting only."
    )

    print(
        "A positive result does not guarantee",
        "future profitability."
    )


if __name__ == "__main__":
    main()
