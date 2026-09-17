import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
import requests

from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator


# ============================================================
# FOREX SIGNAL PRO
# ============================================================

BOT_NAME = "Forex Signal Pro"

TIMEFRAME = "5m"
DATA_PERIOD = "5d"
SCAN_INTERVAL = 300  # 5 minutes

ENTRY_DURATION = 5  # minutes

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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
        print("Telegram: Disabled")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

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

        if response.status_code == 200:
            print("Telegram notification sent.")
            return True

        print("Telegram error:", response.text)
        return False

    except Exception as e:
        print("Telegram connection error:", e)
        return False


# ============================================================
# ENTRY TIME
# ============================================================

def get_entry_time():
    """
    يقترح أقرب بداية شمعة 5 دقائق قادمة
    بعد وقت ظهور الإشارة.
    """

    now = datetime.now(ZoneInfo("Asia/Baghdad"))

    next_minute = ((now.minute // 5) + 1) * 5

    if next_minute >= 60:
        entry_time = (
            now.replace(
                minute=0,
                second=0,
                microsecond=0
            )
            + timedelta(hours=1)
        )
    else:
        entry_time = now.replace(
            minute=next_minute,
            second=0,
            microsecond=0
        )

    return entry_time


# ============================================================
# DOWNLOAD DATA
# ============================================================

def get_data(symbol):

    try:

        data = yf.download(
            symbol,
            period=DATA_PERIOD,
            interval=TIMEFRAME,
            progress=False,
            auto_adjust=False
        )

        if data is None or data.empty:
            return None

        # التعامل مع MultiIndex في بعض إصدارات yfinance
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        required_columns = ["Close"]

        for column in required_columns:
            if column not in data.columns:
                return None

        data = data.dropna()

        if len(data) < 60:
            return None

        return data

    except Exception as e:

        print(f"Data error {symbol}: {e}")

        return None


# ============================================================
# ANALYZE PAIR
# ============================================================

def analyze_pair(pair_name, symbol):

    data = get_data(symbol)

    if data is None:
        print(f"{pair_name:<10} | No data")
        return None

    try:

        close = data["Close"]

        # ====================================================
        # INDICATORS
        # ====================================================

        ema20 = EMAIndicator(
            close=close,
            window=20
        ).ema_indicator()

        ema50 = EMAIndicator(
            close=close,
            window=50
        ).ema_indicator()

        rsi = RSIIndicator(
            close=close,
            window=14
        ).rsi()

        macd_indicator = MACD(
            close=close,
            window_fast=12,
            window_slow=26,
            window_sign=9
        )

        macd_line = macd_indicator.macd()
        macd_signal = macd_indicator.macd_signal()

        # ====================================================
        # آخر شمعة مكتملة
        # ====================================================

        latest = -2

        price = float(close.iloc[latest])
        ema20_value = float(ema20.iloc[latest])
        ema50_value = float(ema50.iloc[latest])
        rsi_value = float(rsi.iloc[latest])
        macd_value = float(macd_line.iloc[latest])
        macd_signal_value = float(macd_signal.iloc[latest])

        # ====================================================
        # CONDITIONS
        # ====================================================

        bullish_ema = (
            price > ema20_value
            and ema20_value > ema50_value
        )

        bearish_ema = (
            price < ema20_value
            and ema20_value < ema50_value
        )

        bullish_macd = (
            macd_value > macd_signal_value
        )

        bearish_macd = (
            macd_value < macd_signal_value
        )

        # ====================================================
        # SCORE
        # ====================================================

        call_score = 0
        put_score = 0

        if bullish_ema:
            call_score += 1

        if rsi_value > 50:
            call_score += 1

        if bullish_macd:
            call_score += 1

        if bearish_ema:
            put_score += 1

        if rsi_value < 50:
            put_score += 1

        if bearish_macd:
            put_score += 1

        # ====================================================
        # SIGNAL
        # ====================================================

        signal = None

        if call_score == 3:
            signal = "CALL"

        elif put_score == 3:
            signal = "PUT"

        # ====================================================
        # CONSOLE
        # ====================================================

        if signal:

            print(
                f"{pair_name:<10} | "
                f"{signal:<4} | "
                f"RSI {rsi_value:.1f} | "
                f"Score 3/3"
            )

        else:

            print(
                f"{pair_name:<10} | "
                f"WAIT | "
                f"RSI {rsi_value:.1f}"
            )

        return {
            "pair": pair_name,
            "signal": signal,
            "rsi": rsi_value,
            "call_score": call_score,
            "put_score": put_score
        }

    except Exception as e:

        print(f"Analysis error {pair_name}: {e}")

        return None


# ============================================================
# BUILD TELEGRAM MESSAGE
# ============================================================

def build_telegram_message(signals):

    if not signals:
        return None

    entry_time = get_entry_time()

    message = (
        "🚨 FOREX SIGNAL PRO\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    for signal in signals:

        pair = signal["pair"]
        direction = signal["signal"]

        if direction == "CALL":
            emoji = "🟢"
        else:
            emoji = "🔴"

        message += (
            f"{emoji} {pair} → {direction}\n"
            f"🕐 وقت الدخول: {entry_time.strftime('%H:%M')}\n"
            f"⏳ مدة الصفقة: {ENTRY_DURATION} دقائق\n\n"
        )

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "⚠️ إشارة آلية وليست ضماناً للنتيجة."
    )

    return message


# ============================================================
# SCAN MARKET
# ============================================================

def scan_market():

    print()
    print("==============================================")
    print("Scanning market...")
    print("==============================================")

    signals = []

    for pair_name, symbol in PAIRS.items():

        result = analyze_pair(
            pair_name,
            symbol
        )

        if result and result["signal"]:

            signals.append(result)

    # ========================================================
    # TELEGRAM ONLY WHEN SIGNAL EXISTS
    # ========================================================

    if signals:

        message = build_telegram_message(signals)

        if message:
            send_telegram(message)

    else:

        print("No complete signals.")

    print("==============================================")


# ============================================================
# STARTUP
# ============================================================

def startup():

    print()
    print("==============================================")
    print("       FOREX SIGNAL PRO")
    print("==============================================")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"Scan interval: {SCAN_INTERVAL} seconds")
    print(f"Entry duration: {ENTRY_DURATION} minutes")

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        print("Telegram: Enabled")

        send_telegram(
            "🚀 FOREX SIGNAL PRO\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ البوت يعمل الآن\n"
            "⏱ Timeframe: 5m\n"
            "⏳ مدة الصفقة المقترحة: 5 دقائق"
        )

    else:
        print("Telegram: Disabled")

    print("==============================================")
    print()


# ============================================================
# MAIN LOOP
# ============================================================

def main():

    startup()

    while True:

        try:

            current_time = datetime.now(
                ZoneInfo("Asia/Baghdad")
            )

            print(
                f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Market scan started..."
            )

            scan_market()

            print(
                f"Next scan in {SCAN_INTERVAL} seconds..."
            )

            time.sleep(SCAN_INTERVAL)

        except KeyboardInterrupt:

            print()
            print("Bot stopped.")
            break

        except Exception as e:

            print("Main loop error:", e)

            print("Retrying in 30 seconds...")

            time.sleep(30)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
