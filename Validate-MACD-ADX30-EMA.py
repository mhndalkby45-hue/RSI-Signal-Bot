print("TEST: Validate-MACD-ADX30-EMA.py STARTED")
import requests
import pandas as pd
import numpy as np
import time

BOT_NAME = "MACD + ADX30 + EMA50 Validation"

SYMBOL = "BTC-USD"
INTERVAL = 300

EXPIRIES = [1, 2, 3]
DAYS_LIST = [7, 14, 30]

ADX_PERIOD = 14
ADX_MIN = 30

EMA_FILTER_PERIOD = 50

STAKE = 1.0
PAYOUT = 0.80

BREAK_EVEN = 1 / (1 + PAYOUT)


def download_candles(days):
    print("DOWNLOAD FUNCTION STARTED")

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

            print(
                "Failed to download this section."
            )

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

    df = df.sort_values(
        "timestamp"
    )

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

    df = df.reset_index(
        drop=True
    )

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
    # EMA50 TREND FILTER
    # =========================

    df["ema50"] = df["close"].ewm(
        span=EMA_FILTER_PERIOD,
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


def generate_signals(
    df,
    use_adx=False,
    use_ema=False
):

    df = df.copy()

    df["signal"] = ""

    # =========================
    # MACD CROSS
    # =========================

    macd_cross_up = (
        (df["macd"] > df["macd_signal"]) &
        (
            df["macd"].shift(1)
            <=
            df["macd_signal"].shift(1)
        )
    )

    conditions
 if __name__ == "__main__":
              main()
