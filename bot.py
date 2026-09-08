import json
import os
import time
import warnings
import pandas as pd
import requests
import yfinance as yf

from groq import Groq
from ta.trend import SMAIndicator, MACD
from ta.momentum import RSIIndicator

warnings.filterwarnings("ignore")

# ==========================================
# KONFIGURASI DARI GITHUB SECRETS
# ==========================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TOKEN_TELEGRAM = os.getenv("TOKEN_TELEGRAM")
CHAT_ID_TELEGRAM = os.getenv("CHAT_ID_TELEGRAM")

# Stock Pool difokuskan ke saham Blue Chip / Core Holding
STOCK_POOL = [
    "BBRI.JK", "BMRI.JK", "BBCA.JK", "TLKM.JK", "ASII.JK", 
    "BRIS.JK", "UNVR.JK", "AMRT.JK", "PGAS.JK", "ICBP.JK"
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

def minta_analisa_groq(ticker, close_price, sma50, sma200, rsi_weekly, macd_hist, trend_status):
    prompt = f"""
    Bertindaklah sebagai Senior Position Trader & Value Investor Saham IDX.
    Analisa data teknikal mingguan (Weekly) saham berikut:
    - Saham: {ticker} | Harga Terakhir: Rp{int(close_price)}
    - SMA 50 Weekly: Rp{int(sma50)} | SMA 200 Weekly: Rp{int(sma200)}
    - Weekly RSI (14): {rsi_weekly:.1f}
    - Weekly MACD Histogram: {macd_hist:.2f}
    - Tren Struktural: {trend_status}

    Berikan analisa perspektif investasi/swing jangka panjang (3-12 bulan) maksimal 2 kalimat.
    WAJIB KEMBALIKAN DALAM FORMAT JSON MURNI SEPERTI INI:
    {{
      "rekomendasi": "AKUMULASI",
      "alasan": "Tulis alasan teknikal jangka panjang di sini",
      "target_tp": {int(close_price * 1.15)},
      "batas_sl": {int(close_price * 0.90)}
    }}
    Nilai rekomendasi HANYA boleh salah satu dari: "AKUMULASI", "HOLD", atau "AVOID".
    """

    candidate_models = [
        "llama-3.3-70b-versatile",
        "llama3-70b-8192",
        "mixtral-8x7b-32768"
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
    print("=== BOT POSITION TRADING / INVESTASI STARTED ===")
    tickers_str = " ".join(STOCK_POOL)
    
    # Ambil data MINGGUAN (1wk) rentang 3 Tahun untuk menghitung MA200 secara akurat
    raw_data = yf.download(tickers_str, period="3y", interval="1wk", group_by="ticker", threads=True)

    pesan_rekap = "🏛️ <b>WEEKLY POSITION & INVEST ANALYSIS</b> 🏛️\n" + "━" * 32 + "\n\n"

    for ticker in STOCK_POOL:
        kode_saham = ticker.replace(".JK", "")
        try:
            df = raw_data[ticker].dropna() if len(STOCK_POOL) > 1 else raw_data.dropna()
            
            if len(df) < 50:
                print(f"⚠️ Data {kode_saham} kurang dari 50 minggu, skipped.")
                continue

            close_prev = float(df["Close"].iloc[-1])

            # Indikator Jarak Jauh (Weekly)
            df["SMA50"] = SMAIndicator(close=df["Close"], window=50).sma_indicator()
            
            # Jika data kurang untuk MA200, gunakan SMA100 sebagai cadangan
            if len(df) >= 200:
                df["SMA200"] = SMAIndicator(close=df["Close"], window=200).sma_indicator()
                sma200 = float(df["SMA200"].iloc[-1]) if not pd.isna(df["SMA200"].iloc[-1]) else close_prev
            else:
                sma200 = float(df["SMA50"].iloc[-1])

            df["RSI"] = RSIIndicator(close=df["Close"], window=14).rsi()
            macd_obj = MACD(close=df["Close"])
            df["MACD_Hist"] = macd_obj.macd_diff()

            sma50 = float(df["SMA50"].iloc[-1]) if not pd.isna(df["SMA50"].iloc[-1]) else close_prev
            rsi = float(df["RSI"].iloc[-1]) if not pd.isna(df["RSI"].iloc[-1]) else 50.0
            macd_hist = float(df["MACD_Hist"].iloc[-1]) if not pd.isna(df["MACD_Hist"].iloc[-1]) else 0.0

            # Penentuan Status Tren Utama
            if close_prev > sma50 and sma50 > sma200:
                trend_status = "BULLISH UPTREND (Strong)"
            elif close_prev > sma50:
                trend_status = "RECOVERY / EARLY UPTREND"
            else:
                trend_status = "DOWNTREND / DANGER ZONE"

            print(f"🤖 Menganalisa {kode_saham} (Weekly)...")

            ai_result = minta_analisa_groq(
                kode_saham, close_prev, sma50, sma200, rsi, macd_hist, trend_status
            )

            time.sleep(1.5)

            if ai_result:
                status = ai_result.get("rekomendasi", "HOLD")
                alasan = ai_result.get("alasan", "-")
                tp = ai_result.get("target_tp", int(close_prev * 1.15))
                sl = ai_result.get("batas_sl", int(close_prev * 0.90))
            else:
                status = "HOLD"
                alasan = "Gagal memproses respon AI"
                tp = int(close_prev * 1.15)
                sl = int(close_prev * 0.90)

            icon = "🟢" if status == "AKUMULASI" else ("🟡" if status == "HOLD" else "🔴")

            pesan_rekap += (
                f"{icon} <b>[{kode_saham}]</b> -> Rating: <b>{status}</b>\n"
                f"├ 💵 Close: <b>Rp{int(close_prev)}</b> | Tren: {trend_status}\n"
                f"├ 📊 Weekly RSI: {rsi:.1f} | SMA50: Rp{int(sma50)}\n"
                f"├ 💡 <i>{alasan}</i>\n"
                f"├ 🎯 Target TP (Long): Rp{tp}\n"
                f"└ 🛡️ Batas Safe SL: Rp{sl}\n\n"
            )

        except Exception as e:
            print(f"❌ Error olah data {kode_saham}: {e}")
            continue

    kirim_telegram(pesan_rekap)
    print("✅ Seluruh analisa mingguan dikirim ke Telegram!")

if __name__ == "__main__":
    run_screener()
