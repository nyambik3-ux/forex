import json
import os
import warnings
import pandas_ta as ta
import requests
import yfinance as yf
from google import genai
from google.genai import types

warnings.filterwarnings("ignore")

# ==========================================
# KONFIGURASI (MEMBACA DARI GITHUB SECRETS)
# ==========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TOKEN_TELEGRAM = os.getenv("TOKEN_TELEGRAM")
CHAT_ID_TELEGRAM = os.getenv("CHAT_ID_TELEGRAM")

STOCK_POOL = ["BRMS.JK", "ASLI.JK", "PYFA.JK", "SGER.JK", "TRIN.JK"]

if not GEMINI_API_KEY:
  print(
      "❌ FATAL ERROR: GEMINI_API_KEY tidak ditemukan! Cek kembali GitHub"
      " Secrets."
  )
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
    res = requests.post(url, data=payload, timeout=10)
    print(f"Status Telegram: {res.status_code}")
  except Exception as e:
    print(f"❌ Error request Telegram: {e}")


def minta_analisa_gemini(
    ticker,
    open_price,
    close_prev,
    pivot,
    rsi,
    sma20,
    bb_upper,
    bb_lower,
    adx,
    atr,
    is_bullish,
):
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
    - ADX (Kekuatan Tren): {adx:.1f}
    - ATR (14): {atr:.1f}
    - Candle Bullish Kuat: {is_bullish}

    Berikan analisa singkat 2 kalimat. Kembalikan respon DALAM FORMAT JSON SAJA:
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
  raw_data = yf.download(
      tickers_str, period="1mo", interval="1d", group_by="ticker", threads=True
  )

  pesan_rekap = (
      "🤖 <b>PREMARKET ANALYSIS (BB + ADX)</b> 🤖\n" + "━" * 32 + "\n\n"
  )
  ada_hasil = False

  for ticker in STOCK_POOL:
    try:
      df = (
          raw_data[ticker].dropna()
          if len(STOCK_POOL) > 1
          else raw_data.dropna()
      )
      if len(df) < 20:
        continue

      open_price = float(df["Open"].iloc[-1])
      close_prev = float(df["Close"].iloc[-2])
      high_prev = float(df["High"].iloc[-2])
      low_prev = float(df["Low"].iloc[-2])

      df["RSI"] = ta.rsi(df["Close"], length=14)
      df["SMA20"] = ta.sma(df["Close"], length=20)
      df["ATR"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)

      bb = ta.bbands(df["Close"], length=20, std=2)
      adx_df = ta.adx(df["High"], df["Low"], df["Close"], length=14)

      rsi = float(df["RSI"].iloc[-2])
      sma20 = float(df["SMA20"].iloc[-2])
      atr = float(df["ATR"].iloc[-2])
      bb_lower = float(bb.iloc[-2, 0])
      bb_upper = float(bb.iloc[-2, 2])
      adx = float(adx_df.iloc[-2, 0])

      pivot = (high_prev + low_prev + close_prev) / 3
      is_bullish = close_prev >= (high_prev - (high_prev - low_prev) * 0.3)

      kode_saham = ticker.replace(".JK", "")
      print(f"🤖 Menganalisa {kode_saham}...")

      ai_result = minta_analisa_gemini(
          kode_saham,
          open_price,
          close_prev,
          pivot,
          rsi,
          sma20,
          bb_upper,
          bb_lower,
          adx,
          atr,
          is_bullish,
      )

      if ai_result:
        status = ai_result.get("rekomendasi", "SKIP")
        alasan = ai_result.get("alasan", "-")
        tp = ai_result.get("target_tp", 0)
        sl = ai_result.get("batas_sl", 0)

        icon = "🔥" if status == "HAKA" else ("👀" if status == "ANTRE" else "❌")

        pesan_rekap += (
            f"{icon} <b>[{kode_saham}]</b> -> Status: <b>{status}</b>\n"
            f"├ 💵 Open: <b>Rp{int(open_price)}</b> | Prev Close:"
            f" Rp{int(close_prev)}\n"
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
