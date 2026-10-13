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
# 2. VİDEO TARAMASI — AYRI TARAMA
# GÜNLÜK | HEIKIN ASHI + EMA(11) + WAVETREND + STOCH RSI
# =========================================================

SOURCE_INTERVAL = "1d"
DOWNLOAD_PERIOD = "2y"
MINIMUM_CANDLES = 100
BATCH_SIZE = 60
DOWNLOAD_TIMEOUT_SECONDS = 20
MAX_RESULTS = 20
MINIMUM_SCORE = 60

EMA_PERIOD = 11
WT_CHANNEL_PERIOD = 10
WT_AVERAGE_PERIOD = 21
WT_SIGNAL_PERIOD = 4
WT_OVERSOLD_LEVEL = -60.0
STOCH_RSI_PERIOD = 14
STOCH_K_PERIOD = 3
STOCH_D_PERIOD = 3
ATR_PERIOD = 14

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
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100.0 - 100.0 / (1.0 + rs)
    return result.mask((avg_loss == 0) & (avg_gain > 0), 100.0)


def calculate_atr(data: pd.DataFrame, period: int) -> pd.Series:
    previous_close = data["Close"].shift(1)
    true_range = pd.concat([
        data["High"] - data["Low"],
        (data["High"] - previous_close).abs(),
        (data["Low"] - previous_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def add_indicators(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    close = frame["Close"]
    typical = (frame["High"] + frame["Low"] + close) / 3.0

    frame["EMA11"] = close.ewm(span=EMA_PERIOD, adjust=False).mean()

    # Heikin Ashi
    frame["HA_CLOSE"] = (frame["Open"] + frame["High"] + frame["Low"] + frame["Close"]) / 4.0
    ha_open = np.zeros(len(frame), dtype=float)
    if len(frame):
        ha_open[0] = (float(frame["Open"].iloc[0]) + float(frame["Close"].iloc[0])) / 2.0
        for i in range(1, len(frame)):
            ha_open[i] = (ha_open[i - 1] + float(frame["HA_CLOSE"].iloc[i - 1])) / 2.0
    frame["HA_OPEN"] = ha_open

    # WaveTrend: 10 / 21 / 4
    esa = typical.ewm(span=WT_CHANNEL_PERIOD, adjust=False).mean()
    deviation = (typical - esa).abs().ewm(span=WT_CHANNEL_PERIOD, adjust=False).mean()
    ci = (typical - esa) / (0.015 * deviation.replace(0, np.nan))
    frame["WT1"] = ci.ewm(span=WT_AVERAGE_PERIOD, adjust=False).mean()
    frame["WT2"] = frame["WT1"].rolling(WT_SIGNAL_PERIOD).mean()

    # Stokastik RSI: 14 / 14 / 3 / 3
    rsi = calculate_rsi(close, STOCH_RSI_PERIOD)
    rsi_low = rsi.rolling(STOCH_RSI_PERIOD).min()
    rsi_high = rsi.rolling(STOCH_RSI_PERIOD).max()
    raw = (rsi - rsi_low) / (rsi_high - rsi_low).replace(0, np.nan) * 100.0
    frame["STOCH_K"] = raw.rolling(STOCH_K_PERIOD).mean()
    frame["STOCH_D"] = frame["STOCH_K"].rolling(STOCH_D_PERIOD).mean()
    frame["ATR"] = calculate_atr(frame, ATR_PERIOD)
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
    previous_close = float(previous["Close"])
    ema = float(current["EMA11"])
    previous_ema = float(previous["EMA11"])
    wt1, wt2 = float(current["WT1"]), float(current["WT2"])
    previous_wt1, previous_wt2 = float(previous["WT1"]), float(previous["WT2"])
    stoch_k, stoch_d = float(current["STOCH_K"]), float(current["STOCH_D"])
    previous_k, previous_d = float(previous["STOCH_K"]), float(previous["STOCH_D"])
    ha_open, ha_close = float(current["HA_OPEN"]), float(current["HA_CLOSE"])
    previous_ha_open, previous_ha_close = float(previous["HA_OPEN"]), float(previous["HA_CLOSE"])
    atr = float(current["ATR"])

    wt_cross_up = wt1 > wt2 and previous_wt1 <= previous_wt2
    wt_dip_zone = min(wt1, previous_wt1) <= WT_OVERSOLD_LEVEL or max(wt1, wt2) < 0
    stoch_cross_up = stoch_k > stoch_d and previous_k <= previous_d
    stoch_low_zone = min(stoch_k, previous_k) <= 30.0
    ha_green = ha_close > ha_open
    ha_turn_green = ha_green and previous_ha_close <= previous_ha_open
    price_above_ema = close > ema
    price_cross_ema = close > ema and previous_close <= previous_ema

    # Videodaki ortak giriş mantığı:
    # WT dipten yukarı kesişim + Stoch RSI dipten yukarı kesişim + yeşil Heikin Ashi.
    if not (wt_cross_up and wt_dip_zone and stoch_cross_up and stoch_low_zone and ha_green):
        return None

    score = 55
    score += 15 if ha_turn_green else 8
    score += 15 if price_cross_ema else 10 if price_above_ema else 0
    score += 10 if min(wt1, previous_wt1) <= WT_OVERSOLD_LEVEL else 5
    score += 5 if stoch_k < 50 else 0
    score = min(score, 100)
    if score < MINIMUM_SCORE:
        return None

    recent_low = float(frame["Low"].tail(5).min())
    stop = min(recent_low, close - atr * 1.2)
    stop = min(stop, close * 0.995)
    target = max(close + atr * 2.0, close * 1.05)
    target = min(target, close * 1.10)
    gain_pct = (target / close - 1.0) * 100.0

    if price_cross_ema and ha_turn_green:
        signal = "HA DÖNÜŞ + EMA11 KIRILIM"
    elif price_above_ema:
        signal = "WT + STOCH + EMA11 ÜSTÜ"
    else:
        signal = "WT + STOCH + HA DÖNÜŞ"

    decision = "GÜÇLÜ AL" if score >= 85 else "AL" if score >= 70 else "TAKİP"
    return {
        "symbol": symbol.replace(".IS", ""),
        "signal": signal,
        "score": int(score),
        "entry": close,
        "stop": stop,
        "target": target,
        "gain_pct": gain_pct,
        "decision": decision,
        "wt1": wt1,
        "wt2": wt2,
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
    }


def format_table(signals: List[Dict]) -> str:
    headers = ["HİSSE", "SİNYAL", "PUAN", "GİRİŞ", "STOP", "HEDEF", "KAZANÇ %", "KARAR"]
    rows: List[List[str]] = []
    for item in signals:
        rows.append([
            item["symbol"], item["signal"], str(item["score"]),
            f"{item['entry']:.2f}", f"{item['stop']:.2f}", f"{item['target']:.2f}",
            f"%{item['gain_pct']:.2f}", item["decision"],
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
        "<b>BIST — 2. VİDEO TARAMASI (GÜNLÜK)</b>",
        "<i>Heikin Ashi + EMA11 + WaveTrend + Stoch RSI</i>",
        "",
    ]
    for index, item in enumerate(signals, 1):
        lines.append(
            f"{index}. <b>{item['symbol']}</b> | {item['signal']} | Puan {item['score']} | "
            f"Giriş {item['entry']:.2f} | Stop {item['stop']:.2f} | Hedef {item['target']:.2f}"
        )
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": "\n".join(lines), "parse_mode": "HTML"},
            timeout=15,
        ).raise_for_status()
    except requests.RequestException as error:
        print(f"Telegram gönderim hatası: {error}")


def run_video2_scan() -> List[Dict]:
    symbols = get_bist_symbols()
    results: List[Dict] = []
    analyzed = failed = 0
    started = time.perf_counter()
    batches = list(split_batches(symbols, BATCH_SIZE))

    for batch_number, batch in enumerate(batches, 1):
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

    results.sort(key=lambda item: (item["score"], -item["stoch_k"], -item["wt1"]), reverse=True)
    results = results[:MAX_RESULTS]
    elapsed = time.perf_counter() - started

    print("\n" + "=" * 105)
    print("BIST | 2. VİDEO TARAMASI | GÜNLÜK")
    print(f"Analiz: {analyzed} | Alınamayan: {failed} | Bulunan: {len(results)} | Süre: {elapsed:.1f} sn")
    print("Koşul: WT dipten yukarı kesişim + Stoch RSI dipten yukarı kesişim + yeşil Heikin Ashi")
    print("=" * 105)
    if results:
        print(format_table(results))
        send_telegram(results)
    else:
        print("2. video koşullarını sağlayan hisse bulunmadı.")
    return results


if __name__ == "__main__":
    run_video2_scan()
