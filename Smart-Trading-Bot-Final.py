import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator


# ============================================================
# SMART TRADING SIGNAL BOT
# MULTI-PAIR FOREX
# ============================================================

BOT_NAME = "Smart Trading Signal Bot"

TIMEFRAME = "5m"
DATA_PERIOD = "5d"

POLL_SECONDS = 30

RSI_PERIOD = 14
EMA_PERIOD = 50

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

EXPIRY_MINUTES = 10


# ============================================================
# FOREX PAIRS
# ============================================================

PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "USDCAD=X",
    "EUR/JPY": "EURJPY=X",
    "GBP/JPY": "GBPJPY=X",
    "EUR/GBP": "EURGBP=X",
    "EUR/CHF": "EURCHF=X",
    "AUD/JPY": "AUDJPY=X",
}


# ============================================================
# TIME
# ============================================================

IRAQ_TZ = ZoneInfo("Asia/Baghdad")


def iraq_time():
    return datetime.now(IRAQ_TZ).strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# DOWNLOAD DATA
# ============================================================

def download_data():

    symbols = list(PAIRS.values())

    try:

        data = yf.download(
            tickers=symbols,
            interval=TIMEFRAME,
            period=DATA_PERIOD,
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=False
        )

        if data is None or data.empty:
            print("ERROR: No market data received.")
            return None

        return data

    except Exception as e:

        print(f"ERROR downloading data: {e}")
        return None


# ============================================================
# GET PAIR DATA
# ============================================================

def get_pair_data(all_data, yahoo_symbol):

    try:

        if isinstance(all_data.columns, pd.MultiIndex):

            # Normal yfinance format:
            # SYMBOL -> Open, High, Low, Close...

            if yahoo_symbol in all_data.columns.get_level_values(0):
                df = all_data[yahoo_symbol].copy()

            elif yahoo_symbol in all_data.columns.get_level_values(1):
                df = all_data.xs(
                    yahoo_symbol,
                    axis=1,
                    level=1
                ).copy()

            else:
                return None

        else:

            df = all_data.copy()

        required = ["Open", "High", "Low", "Close"]

        for column in required:
            if column not in df.columns:
                return None

        df = df.dropna()

        if len(df) < 100:
            return None

        return df

    except Exception:
        return None


# ============================================================
# CALCULATE INDICATORS
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    # EMA 50
    df["EMA50"] = EMAIndicator(
        close=df["Close"],
        window=EMA_PERIOD
    ).ema_indicator()

    # RSI 14
    df["RSI"] = RSIIndicator(
        close=df["Close"],
        window=RSI_PERIOD
    ).rsi()

    # MACD
    macd = MACD(
        close=df["Close"],
        window_fast=MACD_FAST,
        window_slow=MACD_SLOW,
        window_sign=MACD_SIGNAL
    )

    df["MACD"] = macd.macd()
    df["MACD_SIGNAL"] = macd.macd_signal()
    df["MACD_HIST"] = macd.macd_diff()

    return df.dropna()


# ============================================================
# ANALYZE PAIR
# ============================================================

def analyze_pair(pair_name, df):

    try:

        df = calculate_indicators(df)

        if len(df) < 5:
            return None

        # Last completed candle
        current = df.iloc[-2]

        # Candle before it
        previous = df.iloc[-3]

        close_price = float(current["Close"])
        ema = float(current["EMA50"])
        rsi = float(current["RSI"])

        macd_current = float(current["MACD"])
        macd_signal_current = float(current["MACD_SIGNAL"])

        macd_previous = float(previous["MACD"])
        macd_signal_previous = float(previous["MACD_SIGNAL"])

        bullish_cross = (
            macd_previous <= macd_signal_previous
            and macd_current > macd_signal_current
        )

        bearish_cross = (
            macd_previous >= macd_signal_previous
            and macd_current < macd_signal_current
        )

        # ====================================================
        # CALL
        # ====================================================

        call_conditions = [
            close_price > ema,
            rsi > 50,
            rsi < 70,
            bullish_cross
        ]

        # ====================================================
        # PUT
        # ====================================================

        put_conditions = [
            close_price < ema,
            rsi < 50,
            rsi > 30,
            bearish_cross
        ]

        candle_time = current.name

        if candle_time.tzinfo is None:
            candle_time = candle_time.tz_localize("UTC")

        iraq_candle_time = candle_time.tz_convert(IRAQ_TZ)

        # ====================================================
        # VALID CALL
        # ====================================================

        if all(call_conditions):

            return {
                "pair": pair_name,
                "direction": "CALL",
                "price": close_price,
                "ema": ema,
                "rsi": rsi,
                "macd": macd_current,
                "candle_time": iraq_candle_time
            }

        # ====================================================
        # VALID PUT
        # ====================================================

        if all(put_conditions):

            return {
                "pair": pair_name,
                "direction": "PUT",
                "price": close_price,
                "ema": ema,
                "rsi": rsi,
                "macd": macd_current,
                "candle_time": iraq_candle_time
            }

        return None

    except Exception as e:

        print(f"ERROR analyzing {pair_name}: {e}")
        return None


# ============================================================
# PRINT SIGNAL
# ============================================================

def print_signal(signal):

    print("")
    print("=" * 65)
    print("                 VALID SIGNAL")
    print("=" * 65)

    print(f"PAIR       : {signal['pair']}")
    print(f"DIRECTION  : {signal['direction']}")

    print(f"PRICE      : {signal['price']:.5f}")
    print(f"EMA 50     : {signal['ema']:.5f}")
    print(f"RSI 14     : {signal['rsi']:.2f}")
    print(f"MACD       : {signal['macd']:.6f}")

    print(f"CANDLE     : {signal['candle_time'].strftime('%Y-%m-%d %H:%M:%S')} Iraq")

    print("")
    print("MANUAL ENTRY : NEXT 5-MINUTE CANDLE")
    print(f"EXPIRY       : {EXPIRY_MINUTES} MINUTES")

    print("=" * 65)
    print("")


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 65)
    print(BOT_NAME)
    print("=" * 65)

    print("Timeframe      : 5 minutes")
    print("Pairs          : 10 Forex pairs")
    print("Indicators     : RSI + MACD + EMA")
    print("Trading        : MANUAL")
    print("OTC            : NO")
    print("Expiry         : 10 minutes")
    print("=" * 65)
    print("")

    last_processed_candle = None
    last_signals = {}

    while True:

        try:

            print(f"[{iraq_time()}] Scanning market...")

            all_data = download_data()

            if all_data is None:
                time.sleep(POLL_SECONDS)
                continue

            signals_found = 0

            current_scan_candle = None

            for pair_name, yahoo_symbol in PAIRS.items():

                df = get_pair_data(
                    all_data,
                    yahoo_symbol
                )

                if df is None:
                    print(f"{pair_name:10} | No data")
                    continue

                try:

                    completed_candle = df.index[-2]

                    if completed_candle.tzinfo is None:
                        completed_candle = completed_candle.tz_localize("UTC")

                    completed_candle = completed_candle.tz_convert(
                        IRAQ_TZ
                    )

                    if current_scan_candle is None:
                        current_scan_candle = completed_candle

                except Exception:
                    continue

                signal = analyze_pair(
                    pair_name,
                    df
                )

                # ------------------------------------------------
                # Avoid repeating the same signal
                # ------------------------------------------------

                signal_key = (
                    pair_name,
                    str(completed_candle)
                )

                if signal is not None:

                    if signal_key not in last_signals:

                        print_signal(signal)

                        last_signals[signal_key] = True

                        signals_found += 1

                else:

                    # Simple status
                    try:

                        temp_df = calculate_indicators(df)

                        candle = temp_df.iloc[-2]

                        close = float(candle["Close"])
                        ema = float(candle["EMA50"])
                        rsi = float(candle["RSI"])

                        trend = "ABOVE EMA" if close > ema else "BELOW EMA"

                        print(
                            f"{pair_name:10} | "
                            f"RSI {rsi:5.1f} | "
                            f"{trend}"
                        )

                    except Exception:
                        pass

            # ----------------------------------------------------
            # New candle message
            # ----------------------------------------------------

            if current_scan_candle != last_processed_candle:

                print("")
                print(
                    f"Completed candle: "
                    f"{current_scan_candle}"
                )

                if signals_found == 0:
                    print("No VALID SIGNAL on this scan.")

                last_processed_candle = current_scan_candle

            print("")
            print(
                f"Next scan in {POLL_SECONDS} seconds..."
            )
            print("")

            time.sleep(POLL_SECONDS)

        except KeyboardInterrupt:

            print("")
            print("Bot stopped manually.")
            break

        except Exception as e:

            print(f"MAIN ERROR: {e}")
            time.sleep(POLL_SECONDS)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
