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
GEMINI_API_KEY = os.getenv("AQ.Ab8RN6KSmukz2n4E4a62FY7uL-5z4cnc5Nll2PTpE2V3-IhWpA")
TOKEN_TELEGRAM = os.getenv("8938108866:AAGNEcXVXClll-C8EGSQP61mwkjqKLXW6Tw")
CHAT_ID_TELEGRAM = os.getenv("8014458366")

STOCK_POOL = ["BRMS.JK", "ASLI.JK", "PYFA.JK", "SGER.JK", "TRIN.JK"]

# Inisialisasi Client Gemini SDK
client = genai.Client(api_key=GEMINI_API_KEY)


def kirim_telegram(pesan):
  """Kirim pesan format rapi ke Telegram"""
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
    print(f"❌ Gagal kirim Telegram: {e}")


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
    - ADX (Kekuatan Tren): {adx:.1f} (Nilai > 25 menandakan tren kuat)
    - ATR (14): {atr:.1f}
    - Candle Bullish Kuat: {is_bullish}

    Berikan analisa singkat 2 kalimat dengan mempertimbangkan posisi harga Open terhadap Pivot & Bollinger Bands serta kekuatan tren ADX.
    Kembalikan respon DALAM FORMAT JSON SAJA seperti ini:
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
  print("=== BOT PREMARKET GEMINI (BB + ADX FIXED) STARTED ===\n")

  tickers_str = " ".join(STOCK_POOL)
  raw_data = yf.download(
      tickers_str, period="1mo", interval="1d", group_by="ticker", threads=True
  )

  pesan_rekap = (
      "🤖 <b>PREMARKET ANALYSIS (BB + ADX)</b> 🤖\n" + "━" * 32 + "\n\n"
  )

  for ticker in STOCK_POOL:
    try:
      df = (
          raw_data[ticker].dropna()
          if len(STOCK_POOL) > 1
          else raw_data.dropna()
      )
      if len(df) < 20:
        continue

      # Ambil Data Harga
      open_price = float(df["Open"].iloc[-1])
      close_prev = float(df["Close"].iloc[-2])
      high_prev = float(df["High"].iloc[-2])
      low_prev = float(df["Low"].iloc[-2])

      # Indikator Dasar
      df["RSI"] = ta.rsi(df["Close"], length=14)
      df["SMA20"] = ta.sma(df["Close"], length=20)
      df["ATR"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)

      # Indikator Bollinger Bands
      bb = ta.bbands(df["Close"], length=20, std=2)
      bb_lower_series = bb.iloc[:, 0]
      bb_upper_series = bb.iloc[:, 2]

      # Indikator ADX
      adx_df = ta.adx(df["High"], df["Low"], df["Close"], length=14)
      adx_series = adx_df.iloc[:, 0]

      # Nilai Terbaru
      rsi = float(df["RSI"].iloc[-2])
      sma20 = float(df["SMA20"].iloc[-2])
      atr = float(df["ATR"].iloc[-2])
      bb_upper = float(bb_upper_series.iloc[-2])
      bb_lower = float(bb_lower_series.iloc[-2])
      adx = float(adx_series.iloc[-2])

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
            f"├ 💵 Open: <b>Rp{int(open_price)}</b> | Prev Close: Rp{int(close_prev)}\n"
            f"├ 📊 ADX: {adx:.1f} | BB Upper: Rp{int(bb_upper)}\n"
            f"├ 💡 <i>{alasan}</i>\n"
            f"├ 🎯 TP: Rp{tp}\n"
            f"└ 🛡️ SL: Rp{sl}\n\n"
        )

    except Exception as e:
      print(f"Error olah data {ticker}: {e}")
      continue

  # Kirim Rangkuman ke Telegram
  kirim_telegram(pesan_rekap)
  print("✅ Seluruh analisa berhasil dikirim ke Telegram!")


if __name__ == "__main__":
  run_gemini_screener()
