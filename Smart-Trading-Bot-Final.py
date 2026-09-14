import requests
import pandas as pd
import time
from datetime import datetime, timezone
from ta.trend import MACD, ADXIndicator, EMAIndicator


# ============================================================
# SMART TRADING SIGNAL BOT
# ============================================================

BOT_NAME = "Smart Trading Signal Bot"

SYMBOL = "BTC-USD"
GRANULARITY = 300       # 5 minutes

ADX_MIN = 35
EMA_PERIOD = 50

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

POLL_SECONDS = 20

# Expiry = 2 candles
# 2 x 5 minutes = 10 minutes
EXPIRY_CANDLES = 2


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

    macd = MACD(
        close=df["close"],
        window_fast=MACD_FAST,
        window_slow=MACD_SLOW,
        window_sign=MACD_SIGNAL
    )

    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    adx = ADXIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    )

    df["adx"] = adx.adx()

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

    # Use the last COMPLETED candle.
    # The last candle may still be forming.
    current = df.iloc[-2]
    previous = df.iloc[-3]

    if pd.isna(current["macd"]):
        return None

    if pd.isna(current["macd_signal"]):
        return None

    if pd.isna(current["adx"]):
        return None

    if pd.isna(current["ema50"]):
        return None

    macd_cross = (
        current["macd"] > current["macd_signal"]
        and
        previous["macd"] <= previous["macd_signal"]
    )

    adx_ok = current["adx"] >= ADX_MIN

    ema_ok = current["close"] > current["ema50"]

    if macd_cross and adx_ok and ema_ok:

        return {
            "signal": "CALL",
            "time": current["timestamp"],
            "price": float(current["close"]),
            "macd": float(current["macd"]),
            "macd_signal": float(current["macd_signal"]),
            "adx": float(current["adx"]),
            "ema50": float(current["ema50"])
        }

    return None


# ============================================================
# CONFIDENCE
# ============================================================

def calculate_confidence(signal):

    score = 0

    # MACD bullish cross
    score += 40

    # ADX strength
    adx = signal["adx"]

    if adx >= 45:
        score += 10

    elif adx >= 40:
        score += 15

    elif adx >= 35:
        score += 20

    # Price above EMA
    distance = (
        (signal["price"] - signal["ema50"])
        / signal["ema50"]
    ) * 100

    if distance >= 0.50:
        score += 25

    elif distance >= 0.20:
        score += 20

    elif distance > 0:
        score += 15

    # Cap confidence
    score = min(score, 100)

    return score


# ============================================================
# PRINT SIGNAL
# ============================================================

def print_signal(signal):

    confidence = calculate_confidence(signal)

    print()
    print("=" * 60)
    print("🟢 CALL SIGNAL")
    print("=" * 60)

    print(
        "Time:",
        signal["time"].strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )

    print(
        "Price:",
        f"{signal['price']:.2f}"
    )

    print()
    print("MACD:", f"{signal['macd']:.6f}")
    print(
        "MACD Signal:",
        f"{signal['macd_signal']:.6f}"
    )

    print(
        "ADX:",
        f"{signal['adx']:.2f}"
    )

    print(
        "EMA50:",
        f"{signal['ema50']:.2f}"
    )

    print()
    print("Direction: CALL")
    print("Expiry: 10 minutes")
    print(
        "Confidence:",
        f"{confidence}%"
    )

    print("=" * 60)
    print()


# ============================================================
# WAITING MESSAGE
# ============================================================

def print_status(df):

    current = df.iloc[-2]

    now = datetime.now(timezone.utc)

    print(
        f"[{now.strftime('%H:%M:%S')} UTC] "
        f"BTC: {current['close']:.2f} | "
        f"ADX: {current['adx']:.2f} | "
        f"EMA50: "
        f"{'ABOVE' if current['close'] > current['ema50'] else 'BELOW'} | "
        f"Waiting..."
    )


# ============================================================
# MAIN LOOP
# ============================================================

def main():

    print()
    print("=" * 60)
    print(BOT_NAME)
    print("=" * 60)

    print("Symbol:", SYMBOL)
    print("Timeframe: 5 minutes")
    print("Strategy:")
    print("MACD Bullish Cross")
    print("ADX >= 35")
    print("Price > EMA50")
    print("Direction: CALL only")
    print("Expiry: 10 minutes")
    print()
    print("Starting bot...")
    print("The bot uses completed candles only.")
    print("No automatic trades are executed.")
    print("=" * 60)
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

                time.sleep(POLL_SECONDS)
                continue

            df = calculate_indicators(df)

            completed_candle = df.iloc[-2]
            candle_time = completed_candle["timestamp"]

            # Only analyze when a new candle has completed.
            if candle_time != last_checked_candle:

                last_checked_candle = candle_time

                print()

                print(
                    "-" * 60
                )

                print(
                    "New completed candle:",
                    candle_time.strftime(
                        "%Y-%m-%d %H:%M:%S UTC"
                    )
                )

                signal = analyze_signal(df)

                if signal is not None:

                    # Prevent duplicate signal
                    if (
                        signal["time"]
                        != last_signal_candle
                    ):

                        last_signal_candle = (
                            signal["time"]
                        )

                        print_signal(signal)

                    else:

                        print(
                            "Signal already reported."
                        )

                else:

                    print_status(df)

            time.sleep(POLL_SECONDS)

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
            print(str(e))
            print(
                "Retrying..."
            )

            time.sleep(POLL_SECONDS)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
