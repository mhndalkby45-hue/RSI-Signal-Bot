import time
import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator


# ============================================================
# FOREX SIGNAL PRO
# RSI + EMA + MACD
# TIMEFRAME: 5 MINUTES
# TELEGRAM NOTIFICATIONS
# ============================================================

BOT_NAME = "Forex Signal Pro"

TIMEFRAME = "5m"
DATA_PERIOD = "5d"

PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "AUD/USD": "AUDUSD=X",
    "USD/JPY": "JPY=X",
    "USD/CAD": "CAD=X",
    "USD/CHF": "CHF=X",
    "NZD/USD": "NZDUSD=X",
}

SCAN_INTERVAL = 300  # 5 minutes


# ============================================================
# TELEGRAM SETTINGS
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram settings not found.")
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
            data=payload,
            timeout=15
        )

        if response.ok:
            print("Telegram notification sent.")
            return True

        print(
            "Telegram error:",
            response.status_code,
            response.text
        )

        return False

    except Exception as e:

        print(
            "Telegram connection error:",
            e
        )

        return False


# ============================================================
# GET MARKET DATA
# ============================================================

def get_data(symbol):

    try:

        data = yf.download(
            symbol,
            period=DATA_PERIOD,
            interval=TIMEFRAME,
            progress=False,
            auto_adjust=False,
            threads=False
        )

        if data is None or data.empty:
            return None

        # Handle yfinance MultiIndex columns
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        required = [
            "Open",
            "High",
            "Low",
            "Close"
        ]

        for column in required:

            if column not in data.columns:
                return None

        data = data.dropna().copy()

        if len(data) < 50:
            return None

        return data

    except Exception as e:

        print(
            f"Data error for {symbol}: {e}"
        )

        return None


# ============================================================
# ANALYZE PAIR
# ============================================================

def analyze_pair(pair_name, symbol):

    data = get_data(symbol)

    if data is None:

        return {
            "pair": pair_name,
            "signal": "NO DATA"
        }

    try:

        close = data["Close"]

        # -----------------------------
        # EMA
        # -----------------------------

        ema20 = EMAIndicator(
            close=close,
            window=20
        ).ema_indicator()

        ema50 = EMAIndicator(
            close=close,
            window=50
        ).ema_indicator()

        # -----------------------------
        # RSI
        # -----------------------------

        rsi = RSIIndicator(
            close=close,
            window=14
        ).rsi()

        # -----------------------------
        # MACD
        # -----------------------------

        macd_indicator = MACD(
            close=close,
            window_slow=26,
            window_fast=12,
            window_sign=9
        )

        macd = macd_indicator.macd()
        signal_line = macd_indicator.macd_signal()

        # Latest completed candle
        latest = -2

        price = float(close.iloc[latest])
        ema20_value = float(
            ema20.iloc[latest]
        )
        ema50_value = float(
            ema50.iloc[latest]
        )
        rsi_value = float(
            rsi.iloc[latest]
        )
        macd_value = float(
            macd.iloc[latest]
        )
        signal_value = float(
            signal_line.iloc[latest]
        )

        # ====================================================
        # SIGNAL LOGIC
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
            macd_value > signal_value
        )

        bearish_macd = (
            macd_value < signal_value
        )

        # CALL
        call_conditions = 0

        if bullish_ema:
            call_conditions += 1

        if rsi_value > 50:
            call_conditions += 1

        if bullish_macd:
            call_conditions += 1

        # PUT
        put_conditions = 0

        if bearish_ema:
            put_conditions += 1

        if rsi_value < 50:
            put_conditions += 1

        if bearish_macd:
            put_conditions += 1

        # ====================================================
        # FINAL SIGNAL
        # ====================================================

        if call_conditions == 3:

            signal = "CALL"

        elif put_conditions == 3:

            signal = "PUT"

        else:

            signal = "WAIT"

        return {
            "pair": pair_name,
            "signal": signal,
            "price": price,
            "rsi": rsi_value,
            "ema20": ema20_value,
            "ema50": ema50_value,
            "macd": macd_value,
            "macd_signal": signal_value,
            "call_score": call_conditions,
            "put_score": put_conditions
        }

    except Exception as e:

        print(
            f"Analysis error for {pair_name}: {e}"
        )

        return {
            "pair": pair_name,
            "signal": "ERROR"
        }


# ============================================================
# DISPLAY RESULT
# ============================================================

def print_result(result):

    pair = result["pair"]
    signal = result["signal"]

    if signal in [
        "NO DATA",
        "ERROR"
    ]:

        print(
            f"{pair:<10} | {signal}"
        )

        return

    print(
        f"{pair:<10} | "
        f"RSI {result['rsi']:5.1f} | "
        f"EMA20 {result['ema20']:.5f} | "
        f"EMA50 {result['ema50']:.5f} | "
        f"MACD {result['macd']:.5f} | "
        f"{signal}"
    )


# ============================================================
# BUILD TELEGRAM MESSAGE
# ============================================================

def build_telegram_message(signals):

    now = datetime.now(
        ZoneInfo("Asia/Baghdad")
    )

    message = (
        "📊 FOREX SIGNAL PRO\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⏱ Timeframe: {TIMEFRAME}\n\n"
    )

    if not signals:

        message += "⏸ No complete signals this scan."

        return message

    message += "🚨 SIGNALS\n\n"

    for result in signals:

        if result["signal"] == "CALL":
            icon = "🟢"
        else:
            icon = "🔴"

        message += (
            f"{icon} {result['pair']} → "
            f"{result['signal']}\n"
            f"RSI: {result['rsi']:.1f}\n"
            f"EMA20: {result['ema20']:.5f}\n"
            f"EMA50: {result['ema50']:.5f}\n"
            f"MACD: {result['macd']:.5f}\n"
            f"Score: "
            f"{result['call_score'] if result['signal'] == 'CALL' else result['put_score']}/3\n\n"
        )

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "⚠️ Signal only — not financial advice."
    )

    return message


# ============================================================
# MAIN SCAN
# ============================================================

def scan_market():

    print()
    print("=" * 75)
    print(BOT_NAME)
    print("=" * 75)

    now = datetime.now(
        ZoneInfo("Asia/Baghdad")
    )

    print(
        "Scan time:",
        now.strftime("%Y-%m-%d %H:%M:%S")
    )

    print("-" * 75)

    signals = []

    for pair_name, symbol in PAIRS.items():

        result = analyze_pair(
            pair_name,
            symbol
        )

        print_result(result)

        if result["signal"] in [
            "CALL",
            "PUT"
        ]:

            signals.append(result)

        # Small delay to avoid requests too quickly
        time.sleep(1)

    print("-" * 75)

    if signals:

        print("STRONG SIGNALS:")

        for result in signals:

            print(
                f">>> {result['pair']} : "
                f"{result['signal']} "
                f"(RSI {result['rsi']:.1f})"
            )

    else:

        print(
            "No complete signal at this scan."
        )

    # ========================================================
    # SEND TELEGRAM
    # ========================================================

    telegram_message = build_telegram_message(
        signals
    )

    send_telegram(
        telegram_message
    )

    print("=" * 75)


# ============================================================
# RUN BOT
# ============================================================

def main():

    print()
    print("=" * 75)
    print(f"{BOT_NAME} STARTED")
    print("=" * 75)
    print(f"Timeframe: {TIMEFRAME}")
    print(f"Pairs: {len(PAIRS)}")
    print(
        "Telegram:",
        "Enabled"
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
        else "NOT CONFIGURED"
    )
    print("=" * 75)

    while True:

        try:

            scan_market()

            print()
            print(
                "Next scan in 5 minutes..."
            )
            print()

            time.sleep(
                SCAN_INTERVAL
            )

        except KeyboardInterrupt:

            print()
            print("Bot stopped.")
            break

        except Exception as e:

            print()
            print(
                "Unexpected error:",
                e
            )

            print(
                "Restarting in 30 seconds..."
            )

            time.sleep(30)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
