import requests
import pandas as pd
import time
from datetime import datetime, timezone

from ta.trend import MACD, EMAIndicator
from ta.momentum import RSIIndicator


# ============================================================
# SMART TRADING SIGNAL BOT
# ============================================================

BOT_NAME = "Smart Trading Signal Bot"

SYMBOL = "BTC-USD"
GRANULARITY = 300       # 5 minutes

# ============================================================
# INDICATOR SETTINGS
# ============================================================

RSI_PERIOD = 14

EMA_PERIOD = 50

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

POLL_SECONDS = 20


# ============================================================
# DOWNLOAD CANDLES
# ============================================================

def get_candles():

    url = (
        "https://api.exchange.coinbase.com/"
        "products/BTC-USD/candles"
    )

    params = {
        "granularity": GRANULARITY,
        "limit": 300
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        if not data:
            return None

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
            unit="s",
            utc=True
        )

        df = df.sort_values("timestamp")
        df = df.drop_duplicates("timestamp")

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

        df = df.dropna()

        return df

    except Exception as e:

        print()
        print("ERROR downloading market data:")
        print(str(e))
        return None


# ============================================================
# CALCULATE INDICATORS
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    # --------------------------------------------------------
    # RSI 14
    # --------------------------------------------------------

    rsi = RSIIndicator(
        close=df["close"],
        window=RSI_PERIOD
    )

    df["rsi"] = rsi.rsi()

    # --------------------------------------------------------
    # MACD 12 / 26 / 9
    # --------------------------------------------------------

    macd = MACD(
        close=df["close"],
        window_fast=MACD_FAST,
        window_slow=MACD_SLOW,
        window_sign=MACD_SIGNAL
    )

    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_histogram"] = macd.macd_diff()

    # --------------------------------------------------------
    # EMA 50
    # --------------------------------------------------------

    ema = EMAIndicator(
        close=df["close"],
        window=EMA_PERIOD
    )

    df["ema50"] = ema.ema_indicator()

    return df


# ============================================================
# SIGNAL ANALYSIS
# ============================================================

def analyze_signal(df):

    if len(df) < 100:
        return None

    # --------------------------------------------------------
    # Last completed candle
    # --------------------------------------------------------

    current = df.iloc[-2]
    previous = df.iloc[-3]

    required_columns = [
        "rsi",
        "macd",
        "macd_signal",
        "ema50"
    ]

    for column in required_columns:

        if pd.isna(current[column]):
            return None

        if pd.isna(previous[column]):
            return None

    # ========================================================
    # MACD CROSS
    # ========================================================

    bullish_cross = (
        current["macd"] > current["macd_signal"]
        and
        previous["macd"] <= previous["macd_signal"]
    )

    bearish_cross = (
        current["macd"] < current["macd_signal"]
        and
        previous["macd"] >= previous["macd_signal"]
    )

    # ========================================================
    # CALL CONDITIONS
    # ========================================================

    call_conditions = (
        current["close"] > current["ema50"]
        and
        current["rsi"] > 50
        and
        current["rsi"] < 70
        and
        bullish_cross
    )

    if call_conditions:

        return {
            "direction": "CALL",
            "time": current["timestamp"],
            "price": float(current["close"]),
            "rsi": float(current["rsi"]),
            "macd": float(current["macd"]),
            "macd_signal": float(
                current["macd_signal"]
            ),
            "macd_histogram": float(
                current["macd_histogram"]
            ),
            "ema50": float(current["ema50"])
        }

    # ========================================================
    # PUT CONDITIONS
    # ========================================================

    put_conditions = (
        current["close"] < current["ema50"]
        and
        current["rsi"] < 50
        and
        current["rsi"] > 30
        and
        bearish_cross
    )

    if put_conditions:

        return {
            "direction": "PUT",
            "time": current["timestamp"],
            "price": float(current["close"]),
            "rsi": float(current["rsi"]),
            "macd": float(current["macd"]),
            "macd_signal": float(
                current["macd_signal"]
            ),
            "macd_histogram": float(
                current["macd_histogram"]
            ),
            "ema50": float(current["ema50"])
        }

    return None


# ============================================================
# CONFIDENCE
# ============================================================

def calculate_confidence(signal):

    score = 0

    # --------------------------------------------------------
    # EMA confirmation
    # --------------------------------------------------------

    if signal["direction"] == "CALL":

        if signal["price"] > signal["ema50"]:
            score += 30

    else:

        if signal["price"] < signal["ema50"]:
            score += 30

    # --------------------------------------------------------
    # RSI confirmation
    # --------------------------------------------------------

    rsi = signal["rsi"]

    if signal["direction"] == "CALL":

        if 55 <= rsi < 65:
            score += 30

        elif 50 < rsi < 70:
            score += 25

    else:

        if 35 < rsi <= 45:
            score += 30

        elif 30 < rsi < 50:
            score += 25

    # --------------------------------------------------------
    # MACD confirmation
    # --------------------------------------------------------

    if signal["direction"] == "CALL":

        if signal["macd"] > signal["macd_signal"]:
            score += 40

    else:

        if signal["macd"] < signal["macd_signal"]:
            score += 40

    return min(score, 100)


# ============================================================
# PRINT SIGNAL
# ============================================================

def print_signal(signal):

    confidence = calculate_confidence(signal)

    print()
    print("=" * 70)
    print("🚨 VALID SIGNAL")
    print("=" * 70)

    print(
        "Signal time:",
        signal["time"].strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )

    print(
        "Entry:",
        "NEXT 5-MINUTE CANDLE"
    )

    print()

    print(
        "Direction:",
        signal["direction"]
    )

    print(
        "Price:",
        f"{signal['price']:.2f}"
    )

    print()

    print(
        "RSI:",
        f"{signal['rsi']:.2f}"
    )

    print(
        "MACD:",
        f"{signal['macd']:.6f}"
    )

    print(
        "MACD Signal:",
        f"{signal['macd_signal']:.6f}"
    )

    print(
        "MACD Histogram:",
        f"{signal['macd_histogram']:.6f}"
    )

    print(
        "EMA50:",
        f"{signal['ema50']:.2f}"
    )

    print()

    print(
        "Confidence:",
        f"{confidence}%"
    )

    print()

    print(
        "Timeframe: 5 minutes"
    )

    print(
        "Suggested expiry: 10 minutes"
    )

    print()

    print(
        "⚠️ MANUAL ENTRY"
    )

    print(
        "The bot does NOT execute trades."
    )

    print("=" * 70)
    print()


# ============================================================
# STATUS
# ============================================================

def print_status(df):

    current = df.iloc[-2]

    now = datetime.now(timezone.utc)

    if current["close"] > current["ema50"]:
        trend = "ABOVE EMA50"
    else:
        trend = "BELOW EMA50"

    if current["macd"] > current["macd_signal"]:
        macd_state = "BULLISH"
    else:
        macd_state = "BEARISH"

    print(
        f"[{now.strftime('%H:%M:%S')} UTC] "
        f"BTC: {current['close']:.2f} | "
        f"RSI: {current['rsi']:.2f} | "
        f"MACD: {macd_state} | "
        f"{trend} | "
        f"Waiting..."
    )


# ============================================================
# MAIN LOOP
# ============================================================

def main():

    print()
    print("=" * 70)
    print(BOT_NAME)
    print("=" * 70)

    print(
        "Symbol: BTC-USD"
    )

    print(
        "Timeframe: 5 minutes"
    )

    print()

    print("INDICATORS:")
    print("RSI 14")
    print("MACD 12 / 26 / 9")
    print("EMA 50")

    print()

    print("SIGNAL RULES:")
    print("CALL = Price > EMA50 + RSI 50-70 + Bullish MACD Cross")
    print("PUT  = Price < EMA50 + RSI 30-50 + Bearish MACD Cross")

    print()

    print(
        "Entry: NEXT CANDLE"
    )

    print(
        "Expiry: 10 minutes"
    )

    print(
        "Automatic trading: DISABLED"
    )

    print(
        "Paper trading: DISABLED"
    )

    print()

    print(
        "The bot analyzes completed candles only."
    )

    print("=" * 70)
    print()

    last_checked_candle = None
    last_signal_candle = None

    while True:

        try:

            df = get_candles()

            if df is None:

                print(
                    "Unable to download data. "
                    "Retrying..."
                )

                time.sleep(
                    POLL_SECONDS
                )

                continue

            df = calculate_indicators(df)

            completed_candle = df.iloc[-2]

            candle_time = (
                completed_candle["timestamp"]
            )

            # ------------------------------------------------
            # Analyze only when a new candle closes
            # ------------------------------------------------

            if candle_time != last_checked_candle:

                last_checked_candle = candle_time

                print()

                print(
                    "-" * 70
                )

                print(
                    "NEW COMPLETED CANDLE:",
                    candle_time.strftime(
                        "%Y-%m-%d %H:%M:%S UTC"
                    )
                )

                signal = analyze_signal(df)

                if signal is not None:

                    if (
                        signal["time"]
                        != last_signal_candle
                    ):

                        last_signal_candle = (
                            signal["time"]
                        )

                        print_signal(
                            signal
                        )

                else:

                    print_status(df)

            time.sleep(
                POLL_SECONDS
            )

        except KeyboardInterrupt:

            print()

            print(
                "Bot stopped by user."
            )

            break

        except Exception as e:

            print()

            print(
                "Unexpected error:"
            )

            print(
                str(e)
            )

            print(
                "Retrying..."
            )

            time.sleep(
                POLL_SECONDS
            )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
