import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
import requests


# ============================================================
# FOREX SIGNAL PRO
# ALLIGATOR + RSI
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

    now = datetime.now(
        ZoneInfo("Asia/Baghdad")
    )

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

        # Handle MultiIndex
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        if "Close" not in data.columns:
            return None

        data = data.dropna()

        if len(data) < 60:
            return None

        return data

    except Exception as e:

        print(f"Data error {symbol}: {e}")

        return None


# ============================================================
# ALLIGATOR CALCULATION
# ============================================================

def calculate_alligator(close):

    # Williams Alligator
    #
    # Jaw   = SMMA 13
    # Teeth = SMMA 8
    # Lips  = SMMA 5
    #
    # For signal direction we compare the three lines
    # on the latest completed candle.

    jaw = close.ewm(
        alpha=1 / 13,
        adjust=False
    ).mean()

    teeth = close.ewm(
        alpha=1 / 8,
        adjust=False
    ).mean()

    lips = close.ewm(
        alpha=1 / 5,
        adjust=False
    ).mean()

    return jaw, teeth, lips


# ============================================================
# RSI CALCULATION
# ============================================================

def calculate_rsi(close, period=14):

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, float("nan"))

    rsi = 100 - (
        100 / (1 + rs)
    )

    return rsi


# ============================================================
# ANALYZE PAIR
# ============================================================

def analyze_pair(pair_name, symbol):

    data = get_data(symbol)

    if data is None:

        print(
            f"{pair_name:<10} | No data"
        )

        return None

    try:

        close = data["Close"]

        # ====================================================
        # INDICATORS
        # ====================================================

        jaw, teeth, lips = calculate_alligator(close)

        rsi = calculate_rsi(
            close,
            period=14
        )

        # ====================================================
        # LAST COMPLETED CANDLE
        # ====================================================

        latest = -2

        price = float(
            close.iloc[latest]
        )

        jaw_value = float(
            jaw.iloc[latest]
        )

        teeth_value = float(
            teeth.iloc[latest]
        )

        lips_value = float(
            lips.iloc[latest]
        )

        rsi_value = float(
            rsi.iloc[latest]
        )

        # ====================================================
        # ALLIGATOR DIRECTION
        # ====================================================

        bullish_alligator = (
            lips_value > teeth_value
            and teeth_value > jaw_value
            and price > lips_value
        )

        bearish_alligator = (
            lips_value < teeth_value
            and teeth_value < jaw_value
            and price < lips_value
        )

        # ====================================================
        # RSI CONFIRMATION
        # ====================================================

        bullish_rsi = rsi_value >= 55

        bearish_rsi = rsi_value <= 45

        # ====================================================
        # SIGNAL
        # ====================================================

        signal = None

        if bullish_alligator and bullish_rsi:

            signal = "CALL"

        elif bearish_alligator and bearish_rsi:

            signal = "PUT"

        # ====================================================
        # CONSOLE
        # ====================================================

        if signal:

            print(
                f"{pair_name:<10} | "
                f"{signal:<4} | "
                f"RSI {rsi_value:.1f} | "
                f"Alligator CONFIRMED"
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
            "rsi": rsi_value
        }

    except Exception as e:

        print(
            f"Analysis error {pair_name}: {e}"
        )

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
            f"🕐 وقت الدخول: "
            f"{entry_time.strftime('%H:%M')}\n"
            f"⏳ مدة الصفقة: "
            f"{ENTRY_DURATION} دقائق\n\n"
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

        message = build_telegram_message(
            signals
        )

        if message:

            send_telegram(
                message
            )

    else:

        print(
            "No complete signals."
        )

    print(
        "=============================================="
    )


# ============================================================
# STARTUP
# ============================================================

def startup():

    print()
    print("==============================================")
    print("       FOREX SIGNAL PRO")
    print("       ALLIGATOR + RSI")
    print("==============================================")

    print(
        f"Timeframe: {TIMEFRAME}"
    )

    print(
        f"Scan interval: {SCAN_INTERVAL} seconds"
    )

    print(
        f"Entry duration: {ENTRY_DURATION} minutes"
    )

    print(
        "Strategy: Alligator + RSI"
    )

    if (
        TELEGRAM_BOT_TOKEN
        and TELEGRAM_CHAT_ID
    ):

        print(
            "Telegram: Enabled"
        )

        send_telegram(
            "🚀 FOREX SIGNAL PRO\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ البوت يعمل الآن\n"
            "📊 Strategy: Alligator + RSI\n"
            "⏱ Timeframe: 5m\n"
            "⏳ مدة الصفقة المقترحة: 5 دقائق"
        )

    else:

        print(
            "Telegram: Disabled"
        )

    print(
        "=============================================="
    )

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
                f"Next scan in "
                f"{SCAN_INTERVAL} seconds..."
            )

            time.sleep(
                SCAN_INTERVAL
            )

        except KeyboardInterrupt:

            print()
            print(
                "Bot stopped."
            )

            break

        except Exception as e:

            print(
                "Main loop error:",
                e
            )

            print(
                "Retrying in 30 seconds..."
            )

            time.sleep(30)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
