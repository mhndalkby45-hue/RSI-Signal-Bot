import time
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
import requests

from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator

============================================================

SMART TRADING SIGNAL BOT

MULTI-PAIR FOREX + TELEGRAM

============================================================

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

============================================================

TELEGRAM

============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

TELEGRAM_CHAT_ID = None

def get_telegram_chat_id():

if not TELEGRAM_BOT_TOKEN:
    print("WARNING: TELEGRAM_BOT_TOKEN is not configured.")
    return None

try:

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/getUpdates"
    )

    response = requests.get(
        url,
        timeout=15
    )

    data = response.json()

    if not data.get("ok"):
        print(
            "Telegram error while getting Chat ID:",
            data
        )
        return None

    updates = data.get("result", [])

    if not updates:
        print(
            "No Telegram messages found."
        )
        print(
            "Open your bot in Telegram and send: test"
        )
        return None

    # Use the most recent message
    for update in reversed(updates):

        message = update.get("message")

        if message:

            chat = message.get("chat")

            if chat:

                chat_id = chat.get("id")

                if chat_id is not None:

                    print(
                        f"Telegram Chat ID detected: {chat_id}"
                    )

                    return str(chat_id)

    print(
        "Could not find a Telegram Chat ID."
    )

    return None

except Exception as e:

    print(
        f"Telegram Chat ID error: {e}"
    )

    return None

def send_telegram(message):

if not TELEGRAM_BOT_TOKEN:
    print(
        "Telegram not configured."
    )
    return False

global TELEGRAM_CHAT_ID

if TELEGRAM_CHAT_ID is None:

    TELEGRAM_CHAT_ID = get_telegram_chat_id()

if TELEGRAM_CHAT_ID is None:

    print(
        "Telegram message not sent: "
        "Chat ID not available."
    )

    return False

try:

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    response = requests.post(
        url,
        json=payload,
        timeout=15
    )

    data = response.json()

    if data.get("ok"):

        print(
            "Telegram notification sent."
        )

        return True

    print(
        "Telegram send error:",
        data
    )

    return False

except Exception as e:

    print(
        f"Telegram send exception: {e}"
    )

    return False

============================================================

FOREX PAIRS

============================================================

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

============================================================

TIME

============================================================

IRAQ_TZ = ZoneInfo("Asia/Baghdad")

def iraq_time():

return datetime.now(
    IRAQ_TZ
).strftime(
    "%Y-%m-%d %H:%M:%S"
)

============================================================

DOWNLOAD DATA

============================================================

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

        print(
            "ERROR: No market data received."
        )

        return None

    return data

except Exception as e:

    print(
        f"ERROR downloading data: {e}"
    )

    return None

============================================================

GET PAIR DATA

============================================================

def get_pair_data(
all_data,
yahoo_symbol
):

try:

    if isinstance(
        all_data.columns,
        pd.MultiIndex
    ):

        if yahoo_symbol in all_data.columns.get_level_values(0):

            df = all_data[
                yahoo_symbol
            ].copy()

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

    required = [
        "Open",
        "High",
        "Low",
        "Close"
    ]

    for column in required:

        if column not in df.columns:

            return None

    df = df.dropna()

    if len(df) < 100:

        return None

    return df

except Exception:

    return None

============================================================

CALCULATE INDICATORS

============================================================

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

df["MACD_SIGNAL"] = (
    macd.macd_signal()
)

df["MACD_HIST"] = (
    macd.macd_diff()
)

return df.dropna()

============================================================

ANALYZE PAIR

============================================================

def analyze_pair(
pair_name,
df
):

try:

    df = calculate_indicators(df)

    if len(df) < 5:

        return None

    # Last completed candle

    current = df.iloc[-2]

    # Candle before it

    previous = df.iloc[-3]

    close_price = float(
        current["Close"]
    )

    ema = float(
        current["EMA50"]
    )

    rsi = float(
        current["RSI"]
    )

    macd_current = float(
        current["MACD"]
    )

    macd_signal_current = float(
        current["MACD_SIGNAL"]
    )

    macd_previous = float(
        previous["MACD"]
    )

    macd_signal_previous = float(
        previous["MACD_SIGNAL"]
    )

    bullish_cross = (
        macd_previous <= macd_signal_previous
        and
        macd_current > macd_signal_current
    )

    bearish_cross = (
        macd_previous >= macd_signal_previous
        and
        macd_current < macd_signal_current
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

        candle_time = (
            candle_time.tz_localize("UTC")
        )

    iraq_candle_time = (
        candle_time.tz_convert(
            IRAQ_TZ
        )
    )

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

    print(
        f"ERROR analyzing "
        f"{pair_name}: {e}"
    )

    return None

============================================================

PRINT + TELEGRAM SIGNAL

============================================================

def print_signal(signal):

print("")

print("=" * 65)

print(
    "                 VALID SIGNAL"
)

print("=" * 65)

print(
    f"PAIR       : "
    f"{signal['pair']}"
)

print(
    f"DIRECTION  : "
    f"{signal['direction']}"
)

print(
    f"PRICE      : "
    f"{signal['price']:.5f}"
)

print(
    f"EMA 50     : "
    f"{signal['ema']:.5f}"
)

print(
    f"RSI 14     : "
    f"{signal['rsi']:.2f}"
)

print(
    f"MACD       : "
    f"{signal['macd']:.6f}"
)

print(
    f"CANDLE     : "
    f"{signal['candle_time'].strftime('%Y-%m-%d %H:%M:%S')} Iraq"
)

print("")

print(
    "MANUAL ENTRY : "
    "NEXT 5-MINUTE CANDLE"
)

print(
    f"EXPIRY       : "
    f"{EXPIRY_MINUTES} MINUTES"
)

print("=" * 65)

print("")

# ========================================================
# TELEGRAM MESSAGE
# ========================================================

direction_icon = (
    "🟢 CALL"
    if signal["direction"] == "CALL"
    else
    "🔴 PUT"
)

telegram_message = (
    "📊 SMART TRADING SIGNAL\n"
    "\n"
    f"💱 Pair: {signal['pair']}\n"
    f"📌 Direction: {direction_icon}\n"
    f"💰 Price: {signal['price']:.5f}\n"
    f"📈 EMA 50: {signal['ema']:.5f}\n"
    f"📊 RSI 14: {signal['rsi']:.2f}\n"
    f"📉 MACD: {signal['macd']:.6f}\n"
    "\n"
    "⏱ Entry: NEXT 5-MINUTE CANDLE\n"
    f"⌛ Expiry: {EXPIRY_MINUTES} minutes\n"
    "\n"
    f"🕐 Iraq time: "
    f"{signal['candle_time'].strftime('%Y-%m-%d %H:%M:%S')}"
)

send_telegram(
    telegram_message
)

============================================================

MAIN

============================================================

def main():

print("")

print("=" * 65)

print(BOT_NAME)

print("=" * 65)

print(
    "Timeframe      : 5 minutes"
)

print(
    "Pairs          : 10 Forex pairs"
)

print(
    "Indicators     : RSI + MACD + EMA"
)

print(
    "Trading        : MANUAL"
)

print(
    "OTC            : NO"
)

print(
    "Expiry         : 10 minutes"
)

print(
    "Telegram       : ENABLED"
)

print("=" * 65)

print("")

# ========================================================
# TEST TELEGRAM CONNECTION
# ========================================================

if TELEGRAM_BOT_TOKEN:

    print(
        "Connecting to Telegram..."
    )

    global TELEGRAM_CHAT_ID

    TELEGRAM_CHAT_ID = (
        get_telegram_chat_id()
    )

    if TELEGRAM_CHAT_ID:

        send_telegram(
            "✅ Smart Trading Signal Bot is connected.\n"
            "Telegram notifications are active."
        )

    else:

        print(
            "Telegram Chat ID was not found."
        )

        print(
            "Make sure you sent 'test' to the bot."
        )

else:

    print(
        "WARNING: TELEGRAM_BOT_TOKEN is missing."
    )

last_processed_candle = None

last_signals = {}

while True:

    try:

        print(
            f"[{iraq_time()}] "
            "Scanning market..."
        )

        all_data = download_data()

        if all_data is None:

            time.sleep(
                POLL_SECONDS
            )

            continue

        signals_found = 0

        current_scan_candle = None

        for pair_name, yahoo_symbol in PAIRS.items():

            df = get_pair_data(
                all_data,
                yahoo_symbol
            )

            if df is None:

                print(
                    f"{pair_name:10} | "
                    "No data"
                )

                continue

            try:

                completed_candle = (
                    df.index[-2]
                )

                if completed_candle.tzinfo is None:

                    completed_candle = (
                        completed_candle.tz_localize(
                            "UTC"
                        )
                    )

                completed_candle = (
                    completed_candle.tz_convert(
                        IRAQ_TZ
                    )
                )

                if current_scan_candle is None:

                    current_scan_candle = (
                        completed_candle
                    )

            except Exception:

                continue

            signal = analyze_pair(
                pair_name,
                df
            )

            signal_key = (
                pair_name,
                str(completed_candle)
            )

            if signal is not None:

                if signal_key not in last_signals:

                    print_signal(
                        signal
                    )

                    last_signals[
                        signal_key
                    ] = True

                    signals_found += 1

            else:

                try:

                    temp_df = (
                        calculate_indicators(
                            df
                        )
                    )

                    candle = (
                        temp_df.iloc[-2]
                    )

                    close = float(
                        candle["Close"]
                    )

                    ema = float(
                        candle["EMA50"]
                    )

                    rsi = float(
                        candle["RSI"]
                    )

                    trend = (
                        "ABOVE EMA"
                        if close > ema
                        else
                        "BELOW EMA"
                    )

                    print(
                        f"{pair_name:10} | "
                        f"RSI {rsi:5.1f} | "
                        f"{trend}"
                    )

                except Exception:

                    pass

        # =================================================
        # NEW CANDLE MESSAGE
        # =================================================

        if (
            current_scan_candle
            != last_processed_candle
        ):

            print("")

            print(
                f"Completed candle: "
                f"{current_scan_candle}"
            )

            if signals_found == 0:

                print(
                    "No VALID SIGNAL "
                    "on this scan."
                )

            last_processed_candle = (
                current_scan_candle
            )

        print("")

        print(
            f"Next scan in "
            f"{POLL_SECONDS} seconds..."
        )

        print("")

        time.sleep(
            POLL_SECONDS
        )

    except KeyboardInterrupt:

        print("")

        print(
            "Bot stopped manually."
        )

        break

    except Exception as e:

        print(
            f"MAIN ERROR: {e}"
        )

        time.sleep(
            POLL_SECONDS
        )

============================================================

START

============================================================

if name == "main":

main()
