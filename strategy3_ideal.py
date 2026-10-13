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
# 3. VİDEO TARAMASI — AYRI TARAMA
# 2 SAATLİK | ALMA(7/11) + MOM(10) + STOCH RSI + BOLLINGER
# =========================================================

DOWNLOAD_INTERVAL = "60m"          # Yahoo 2 saat vermediği için 60 dk indirilip 2 saate çevrilir.
DOWNLOAD_PERIOD = "730d"
RESAMPLE_RULE = "2h"
MINIMUM_CANDLES = 120
BATCH_SIZE = 50
DOWNLOAD_TIMEOUT_SECONDS = 25
MAX_RESULTS = 25
MINIMUM_SCORE = 65
SIGNAL_LOOKBACK = 3

ALMA_FAST_PERIOD = 7
ALMA_SLOW_PERIOD = 11
ALMA_OFFSET = 0.85
ALMA_SIGMA = 6.0
MOMENTUM_PERIOD = 10
RSI_PERIOD = 14
STOCH_RSI_PERIOD = 14
STOCH_K_PERIOD = 3
STOCH_D_PERIOD = 3
STOCH_BUY_LEVEL = 30.0
BB_PERIOD = 20
BB_STD = 2.0
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
            interval=DOWNLOAD_INTERVAL,
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
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    if frame.empty:
        return frame

    # 60 dakikalık veriyi gerçek 2 saatlik mumlara dönüştür.
    frame = frame.resample(RESAMPLE_RULE, label="right", closed="right").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    })
    return frame.dropna(subset=["Open", "High", "Low", "Close"])


def calculate_alma(series: pd.Series, period: int, offset: float, sigma: float) -> pd.Series:
    m = offset * (period - 1)
    s = period / sigma
    weights = np.exp(-((np.arange(period) - m) ** 2) / (2.0 * s * s))
    weights /= weights.sum()
    return series.rolling(period).apply(lambda values: float(np.dot(values, weights)), raw=True)


def calculate_rsi(close: pd.Series, period: int) -> pd.Series:
    change = close.diff()
    gain = change.clip(lower=0.0)
    loss = -change.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100.0 - (100.0 / (1.0 + rs))
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

    frame["ALMA7"] = calculate_alma(close, ALMA_FAST_PERIOD, ALMA_OFFSET, ALMA_SIGMA)
    frame["ALMA11"] = calculate_alma(close, ALMA_SLOW_PERIOD, ALMA_OFFSET, ALMA_SIGMA)
    frame["MOM10"] = close - close.shift(MOMENTUM_PERIOD)

    rsi = calculate_rsi(close, RSI_PERIOD)
    rsi_low = rsi.rolling(STOCH_RSI_PERIOD).min()
    rsi_high = rsi.rolling(STOCH_RSI_PERIOD).max()
    raw_stoch = (rsi - rsi_low) / (rsi_high - rsi_low).replace(0, np.nan) * 100.0
    frame["STOCH_K"] = raw_stoch.rolling(STOCH_K_PERIOD).mean()
    frame["STOCH_D"] = frame["STOCH_K"].rolling(STOCH_D_PERIOD).mean()

    frame["BB_MID"] = close.rolling(BB_PERIOD).mean()
    bb_deviation = close.rolling(BB_PERIOD).std(ddof=0)
    frame["BB_UPPER"] = frame["BB_MID"] + BB_STD * bb_deviation
    frame["BB_LOWER"] = frame["BB_MID"] - BB_STD * bb_deviation
    frame["ATR"] = calculate_atr(frame, ATR_PERIOD)
    return frame.replace([np.inf, -np.inf], np.nan)


def crossed_up(series_a: pd.Series, series_b: pd.Series, lookback: int) -> bool:
    for offset in range(lookback):
        index = len(series_a) - 1 - offset
        if index <= 0:
            break
        if float(series_a.iloc[index]) > float(series_b.iloc[index]) and float(series_a.iloc[index - 1]) <= float(series_b.iloc[index - 1]):
            return True
    return False


def stoch_buy_in_lookback(frame: pd.DataFrame, lookback: int) -> bool:
    for offset in range(lookback):
        index = len(frame) - 1 - offset
        if index <= 0:
            break
        k_now = float(frame["STOCH_K"].iloc[index])
        d_now = float(frame["STOCH_D"].iloc[index])
        k_prev = float(frame["STOCH_K"].iloc[index - 1])
        d_prev = float(frame["STOCH_D"].iloc[index - 1])
        crossed = k_now > d_now and k_prev <= d_prev
        dip_zone = min(k_now, d_now, k_prev, d_prev) < STOCH_BUY_LEVEL
        if crossed and dip_zone:
            return True
    return False


def analyze_symbol(symbol: str, data: pd.DataFrame) -> Optional[Dict]:
    if len(data) < MINIMUM_CANDLES:
        return None

    frame = add_indicators(data).dropna()
    if len(frame) < 5:
        return None

    current = frame.iloc[-1]
    previous = frame.iloc[-2]
    close = float(current["Close"])
    atr = float(current["ATR"])

    alma_cross = crossed_up(frame["ALMA7"], frame["ALMA11"], SIGNAL_LOOKBACK)
    alma_bullish = float(current["ALMA7"]) > float(current["ALMA11"])
    stoch_buy = stoch_buy_in_lookback(frame, SIGNAL_LOOKBACK)
    momentum_positive = float(current["MOM10"]) > 0.0
    momentum_rising = float(current["MOM10"]) > float(previous["MOM10"])

    recent = frame.tail(SIGNAL_LOOKBACK + 2)
    lower_band_touch = bool((recent["Low"] <= recent["BB_LOWER"] * 1.01).any())
    lower_band_rebound = close > float(current["BB_LOWER"]) and lower_band_touch

    # Videodaki temel şartlar: ALMA 7/11 yukarı kesişim, MOM(10) sıfır üstü,
    # Stoch RSI 30 altında yukarı kesişim ve Bollinger alt banttan toparlanma.
    if not (alma_cross and alma_bullish and stoch_buy and momentum_positive and lower_band_rebound):
        return None

    score = 65
    score += 10 if momentum_rising else 0
    score += 10 if close > float(current["BB_MID"]) else 5
    score += 10 if float(current["STOCH_K"]) < 50.0 else 5
    score += 5 if close > float(previous["Close"]) else 0
    score = min(score, 100)
    if score < MINIMUM_SCORE:
        return None

    recent_low = float(frame["Low"].tail(6).min())
    stop = min(recent_low, close - atr * 1.2)
    stop = min(stop, close * 0.995)
    target = max(close + atr * 2.0, close * 1.05)
    target = min(target, close * 1.10)
    gain_pct = (target / close - 1.0) * 100.0

    if score >= 90:
        signal = "ALMA + MOM + STOCH + BB"
    elif close > float(current["BB_MID"]):
        signal = "ALMA KESİŞİM + BB ORTA ÜSTÜ"
    else:
        signal = "ALMA KESİŞİM + ALT BANT DÖNÜŞ"

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
        "mom": float(current["MOM10"]),
        "stoch_k": float(current["STOCH_K"]),
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
    separator = "+" + "+".join("-" * (width + 2) for width in widths) + "+"
    lines = [separator, "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |", separator]
    for row in rows:
        lines.append("| " + " | ".join(row[i].ljust(widths[i]) for i in range(len(row))) + " |")
    lines.append(separator)
    return "\n".join(lines)


def send_telegram(signals: List[Dict]) -> None:
    if not (TELEGRAM_ENABLED and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID and signals):
        return
    lines = [
        "<b>BIST — 3. VİDEO TARAMASI (2 SAATLİK)</b>",
        "<i>ALMA 7/11 + Momentum 10 + Stoch RSI + Bollinger</i>",
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


def run_video3_scan() -> List[Dict]:
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

    results.sort(key=lambda item: (item["score"], item["mom"], -item["stoch_k"]), reverse=True)
    results = results[:MAX_RESULTS]
    elapsed = time.perf_counter() - started

    print("\n" + "=" * 108)
    print("BIST | 3. VİDEO TARAMASI | 2 SAATLİK")
    print(f"Analiz: {analyzed} | Alınamayan: {failed} | Bulunan: {len(results)} | Süre: {elapsed:.1f} sn")
    print("Koşul: ALMA7, ALMA11'i yukarı keser + MOM(10) > 0 + Stoch RSI 30 altında AL + Bollinger alt bant dönüşü")
    print("=" * 108)
    if results:
        print(format_table(results))
        send_telegram(results)
    else:
        print("3. video koşullarını sağlayan hisse bulunmadı.")
    return results


if __name__ == "__main__":
    run_video3_scan()
