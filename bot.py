import json
import os
import time
import warnings
import pandas as pd
import requests
import yfinance as yf

from groq import Groq
from ta.volatility import BollingerBands, AverageTrueRange
from ta.trend import SMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator

warnings.filterwarnings("ignore")

# ==========================================
# KONFIGURASI DARI GITHUB SECRETS
# ==========================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TOKEN_TELEGRAM = os.getenv("TOKEN_TELEGRAM")
CHAT_ID_TELEGRAM = os.getenv("CHAT_ID_TELEGRAM")

STOCK_POOL = [
    "BRMS.JK", "ASLI.JK", "PYFA.JK", "SGER.JK",
    "TRIN.JK", "CASH.JK", "DOOH.JK"
]

client = Groq(api_key=GROQ_API_KEY)

def kirim_telegram(pesan):
    try:
        url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
        payload = {
            "chat_id": CHAT_ID_TELEGRAM,
            "text": pesan,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"❌ Gagal kirim Telegram: {e}")

def minta_analisa_groq(ticker, open_price, close_prev, pivot, rsi, sma20, bb_upper, bb_lower, adx, atr, is_bullish):
    prompt = f"""
    Bertindaklah sebagai Senior Scalper Saham IDX. Analisa data teknikal berikut:
    - Saham: {ticker} | Open: Rp{open_price} | Prev Close: Rp{close_prev} | Pivot: Rp{pivot}
    - RSI: {rsi:.1f} | SMA20: {sma20:.1f} | BB Upper: Rp{bb_upper:.1f} | BB Lower: Rp{bb_lower:.1f}
    - ADX: {adx:.1f} | ATR: {atr:.1f} | Bullish Candle: {is_bullish}

    Berikan analisa singkat maksimal 2 kalimat.
    WAJIB KEMBALIKAN DALAM FORMAT JSON MURNI SEPERTI INI:
    {{
      "rekomendasi": "HAKA",
      "alasan": "Tulis alasan singkat di sini",
      "target_tp": {int(pivot * 1.03)},
      "batas_sl": {int(pivot * 0.97)}
    }}
    Nilai rekomendasi HANYA boleh salah satu dari: "HAKA", "ANTRE", atau "SKIP".
    """

    candidate_models = [
        "groq/compound",
        "groq/compound-mini",
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b"
    ]

    for model_name in candidate_models:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a stock analyst API. You MUST reply with a valid JSON object ONLY. No markdown, no prose."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            res_text = response.choices[0].message.content.strip()
            return json.loads(res_text)
        except Exception as e:
            continue

    return None

def run_screener():
    print("=== BOT PREMARKET GROQ STARTED ===")
    tickers_str = " ".join(STOCK_POOL)
    raw_data = yf.download(tickers_str, period="3mo", interval="1d", group_by="ticker", threads=True)

    pesan_rekap = "🤖 <b>PREMARKET ANALYSIS (GROQ AI)</b> 🤖\n" + "━" * 32 + "\n\n"

    for ticker in STOCK_POOL:
        kode_saham = ticker.replace(".JK", "")
        try:
            df = raw_data[ticker].dropna() if len(STOCK_POOL) > 1 else raw_data.dropna()
            
            if len(df) < 10:
                print(f"⚠️ Data {kode_saham} terlalu sedikit, skipped.")
                continue

            open_price = float(df["Open"].iloc[-1])
            close_prev = float(df["Close"].iloc[-2])
            high_prev = float(df["High"].iloc[-2])
            low_prev = float(df["Low"].iloc[-2])

            df["RSI"] = RSIIndicator(close=df["Close"], window=14).rsi()
            df["SMA20"] = SMAIndicator(close=df["Close"], window=20).sma_indicator()
            df["ATR"] = AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"], window=14).average_true_range()
            
            bb = BollingerBands(close=df["Close"], window=20, window_dev=2)
            df["BB_Upper"] = bb.bollinger_hband()
            df["BB_Lower"] = bb.bollinger_lband()
            df["ADX"] = ADXIndicator(high=df["High"], low=df["Low"], close=df["Close"], window=14).adx()

            rsi = float(df["RSI"].iloc[-2]) if not pd.isna(df["RSI"].iloc[-2]) else 50.0
            sma20 = float(df["SMA20"].iloc[-2]) if not pd.isna(df["SMA20"].iloc[-2]) else close_prev
            atr = float(df["ATR"].iloc[-2]) if not pd.isna(df["ATR"].iloc[-2]) else 0.0
            bb_upper = float(df["BB_Upper"].iloc[-2]) if not pd.isna(df["BB_Upper"].iloc[-2]) else close_prev
            bb_lower = float(df["BB_Lower"].iloc[-2]) if not pd.isna(df["BB_Lower"].iloc[-2]) else close_prev
            adx = float(df["ADX"].iloc[-2]) if not pd.isna(df["ADX"].iloc[-2]) else 0.0

            pivot = (high_prev + low_prev + close_prev) / 3
            is_bullish = close_prev >= (high_prev - (high_prev - low_prev) * 0.3)

            print(f"🤖 Menganalisa {kode_saham}...")

            ai_result = minta_analisa_groq(
                kode_saham, open_price, close_prev, pivot, rsi, sma20, bb_upper, bb_lower, adx, atr, is_bullish
            )

            time.sleep(1.5)

            if ai_result:
                status = ai_result.get("rekomendasi", "SKIP")
                alasan = ai_result.get("alasan", "-")
                tp = ai_result.get("target_tp", int(pivot * 1.03))
                sl = ai_result.get("batas_sl", int(pivot * 0.97))
            else:
                status = "SKIP"
                alasan = "Gagal memproses respon AI"
                tp = int(pivot * 1.03)
                sl = int(pivot * 0.97)

            icon = "🔥" if status == "HAKA" else ("👀" if status == "ANTRE" else "❌")

            pesan_rekap += (
                f"{icon} <b>[{kode_saham}]</b> -> Status: <b>{status}</b>\n"
                f"├ 💵 Open: <b>Rp{int(open_price)}</b> | Prev Close: Rp{int(close_prev)}\n"
                f"├ 📊 ADX: {adx:.1f} | BB Upper: Rp{int(bb_upper)}\n"
                f"├ 💡 <i>{alasan}</i>\n"
                f"├ 🎯 TP: Rp{tp}\n"
                f"└ 🛡️ SL: Rp{sl}\n\n"
            )

        except Exception as e:
            print(f"❌ Error olah data {kode_saham}: {e}")
            continue

    kirim_telegram(pesan_rekap)
    print("✅ Seluruh analisa dikirim ke Telegram!")

if __name__ == "__main__":
    run_screener()
