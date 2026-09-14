import requests
import pandas as pd
import numpy as np

BOT_NAME = "Smart Trading Signal Bot V15"

DATA_SYMBOL = "BTC-USD"
DISPLAY_SYMBOL = "BTCUSDT"

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

MIN_SCORE = 6

EXPIRY_CANDLES = 1

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

        end_time = oldest_time - 300

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

    df = df.sort_values("time")

    df = df.drop_duplicates(
        subset="time"
    )

    df = df.tail(
        LIMIT
    ).reset_index(
        drop=True
    )

    return df
