import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
import requests


# ============================================================
# FOREX SIGNAL PRO
# SUPERTREND + RSI
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
# INDICATOR SETTINGS
# ============================================================

RSI_PERIOD = 14

SUPERTREND_ATR_PERIOD = 10
SUPERTREND_MULTIPLIER = 2.0


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:

        print("Telegram: NOT CONFIGURED")

        return

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

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

            print(
                "Telegram error:",
                response.text
            )

    except Exception as e:

        print(
            "Telegram error:",
            e
        )


# ============================================================
# RSI
# ============================================================

def calculate_rsi(df, period=14):

    delta = df["Close"].diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    average_gain = gain.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    average_loss = loss.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    rs = (
        average_gain /
        average_loss.replace(
            0,
            pd.NA
        )
    )

    df["RSI"] = (
        100 -
        (100 / (1 + rs))
    )

    return df


# ============================================================
# SUPERTREND
# ============================================================

def calculate_supertrend(
    df,
    atr_period=10,
    multiplier=2.0
):

    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    previous_close = close.shift(1)

    tr1 = high - low

    tr2 = (
        high - previous_close
    ).abs()

    tr3 = (
        low - previous_close
    ).abs()

    true_range = pd.concat(
        [
            tr1,
            tr2,
            tr3
        ],
        axis=1
    ).max(axis=1)

    atr = true_range.rolling(
        atr_period
    ).mean()

    hl2 = (
        high + low
    ) / 2

    basic_upper = (
        hl2 +
        multiplier * atr
    )

    basic_lower = (
        hl2 -
        multiplier * atr
    )

    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()

    supertrend = pd.Series(
        index=df.index,
        dtype="float64"
    )

    direction = pd.Series(
        index=df.index,
        dtype="int64"
    )

    for i in range(len(df)):

        if i == 0:

            final_upper.iloc[i] = (
                basic_upper.iloc[i]
            )

            final_lower.iloc[i] = (
                basic_lower.iloc[i]
            )

            supertrend.iloc[i] = (
                basic_upper.iloc[i]
            )

            direction.iloc[i] = -1

            continue

        # ----------------------------------------------------
        # FINAL UPPER BAND
        # ----------------------------------------------------

        if (
            basic_upper.iloc[i]
            < final_upper.iloc[i - 1]
            or
            close.iloc[i - 1]
            > final_upper.iloc[i - 1]
        ):

            final_upper.iloc[i] = (
                basic_upper.iloc[i]
            )

        else:

            final_upper.iloc[i] = (
                final_upper.iloc[i - 1]
            )

        # ----------------------------------------------------
        # FINAL LOWER BAND
        # ----------------------------------------------------

        if (
            basic_lower.iloc[i]
            > final_lower.iloc[i - 1]
            or
            close.iloc[i - 1]
            < final_lower.iloc[i - 1]
        ):

            final_lower.iloc[i] = (
                basic_lower.iloc[i]
            )

        else:

            final_lower.iloc[i] = (
                final_lower.iloc[i - 1]
            )

        # ----------------------------------------------------
        # SUPERTREND DIRECTION
        # ----------------------------------------------------

        previous_supertrend = (
            supertrend.iloc[i - 1]
        )

        if (
            previous_supertrend
            == final_upper.iloc[i - 1]
        ):

            if (
                close.iloc[i]
                <= final_upper.iloc[i]
            ):

                supertrend.iloc[i] = (
                    final_upper.iloc[i]
                )

                direction.iloc[i] = -1

            else:

                supertrend.iloc[i] = (
                    final_lower.iloc[i]
                )

                direction.iloc[i] = 1

        else:

            if (
                close.iloc[i]
                >= final_lower.iloc[i]
            ):

                supertrend.iloc[i] = (
                    final_lower.iloc[i]
                )

                direction.iloc[i] = 1

            else:

                supertrend.iloc[i] = (
                    final_upper.iloc[i]
                )

                direction.iloc[i] = -1

    df["Supertrend"] = supertrend

    df["ST_Direction"] = direction

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

        if isinstance(
            df.columns,
            pd.MultiIndex
        ):

            df.columns = (
                df.columns
                .get_level_values(0)
            )

        required = [
            "Open",
            "High",
            "Low",
            "Close"
        ]

        for column in required:

            if column not in df.columns:

                return None

        df = (
            df[required]
            .dropna()
        )

        if len(df) < 60:

            return None

        return df

    except Exception as e:

        print(
            f"Data error {symbol}: {e}"
        )

        return None


# ============================================================
# ANALYZE PAIR
# ============================================================

def analyze_pair(
    pair_name,
    symbol
):

    df = get_data(symbol)

    if df is None:

        print(
            f"{pair_name:8} | NO DATA"
        )

        return None

    # --------------------------------------------------------
    # CALCULATE INDICATORS
    # --------------------------------------------------------

    df = calculate_rsi(
        df,
        RSI_PERIOD
    )

    df = calculate_supertrend(
        df,
        SUPERTREND_ATR_PERIOD,
        SUPERTREND_MULTIPLIER
    )

    df = df.dropna()

    if len(df) < 20:

        return None

    # --------------------------------------------------------
    # LAST COMPLETED CANDLE
    # --------------------------------------------------------

    current = df.iloc[-2]

    previous = df.iloc[-3]

    rsi = float(
        current["RSI"]
    )

    direction = int(
        current["ST_Direction"]
    )

    previous_direction = int(
        previous["ST_Direction"]
    )

    signal = None

    # ========================================================
    # CALL
    # Supertrend: DOWN -> UP
    # RSI > 50
    # ========================================================

    bullish_reversal = (
        previous_direction == -1
        and
        direction == 1
    )

    bullish_rsi = (
        rsi > 50
    )

    if (
        bullish_reversal
        and
        bullish_rsi
    ):

        signal = "CALL"

    # ========================================================
    # PUT
    # Supertrend: UP -> DOWN
    # RSI < 50
    # ========================================================

    bearish_reversal = (
        previous_direction == 1
        and
        direction == -1
    )

    bearish_rsi = (
        rsi < 50
    )

    if (
        bearish_reversal
        and
        bearish_rsi
    ):

        signal = "PUT"

    # ========================================================
    # DISPLAY
    # ========================================================

    trend = (
        "UP"
        if direction == 1
        else "DOWN"
    )

    if signal:

        print(
            f"{pair_name:8} | "
            f"{signal:4} | "
            f"RSI {rsi:5.1f} | "
            f"Supertrend REVERSAL"
        )

    else:

        print(
            f"{pair_name:8} | "
            f"WAIT | "
            f"RSI {rsi:5.1f} | "
            f"Supertrend {trend}"
        )

    return signal


# ============================================================
# NEXT 5-MINUTE ENTRY TIME
# ============================================================

def get_next_entry_time():

    now = datetime.now(
        ZoneInfo("Asia/Baghdad")
    )

    next_minute = (
        ((now.minute // 5) + 1) * 5
    )

    if next_minute >= 60:

        entry = (
            now.replace(
                minute=0,
                second=0,
                microsecond=0
            )
            +
            timedelta(
                hours=1
            )
        )

    else:

        entry = now.replace(
            minute=next_minute,
            second=0,
            microsecond=0
        )

    return entry


# ============================================================
# SEND SIGNAL
# ============================================================

def send_signal(
    pair,
    signal
):

    entry_time = (
        get_next_entry_time()
    )

    message = (
        "🚨 FOREX SIGNAL PRO\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"💱 {pair} → {signal}\n"
        f"🕐 وقت الدخول: "
        f"{entry_time.strftime('%H:%M')}\n"
        f"⏱️ مدة الصفقة: "
        f"{TRADE_DURATION} دقائق\n\n"
        "📊 Supertrend + RSI"
    )

    print(
        "\n" +
        message +
        "\n"
    )

    send_telegram(
        message
    )


# ============================================================
# STARTUP MESSAGE
# ============================================================

def send_startup():

    message = (
        "🤖 FOREX SIGNAL PRO\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "✅ البوت يعمل الآن\n\n"
        "📊 Strategy: Supertrend + RSI\n"
        "⏱️ Timeframe: 5m\n"
        "⌛ مدة الصفقة: 5 دقائق\n"
        "📈 Supertrend: ATR 10 / Multiplier 2\n"
        "📊 RSI: 14\n"
        "📱 Telegram: Enabled"
    )

    send_telegram(
        message
    )


# ============================================================
# MAIN LOOP
# ============================================================

def main():

    print("=" * 50)

    print(
        "       FOREX SIGNAL PRO"
    )

    print(
        "       SUPERTREND + RSI"
    )

    print("=" * 50)

    print(
        f"Timeframe: {TIMEFRAME}"
    )

    print(
        f"Scan interval: "
        f"{SCAN_INTERVAL} seconds"
    )

    print(
        f"Entry duration: "
        f"{TRADE_DURATION} minutes"
    )

    print(
        "Strategy: Supertrend + RSI"
    )

    print(
        "Supertrend: "
        "ATR 10 / Multiplier 2"
    )

    print(
        "RSI: 14"
    )

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
                now.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
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

                print(
                    "\nNo valid signals."
                )

            print(
                f"\nNext scan in "
                f"{SCAN_INTERVAL // 60} minutes..."
            )

            time.sleep(
                SCAN_INTERVAL
            )

        except KeyboardInterrupt:

            print(
                "\nBot stopped."
            )

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
