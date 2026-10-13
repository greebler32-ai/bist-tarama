from __future__ import annotations

import os
import time
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

from symbols import get_bist_symbols


# --- SECILEBILIR ZAMAN DILIMI ---
_SELECTED_TF = "1d"

def set_timeframe(tf):
    global _SELECTED_TF
    _SELECTED_TF = tf

def _tf_params():
    if _SELECTED_TF == "5m":
        return "60d", "5m"
    if _SELECTED_TF == "15m":
        return "60d", "15m"
    if _SELECTED_TF == "1h":
        return "2y", "1h"
    if _SELECTED_TF == "2h":
        return "2y", "1h"
    if _SELECTED_TF == "4h":
        return "2y", "1h"
    return "1y", "1d"

def _tf_resample(df):
    if _SELECTED_TF not in ("2h", "4h") or df is None or df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    agg = {}
    for c in df.columns:
        if c == "Open":
            agg[c] = "first"
        elif c == "High":
            agg[c] = "max"
        elif c == "Low":
            agg[c] = "min"
        elif c in ("Close", "Adj Close"):
            agg[c] = "last"
        elif c == "Volume":
            agg[c] = "sum"
    if not agg:
        return df
    out = df.resample("2h" if _SELECTED_TF == "2h" else "4h").agg(agg)
    required = [c for c in ["Open", "High", "Low", "Close"] if c in out.columns]
    return out.dropna(subset=required)
# --- /SECILEBILIR ZAMAN DILIMI ---

load_dotenv()

# =========================================================
# VİDEO TARAMASI — AYRI TARAMA
# GÜNLÜK | MA(9) + RSI(14) + WAVETREND CROSS + MA DEVIATION(21)
# Tablo başlıkları mevcut taramayla birebir aynıdır.
# =========================================================

SOURCE_INTERVAL = "1d"
DOWNLOAD_PERIOD = "2y"
MINIMUM_CANDLES = 80
BATCH_SIZE = 60
DOWNLOAD_TIMEOUT_SECONDS = 20
MAX_RESULTS = 20
MINIMUM_SCORE = 60

PRICE_MA_PERIOD = 9
RSI_PERIOD = 14
DEVIATION_PERIOD = 21
WT_CHANNEL_PERIOD = 10
WT_AVERAGE_PERIOD = 21
WT_SIGNAL_PERIOD = 4
WT_OVERSOLD_LEVEL = -60.0
ATR_PERIOD = 14
MOMENTUM_PERIOD = 10

TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def split_batches(items: List[str], size: int) -> Iterable[List[str]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def download_batch(symbols: List[str]) -> pd.DataFrame:
    try:
        return yf.download(
            tickers=symbols,
            period=DOWNLOAD_PERIOD,
            interval=SOURCE_INTERVAL,
            group_by="ticker",
            auto_adjust=False,
            prepost=False,
            progress=False,
            threads=True,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        )
    except Exception as error:
        print(f"İndirme hatası: {error}")
        return pd.DataFrame()


def extract_symbol_data(downloaded: pd.DataFrame, symbol: str, symbol_count: int) -> pd.DataFrame:
    if downloaded is None or downloaded.empty:
        return pd.DataFrame()

    try:
        if isinstance(downloaded.columns, pd.MultiIndex):
            level_0 = downloaded.columns.get_level_values(0)
            level_1 = downloaded.columns.get_level_values(1)
            if symbol in level_0:
                frame = downloaded[symbol].copy()
            elif symbol in level_1:
                frame = downloaded.xs(symbol, axis=1, level=1, drop_level=True).copy()
            else:
                return pd.DataFrame()
        elif symbol_count == 1:
            frame = downloaded.copy()
        else:
            return pd.DataFrame()
    except (KeyError, ValueError):
        return pd.DataFrame()

    required = ["Open", "High", "Low", "Close", "Volume"]
    if any(column not in frame.columns for column in required):
        return pd.DataFrame()

    frame = frame[required].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def calculate_rsi(close: pd.Series, period: int) -> pd.Series:
    change = close.diff()
    gain = change.clip(lower=0.0)
    loss = -change.clip(upper=0.0)
    average_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    average_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = average_gain / average_loss.replace(0, np.nan)
    result = 100.0 - (100.0 / (1.0 + rs))
    result = result.mask((average_loss == 0) & (average_gain > 0), 100.0)
    return result


def calculate_atr(data: pd.DataFrame, period: int) -> pd.Series:
    previous_close = data["Close"].shift(1)
    true_range = pd.concat(
        [
            data["High"] - data["Low"],
            (data["High"] - previous_close).abs(),
            (data["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def add_indicators(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    close = frame["Close"]
    typical = (frame["High"] + frame["Low"] + close) / 3.0

    frame["MA9"] = close.rolling(PRICE_MA_PERIOD).mean()
    frame["RSI14"] = calculate_rsi(close, RSI_PERIOD)
    frame["MOM10"] = close - close.shift(MOMENTUM_PERIOD)

    ma21 = close.rolling(DEVIATION_PERIOD).mean()
    frame["MA_DEV21"] = (close - ma21) / ma21.replace(0, np.nan) * 100.0

    esa = typical.ewm(span=WT_CHANNEL_PERIOD, adjust=False).mean()
    deviation = (typical - esa).abs().ewm(span=WT_CHANNEL_PERIOD, adjust=False).mean()
    channel_index = (typical - esa) / (0.015 * deviation.replace(0, np.nan))
    frame["WT1"] = channel_index.ewm(span=WT_AVERAGE_PERIOD, adjust=False).mean()
    frame["WT2"] = frame["WT1"].rolling(WT_SIGNAL_PERIOD).mean()
    frame["ATR"] = calculate_atr(frame, ATR_PERIOD)

    # Tablo başlığı değişmesin diye mevcut STOCH K/D sütununda yardımcı gösterim.
    rsi_low = frame["RSI14"].rolling(14).min()
    rsi_high = frame["RSI14"].rolling(14).max()
    raw_stoch = (frame["RSI14"] - rsi_low) / (rsi_high - rsi_low).replace(0, np.nan) * 100.0
    frame["STOCH_K"] = raw_stoch.rolling(3).mean()
    frame["STOCH_D"] = frame["STOCH_K"].rolling(3).mean()
    return frame.replace([np.inf, -np.inf], np.nan)


def analyze_symbol(symbol: str, daily_data: pd.DataFrame) -> Optional[Dict]:
    if len(daily_data) < MINIMUM_CANDLES:
        return None

    frame = add_indicators(daily_data).dropna()
    if len(frame) < 3:
        return None

    current = frame.iloc[-1]
    previous = frame.iloc[-2]

    close = float(current["Close"])
    open_price = float(current["Open"])
    low = float(current["Low"])
    ma9 = float(current["MA9"])
    previous_ma9 = float(previous["MA9"])
    previous_close = float(previous["Close"])
    rsi = float(current["RSI14"])
    previous_rsi = float(previous["RSI14"])
    deviation = float(current["MA_DEV21"])
    previous_deviation = float(previous["MA_DEV21"])
    wt1 = float(current["WT1"])
    wt2 = float(current["WT2"])
    previous_wt1 = float(previous["WT1"])
    previous_wt2 = float(previous["WT2"])
    atr = float(current["ATR"])
    momentum = float(current["MOM10"])
    stoch_k = float(current["STOCH_K"])
    stoch_d = float(current["STOCH_D"])

    wt_cross_up = wt1 > wt2 and previous_wt1 <= previous_wt2
    wt_in_dip = min(wt1, previous_wt1) <= WT_OVERSOLD_LEVEL
    deviation_negative = deviation < 0.0
    deviation_rising = deviation > previous_deviation
    rsi_rising = rsi > previous_rsi
    rsi_recovery_zone = 30.0 <= rsi <= 55.0
    price_above_ma9 = close > ma9
    price_cross_ma9 = close > ma9 and previous_close <= previous_ma9
    green_candle = close > open_price

    # Videodaki ana mantık: dipte WT yukarı kesişimi + MA sapmasının negatiften toparlanması.
    if not (wt_cross_up and wt_in_dip and deviation_negative and deviation_rising):
        return None

    score = 45
    score += 15 if rsi_recovery_zone and rsi_rising else 8 if rsi_rising else 0
    score += 15 if price_cross_ma9 else 10 if price_above_ma9 else 0
    score += 10 if green_candle else 0
    score += 10 if deviation > -5.0 else 5
    score += 5 if momentum > 0 else 0
    score = min(score, 100)

    if score < MINIMUM_SCORE:
        return None

    recent_low = float(frame["Low"].tail(5).min())
    stop = min(recent_low, low) - atr * 0.20
    stop = min(stop, close * 0.995)
    target = max(close + atr * 2.0, ma9 + atr * 1.5)
    target = min(target, close * 1.10)
    gain_pct = (target / close - 1.0) * 100.0

    if price_cross_ma9:
        combination = "WT DİP + MA9 KIRILIM"
    elif price_above_ma9:
        combination = "WT DİP + MA9 ÜSTÜ"
    else:
        combination = "WT DİP TOPARLANMA"

    decision = "GÜÇLÜ AL" if score >= 85 else "AL" if score >= 70 else "TAKİP"

    return {
        "symbol": symbol.replace(".IS", ""),
        "combination": combination,
        "score": int(score),
        "momentum": momentum,
        "momentum_preferred": momentum > 0,
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
        "stoch_below_30": stoch_k < 30,
        "entry": close,
        "stop": stop,
        "target": target,
        "gain_pct": gain_pct,
        "decision": decision,
        "rsi": rsi,
        "wt1": wt1,
        "wt2": wt2,
        "deviation": deviation,
    }


def format_table(signals: List[Dict]) -> str:
    # BAŞLIKLAR BİREBİR KORUNDU.
    headers = [
        "HİSSE", "SİNYAL", "PUAN",
        "GİRİŞ", "STOP", "HEDEF", "KAZANÇ %", "KARAR",
    ]
    rows: List[List[str]] = []
    for signal in signals:
        rows.append([
            signal["symbol"], signal["combination"], str(signal["score"]),
            f"{signal['entry']:.2f}",
            f"{signal['stop']:.2f}",
            f"{signal['target']:.2f}",
            f"%{signal['gain_pct']:.2f}",
            signal["decision"],
        ])

    widths = [max(len(headers[i]), max((len(row[i]) for row in rows), default=0)) for i in range(len(headers))]
    separator = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    lines = [separator, "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |", separator]
    for row in rows:
        lines.append("| " + " | ".join(row[i].ljust(widths[i]) for i in range(len(row))) + " |")
    lines.append(separator)
    return "\n".join(lines)


def send_telegram(signals: List[Dict]) -> None:
    if not (TELEGRAM_ENABLED and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID and signals):
        return
    lines = [
        "<b>BIST — VİDEO TARAMASI (GÜNLÜK)</b>",
        "<i>MA9 + RSI14 + WaveTrend dip kesişimi + MA Deviation21 toparlanması</i>",
        "",
    ]
    for index, signal in enumerate(signals, start=1):
        lines.append(
            f"{index}. <b>{signal['symbol']}</b> | {signal['combination']} | "
            f"Puan {signal['score']} | RSI {signal['rsi']:.1f} | "
            f"WT {signal['wt1']:.1f}/{signal['wt2']:.1f} | Sapma %{signal['deviation']:.2f} | "
            f"Giriş {signal['entry']:.2f} | Stop {signal['stop']:.2f} | Hedef {signal['target']:.2f}"
        )
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": "\n".join(lines), "parse_mode": "HTML"},
            timeout=15,
        ).raise_for_status()
    except requests.RequestException as error:
        print(f"Telegram gönderim hatası: {error}")


def run_video_scan() -> List[Dict]:
    symbols = get_bist_symbols()
    results: List[Dict] = []
    analyzed = 0
    failed = 0
    started = time.perf_counter()

    batches = list(split_batches(symbols, BATCH_SIZE))
    for batch_number, batch in enumerate(batches, start=1):
        print(f"Grup {batch_number}/{len(batches)} indiriliyor ({len(batch)} hisse)...")
        downloaded = download_batch(batch)
        for symbol in batch:
            data = extract_symbol_data(downloaded, symbol, len(batch))
            if data.empty:
                failed += 1
                continue
            analyzed += 1
            result = analyze_symbol(symbol, data)
            if result is not None:
                results.append(result)

    results.sort(key=lambda item: (item["score"], item["deviation"], item["rsi"]), reverse=True)
    results = results[:MAX_RESULTS]

    elapsed = time.perf_counter() - started
    print("\n" + "=" * 105)
    print("BIST | VİDEO TARAMASI | GÜNLÜK")
    print(f"Analiz: {analyzed} | Alınamayan: {failed} | Bulunan: {len(results)} | Süre: {elapsed:.1f} sn")
    print("Koşul: WT dipte yukarı kesişim + MA Deviation(21) negatif bölgede yukarı dönüş")
    print("=" * 105)
    if results:
        print(format_table(results))
        send_telegram(results)
    else:
        print("Video koşullarını sağlayan hisse bulunmadı.")
    return results


if __name__ == "__main__":
    run_video_scan()
