import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
import requests

from ta.momentum import RSIIndicator


# ============================================================
# FOREX SIGNAL PRO
# ALLIGATOR + RSI
# ============================================================

BOT_NAME = "Forex Signal Pro"

TIMEFRAME = "5m"
DATA_PERIOD = "5d"

SCAN_INTERVAL = 300       # 5 minutes
ENTRY_DURATION = 5        # 5 minutes

TIMEZONE = "Asia/Baghdad"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ============================================================
# FOREX PAIRS
# ============================================================

PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "AUD/USD": "AUDUSD=X",
    "USD/JPY": "JPY=X",
    "USD/CAD": "CAD=X",
    "USD/CHF": "CHF=X",
    "NZD/USD": "NZDUSD=X",
}


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram: NOT CONFIGURED")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=15
        )

        if response.ok:
            print("Telegram notification sent.")
            return True

        print("Telegram error:", response.text)
        return False

    except Exception as e:

        print("Telegram error:", e)
        return False


# ============================================================
# ALLIGATOR
# ============================================================

def calculate_alligator(df):

    # Williams Alligator
    # Jaw   = SMA 13 shifted 8
    # Teeth = SMA 8 shifted 5
    # Lips  = SMA 5 shifted 3

    df["jaw"] = (
        df["Close"]
        .rolling(13)
        .mean()
        .shift(8)
    )

    df["teeth"] = (
        df["Close"]
        .rolling(8)
        .mean()
        .shift(5)
    )

    df["lips"] = (
        df["Close"]
        .rolling(5)
        .mean()
        .shift(3)
    )

    return df


# ============================================================
# MARKET DATA
# ============================================================

def get_data(symbol):

    try:

        df = yf.download(
            symbol,
            period=DATA_PERIOD,
            interval=TIMEFRAME,
            progress=False,
            auto_adjust=False
        )

        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        required = [
            "Open",
            "High",
            "Low",
            "Close"
        ]

        for col in required:

            if col not in df.columns:
                return None

        df = df.dropna()

        if len(df) < 100:
            return None

        return df

    except Exception as e:

        print(f"Data error {symbol}: {e}")
        return None


# ============================================================
# ANALYZE PAIR
# ============================================================

def analyze_pair(pair_name, symbol):

    df = get_data(symbol)

    if df is None:

        print(
            f"{pair_name:<10} | DATA ERROR"
        )

        return None

    try:

        # RSI
        rsi_indicator = RSIIndicator(
            close=df["Close"],
            window=14
        )

        df["rsi"] = rsi_indicator.rsi()

        # Alligator
        df = calculate_alligator(df)

        df = df.dropna()

        if len(df) < 10:

            print(
                f"{pair_name:<10} | WAIT"
            )

            return None

        # ====================================================
        # IMPORTANT
        # Use LAST COMPLETED candle
        # ====================================================

        row = df.iloc[-2]

        close_price = float(row["Close"])

        rsi = float(row["rsi"])

        jaw = float(row["jaw"])
        teeth = float(row["teeth"])
        lips = float(row["lips"])

        signal = None

        # ====================================================
        # CALL
        # ====================================================

        if (
            lips > teeth > jaw
            and close_price > lips
            and rsi > 50
            and rsi < 70
        ):

            signal = "CALL"

        # ====================================================
        # PUT
        # ====================================================

        elif (
            lips < teeth < jaw
            and close_price < lips
            and rsi < 50
            and rsi > 30
        ):

            signal = "PUT"

        # ====================================================
        # RESULT
        # ====================================================

        if signal:

            print(
                f"{pair_name:<10} | "
                f"{signal:<4} | "
                f"RSI {rsi:.1f} | "
                f"Alligator CONFIRMED"
            )

            return {
                "pair": pair_name,
                "signal": signal,
                "rsi": rsi
            }

        else:

            print(
                f"{pair_name:<10} | "
                f"WAIT | "
                f"RSI {rsi:.1f}"
            )

            return None

    except Exception as e:

        print(
            f"{pair_name:<10} | ERROR: {e}"
        )

        return None


# ============================================================
# NEXT 5-MINUTE CANDLE
# ============================================================

def get_next_candle_time():

    now = datetime.now(
        ZoneInfo(TIMEZONE)
    )

    # Find the next 5-minute boundary
    minutes_to_add = 5 - (now.minute % 5)

    if minutes_to_add == 5 and now.second == 0:
        minutes_to_add = 0

    next_time = (
        now.replace(
            second=0,
            microsecond=0
        )
        + timedelta(minutes=minutes_to_add)
    )

    # If we are exactly on a boundary,
    # the next candle starts now.
    if (
        now.minute % 5 == 0
        and now.second == 0
    ):

        next_time = now.replace(
            second=0,
            microsecond=0
        )

    return next_time


# ============================================================
# TELEGRAM SIGNAL MESSAGE
# ============================================================

def build_signal_message(
    signals,
    entry_time
):

    if not signals:
        return None

    message = (
        "🚨 FOREX SIGNAL PRO\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    for signal in signals:

        if signal["signal"] == "CALL":
            emoji = "🟢"
        else:
            emoji = "🔴"

        message += (
            f"{emoji} {signal['pair']} → "
            f"{signal['signal']}\n"
            f"🕐 وقت الدخول: "
            f"{entry_time.strftime('%H:%M')}\n"
            f"⏱️ مدة الصفقة: "
            f"{ENTRY_DURATION} دقائق\n\n"
        )

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 Alligator + RSI\n"
        "⏰ Timeframe: 5m\n"
        "➡️ الدخول مع بداية الشمعة التالية"
    )

    return message


# ============================================================
# STARTUP
# ============================================================

def send_startup_message():

    message = (
        "🚨 FOREX SIGNAL PRO\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🟢 البوت يعمل الآن\n"
        "📊 Strategy: Alligator + RSI\n"
        "⏰ Timeframe: 5m\n"
        "⏱️ مدة الصفقة: 5 دقائق\n"
        "➡️ الدخول: بداية الشمعة التالية\n"
        "🕐 التوقيت: العراق"
    )

    send_telegram(message)


# ============================================================
# MAIN
# ============================================================

def main():

    print("==============================================")
    print("       FOREX SIGNAL PRO")
    print("       ALLIGATOR + RSI")
    print("==============================================")

    print(f"Timeframe: {TIMEFRAME}")
    print(f"Scan interval: {SCAN_INTERVAL} seconds")
    print(f"Entry duration: {ENTRY_DURATION} minutes")
    print("Strategy: Alligator + RSI")
    print("Entry: NEXT 5-MINUTE CANDLE")

    if (
        TELEGRAM_BOT_TOKEN
        and TELEGRAM_CHAT_ID
    ):

        print("Telegram: Enabled")
        send_startup_message()

    else:

        print("Telegram: NOT CONFIGURED")

    print("==============================================")

    while True:

        scan_start = datetime.now(
            ZoneInfo(TIMEZONE)
        )

        print(
            f"[{scan_start.strftime('%Y-%m-%d %H:%M:%S')}] "
            "Market scan started..."
        )

        print("==============================================")
        print("Scanning market...")
        print("==============================================")

        signals = []

        for pair_name, symbol in PAIRS.items():

            result = analyze_pair(
                pair_name,
                symbol
            )

            if result:
                signals.append(result)

        # ====================================================
        # SEND SIGNAL
        # ====================================================

        if signals:

            next_candle = get_next_candle_time()

            message = build_signal_message(
                signals,
                next_candle
            )

            send_telegram(message)

            print(
                f"Next candle entry: "
                f"{next_candle.strftime('%H:%M')}"
            )

        else:

            print("No confirmed signals.")

        # ====================================================
        # NEXT SCAN
        # ====================================================

        print("==============================================")
        print(
            f"Next scan in "
            f"{SCAN_INTERVAL} seconds..."
        )
        print("==============================================")

        time.sleep(SCAN_INTERVAL)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
