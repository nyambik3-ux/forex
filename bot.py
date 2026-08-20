import json
import os
import warnings
import pandas as pd
import requests
import yfinance as yf

# Menggunakan library 'ta' standar
from ta.volatility import BollingerBands, AverageTrueRange
from ta.trend import SMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator

from google import genai
from google.genai import types

warnings.filterwarnings("ignore")

# ==========================================
# KONFIGURASI (MEMBACA DARI GITHUB SECRETS)
# ==========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TOKEN_TELEGRAM = os.getenv("TOKEN_TELEGRAM")
CHAT_ID_TELEGRAM = os.getenv("CHAT_ID_TELEGRAM")

STOCK_POOL = ["BRMS.JK", "ASLI.JK", "PYFA.JK", "SGER.JK", "TRIN.JK", "CASH.JK", "DOOH.JK"]

if not GEMINI_API_KEY:
    print("❌ FATAL: GEMINI_API_KEY tidak ditemukan di GitHub Secrets!")
    exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)


def kirim_telegram(pesan):
    if not TOKEN_TELEGRAM or not CHAT_ID_TELEGRAM:
        print("⚠️ Token / Chat ID Telegram belum diatur.")
        return

    try:
        url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
        payload = {
            "chat_id": CHAT_ID_TELEGRAM,
            "text": pesan,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"❌ Error Telegram: {e}")


def minta_analisa_gemini(ticker, open_price, close_prev, pivot, rsi, sma20, bb_upper, bb_lower, adx, atr, is_bullish):
    prompt = f"""
    Bertindaklah sebagai Senior Scalper Saham IDX. Analisa data teknikal komprehensif berikut:
    - Saham: {ticker}
    - Harga Open Hari Ini: Rp{open_price}
    - Closing Kemarin: Rp{close_prev}
    - Level Pivot: Rp{pivot}
    - RSI (14): {rsi:.1f}
    - SMA20: {sma20:.1f}
    - Bollinger Upper Band: Rp{bb_upper:.1f}
    - Bollinger Lower Band: Rp{bb_lower:.1f}
    - ADX (Kekuatan Tren): {adx:.1f} (Nilai > 25 menandakan tren kuat)
    - ATR (14): {atr:.1f}
    - Candle Bullish Kuat: {is_bullish}

    Berikan analisa singkat 2 kalimat dengan mempertimbangkan posisi harga Open terhadap Pivot & Bollinger Bands serta kekuatan tren ADX.
    Kembalikan respon DALAM FORMAT JSON SAJA:
    {{
      "rekomendasi": "HAKA" / "ANTRE" / "SKIP",
      "alasan": "Penjelasan singkat maksimal 2 kalimat",
      "target_tp": {int(pivot * 1.03)},
      "batas_sl": {int(pivot * 0.97)}
    }}
    """

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"❌ Error Gemini ({ticker}): {e}")
        return None


def run_gemini_screener():
    print("=== BOT PREMARKET GEMINI STARTED ===\n")

    tickers_str = " ".join(STOCK_POOL)
    raw_data = yf.download(tickers_str, period="1mo", interval="1d", group_by="ticker", threads=True)

    pesan_rekap = "🤖 <b>PREMARKET ANALYSIS (BB + ADX)</b> 🤖\n" + "━" * 32 + "\n\n"
    ada_hasil = False

    for ticker in STOCK_POOL:
        try:
            df = raw_data[ticker].dropna() if len(STOCK_POOL) > 1 else raw_data.dropna()
            if len(df) < 20:
                continue

            # Ambil Data Harga
            open_price = float(df["Open"].iloc[-1])
            close_prev = float(df["Close"].iloc[-2])
            high_prev = float(df["High"].iloc[-2])
            low_prev = float(df["Low"].iloc[-2])

            # Kalkulasi Indikator Menggunakan 'ta'
            rsi_indicator = RSIIndicator(close=df["Close"], window=14)
            sma_indicator = SMAIndicator(close=df["Close"], window=20)
            atr_indicator = AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"], window=14)
            bb_indicator = BollingerBands(close=df["Close"], window=20, window_dev=2)
            adx_indicator = ADXIndicator(high=df["High"], low=df["Low"], close=df["Close"], window=14)

            df["RSI"] = rsi_indicator.rsi()
            df["SMA20"] = sma_indicator.sma_indicator()
            df["ATR"] = atr_indicator.average_true_range()
            df["BB_Upper"] = bb_indicator.bollinger_hband()
            df["BB_Lower"] = bb_indicator.bollinger_lband()
            df["ADX"] = adx_indicator.adx()

            # Nilai Terbaru
            rsi = float(df["RSI"].iloc[-2])
            sma20 = float(df["SMA20"].iloc[-2])
            atr = float(df["ATR"].iloc[-2])
            bb_upper = float(df["BB_Upper"].iloc[-2])
            bb_lower = float(df["BB_Lower"].iloc[-2])
            adx = float(df["ADX"].iloc[-2])

            pivot = (high_prev + low_prev + close_prev) / 3
            is_bullish = close_prev >= (high_prev - (high_prev - low_prev) * 0.3)

            kode_saham = ticker.replace(".JK", "")
            print(f"🤖 Menganalisa {kode_saham}...")

            ai_result = minta_analisa_gemini(
                kode_saham, open_price, close_prev, pivot, rsi, sma20, bb_upper, bb_lower, adx, atr, is_bullish
            )

            if ai_result:
                status = ai_result.get("rekomendasi", "SKIP")
                alasan = ai_result.get("alasan", "-")
                tp = ai_result.get("target_tp", 0)
                sl = ai_result.get("batas_sl", 0)

                icon = "🔥" if status == "HAKA" else ("👀" if status == "ANTRE" else "❌")

                pesan_rekap += (
                    f"{icon} <b>[{kode_saham}]</b> -> Status: <b>{status}</b>\n"
                    f"├ 💵 Open: <b>Rp{int(open_price)}</b> | Prev Close: Rp{int(close_prev)}\n"
                    f"├ 📊 ADX: {adx:.1f} | BB Upper: Rp{int(bb_upper)}\n"
                    f"├ 💡 <i>{alasan}</i>\n"
                    f"├ 🎯 TP: Rp{tp}\n"
                    f"└ 🛡️ SL: Rp{sl}\n\n"
                )
                ada_hasil = True

        except Exception as e:
            print(f"Error olah data {ticker}: {e}")
            continue

    if ada_hasil:
        kirim_telegram(pesan_rekap)
        print("✅ Seluruh analisa berhasil dikirim ke Telegram!")

if __name__ == "__main__":
    run_gemini_screener()
