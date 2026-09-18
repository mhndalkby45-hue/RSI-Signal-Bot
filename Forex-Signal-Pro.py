import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
import requests


# ============================================================
# FOREX SIGNAL PRO
# AROON + KELTNER CHANNEL
# ============================================================

BOT_NAME = "Forex Signal Pro"

TIMEFRAME = "5m"
DATA_PERIOD = "5d"

SCAN_INTERVAL = 300       # فحص كل 5 دقائق
TRADE_DURATION = 5        # مدة الصفقة 5 دقائق

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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram: NOT CONFIGURED")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            },
            timeout=15
        )

        if response.ok:
            print("Telegram: Message sent")
        else:
            print("Telegram error:", response.text)

    except Exception as e:
        print("Telegram error:", e)


# ============================================================
# AROON
# ============================================================

def calculate_aroon(df, period=14):

    highest = df["High"].rolling(period + 1).apply(
        lambda x: period - x.argmax(),
        raw=True
    )

    lowest = df["Low"].rolling(period + 1).apply(
        lambda x: period - x.argmin(),
        raw=True
    )

    df["Aroon_Up"] = ((period - highest) / period) * 100
    df["Aroon_Down"] = ((period - lowest) / period) * 100

    return df


# ============================================================
# KELTNER CHANNEL
# ============================================================

def calculate_keltner(
    df,
    ema_period=20,
    atr_period=10,
    multiplier=2
):

    df["KC_Middle"] = df["Close"].ewm(
        span=ema_period,
        adjust=False
    ).mean()

    previous_close = df["Close"].shift(1)

    tr1 = df["High"] - df["Low"]
    tr2 = (df["High"] - previous_close).abs()
    tr3 = (df["Low"] - previous_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    atr = true_range.rolling(atr_period).mean()

    df["KC_Upper"] = (
        df["KC_Middle"] +
        multiplier * atr
    )

    df["KC_Lower"] = (
        df["KC_Middle"] -
        multiplier * atr
    )

    return df


# ============================================================
# GET MARKET DATA
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

        for column in required:
            if column not in df.columns:
                return None

        df = df[required].dropna()

        if len(df) < 60:
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

        print(f"{pair_name:8} | NO DATA")

        return None

    df = calculate_aroon(df, 14)

    df = calculate_keltner(
        df,
        ema_period=20,
        atr_period=10,
        multiplier=2
    )

    df = df.dropna()

    if len(df) < 10:
        return None

    # آخر شمعة مكتملة
    current = df.iloc[-2]

    previous = df.iloc[-3]

    close = float(current["Close"])

    previous_close = float(previous["Close"])

    aroon_up = float(current["Aroon_Up"])
    aroon_down = float(current["Aroon_Down"])

    upper = float(current["KC_Upper"])
    lower = float(current["KC_Lower"])

    previous_upper = float(previous["KC_Upper"])
    previous_lower = float(previous["KC_Lower"])

    signal = None

    # ========================================================
    # CALL
    # ========================================================

    bullish_aroon = (
        aroon_up > aroon_down
        and aroon_up >= 70
    )

    bullish_breakout = (
        previous_close <= previous_upper
        and close > upper
    )

    if bullish_aroon and bullish_breakout:

        signal = "CALL"

    # ========================================================
    # PUT
    # ========================================================

    bearish_aroon = (
        aroon_down > aroon_up
        and aroon_down >= 70
    )

    bearish_breakout = (
        previous_close >= previous_lower
        and close < lower
    )

    if bearish_aroon and bearish_breakout:

        signal = "PUT"

    # ========================================================
    # DISPLAY
    # ========================================================

    if signal:

        print(
            f"{pair_name:8} | "
            f"{signal:4} | "
            f"Aroon Up {aroon_up:5.1f} | "
            f"Down {aroon_down:5.1f}"
        )

    else:

        print(
            f"{pair_name:8} | WAIT | "
            f"Aroon Up {aroon_up:5.1f} | "
            f"Down {aroon_down:5.1f}"
        )

    return signal


# ============================================================
# NEXT 5-MINUTE ENTRY TIME
# ============================================================

def get_next_entry_time():

    now = datetime.now(
        ZoneInfo("Asia/Baghdad")
    )

    # ننتظر بداية الشمعة التالية
    minutes_to_next = 5 - (now.minute % 5)

    if minutes_to_next == 5 and now.second == 0:
        minutes_to_next = 5

    entry = now + timedelta(
        minutes=minutes_to_next
    )

    entry = entry.replace(
        second=0,
        microsecond=0
    )

    return entry


# ============================================================
# SEND SIGNAL
# ============================================================

def send_signal(pair, signal):

    entry_time = get_next_entry_time()

    message = (
        "🚨 FOREX SIGNAL PRO\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"💱 {pair} → {signal}\n"
        f"🕐 وقت الدخول: {entry_time.strftime('%H:%M')}\n"
        f"⏱️ مدة الصفقة: {TRADE_DURATION} دقائق\n\n"
        "📊 Aroon + Keltner Channel"
    )

    print("\n" + message + "\n")

    send_telegram(message)


# ============================================================
# STARTUP MESSAGE
# ============================================================

def send_startup():

    message = (
        "🤖 FOREX SIGNAL PRO\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "✅ البوت يعمل الآن\n\n"
        "📊 Strategy: Aroon + Keltner Channel\n"
        "⏱️ Timeframe: 5m\n"
        "⌛ مدة الصفقة: 5 دقائق\n"
        "📱 Telegram: Enabled"
    )

    send_telegram(message)


# ============================================================
# MAIN LOOP
# ============================================================

def main():

    print("=" * 50)
    print("       FOREX SIGNAL PRO")
    print("       AROON + KELTNER")
    print("=" * 50)

    print(f"Timeframe: {TIMEFRAME}")
    print(f"Scan interval: {SCAN_INTERVAL} seconds")
    print(f"Entry duration: {TRADE_DURATION} minutes")
    print("Strategy: Aroon + Keltner Channel")
    print("=" * 50)

    send_startup()

    while True:

        try:

            print("\n")
            print("=" * 50)

            now = datetime.now(
                ZoneInfo("Asia/Baghdad")
            )

            print(
                "Scanning market...",
                now.strftime("%Y-%m-%d %H:%M:%S")
            )

            print("=" * 50)

            signals_found = 0

            for pair, symbol in PAIRS.items():

                signal = analyze_pair(
                    pair,
                    symbol
                )

                if signal:

                    send_signal(
                        pair,
                        signal
                    )

                    signals_found += 1

            if signals_found == 0:

                print("\nNo valid signals.")

            print(
                f"\nNext scan in "
                f"{SCAN_INTERVAL // 60} minutes..."
            )

            time.sleep(SCAN_INTERVAL)

        except KeyboardInterrupt:

            print("\nBot stopped.")
            break

        except Exception as e:

            print(
                "Main loop error:",
                e
            )

            time.sleep(30)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
