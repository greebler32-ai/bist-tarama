from __future__ import annotations

import math
import time
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from symbols import get_bist_symbols

# =========================================================
# VİDEO 5 — AYRI TARAMA
# GÜNLÜK | ALMA(9, 0.85, 6) + FISHER TRANSFORM(9)
# Görüntüdeki TradingView ayarlarına en yakın eşdeğer.
# =========================================================


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

SOURCE_INTERVAL = "1d"
DOWNLOAD_PERIOD = "1y"
MINIMUM_CANDLES = 80
BATCH_SIZE = 60
DOWNLOAD_TIMEOUT_SECONDS = 20
MAX_RESULTS = 25
MINIMUM_SCORE = 65

ALMA_LENGTH = 9
ALMA_OFFSET = 0.85
ALMA_SIGMA = 6.0
FISHER_LENGTH = 9
ATR_PERIOD = 14

# Hareketini yapmış / geç kalınmış hisseleri elemek için kalite filtreleri.
MAX_DAILY_CHANGE_PCT = 6.0
MAX_DISTANCE_FROM_ALMA_PCT = 4.0
MAX_3DAY_RISE_PCT = 12.0
MAX_5DAY_RISE_PCT = 18.0


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
    except Exception as exc:
        print(f"İndirme hatası: {exc}")
        return pd.DataFrame()


def extract_symbol_data(downloaded: pd.DataFrame, symbol: str, symbol_count: int) -> pd.DataFrame:
    if downloaded is None or downloaded.empty:
        return pd.DataFrame()

    try:
        if isinstance(downloaded.columns, pd.MultiIndex):
            level0 = downloaded.columns.get_level_values(0)
            level1 = downloaded.columns.get_level_values(1)
            if symbol in level0:
                frame = downloaded[symbol].copy()
            elif symbol in level1:
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
    if any(col not in frame.columns for col in required):
        return pd.DataFrame()

    frame = frame[required].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def alma(series: pd.Series, length: int = ALMA_LENGTH, offset: float = ALMA_OFFSET, sigma: float = ALMA_SIGMA) -> pd.Series:
    m = offset * (length - 1)
    s = length / sigma
    weights = np.array([math.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(length)], dtype=float)
    weights /= weights.sum()

    def _calc(values: np.ndarray) -> float:
        return float(np.dot(values, weights))

    return series.rolling(length).apply(_calc, raw=True)


def fisher_transform(high: pd.Series, low: pd.Series, length: int = FISHER_LENGTH) -> pd.DataFrame:
    median = (high + low) / 2.0
    highest = median.rolling(length).max()
    lowest = median.rolling(length).min()

    value = pd.Series(index=median.index, dtype=float)
    fisher = pd.Series(index=median.index, dtype=float)

    prev_value = 0.0
    prev_fisher = 0.0
    for i in range(len(median)):
        if i < length - 1 or pd.isna(highest.iloc[i]) or pd.isna(lowest.iloc[i]):
            value.iloc[i] = np.nan
            fisher.iloc[i] = np.nan
            continue

        rng = float(highest.iloc[i] - lowest.iloc[i])
        raw = 0.0 if rng == 0 else 2.0 * ((float(median.iloc[i]) - float(lowest.iloc[i])) / rng - 0.5)
        current_value = 0.33 * raw + 0.67 * prev_value
        current_value = max(min(current_value, 0.999), -0.999)
        current_fisher = 0.5 * math.log((1.0 + current_value) / (1.0 - current_value)) + 0.5 * prev_fisher

        value.iloc[i] = current_value
        fisher.iloc[i] = current_fisher
        prev_value = current_value
        prev_fisher = current_fisher

    trigger = fisher.shift(1)
    return pd.DataFrame({"FISHER": fisher, "TRIGGER": trigger})


def atr(data: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    prev_close = data["Close"].shift(1)
    tr = pd.concat(
        [
            data["High"] - data["Low"],
            (data["High"] - prev_close).abs(),
            (data["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def add_indicators(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    frame["ALMA"] = alma(frame["Close"])
    fisher_df = fisher_transform(frame["High"], frame["Low"])
    frame["FISHER"] = fisher_df["FISHER"]
    frame["TRIGGER"] = fisher_df["TRIGGER"]
    frame["ATR"] = atr(frame)
    frame["VOL20"] = frame["Volume"].rolling(20).mean()
    frame["CHG1"] = frame["Close"].pct_change() * 100.0
    frame["RISE3"] = (frame["Close"] / frame["Close"].shift(3) - 1.0) * 100.0
    frame["RISE5"] = (frame["Close"] / frame["Close"].shift(5) - 1.0) * 100.0
    return frame.replace([np.inf, -np.inf], np.nan)


def analyze_symbol(symbol: str, daily_data: pd.DataFrame) -> Optional[Dict]:
    if len(daily_data) < MINIMUM_CANDLES:
        return None

    frame = add_indicators(daily_data).dropna()
    if len(frame) < 4:
        return None

    cur = frame.iloc[-1]
    prev = frame.iloc[-2]

    close = float(cur["Close"])
    open_price = float(cur["Open"])
    low = float(cur["Low"])
    alma_now = float(cur["ALMA"])
    alma_prev = float(prev["ALMA"])
    fisher_now = float(cur["FISHER"])
    fisher_prev = float(prev["FISHER"])
    trigger_now = float(cur["TRIGGER"])
    trigger_prev = float(prev["TRIGGER"])
    atr_now = float(cur["ATR"])
    daily_change = float(cur["CHG1"])
    rise3 = float(cur["RISE3"])
    rise5 = float(cur["RISE5"])
    volume = float(cur["Volume"])
    vol20 = float(cur["VOL20"])

    fisher_cross_up = fisher_now > trigger_now and fisher_prev <= trigger_prev
    fisher_dip = min(fisher_prev, trigger_prev) <= 0.0
    deep_fisher = min(fisher_prev, trigger_prev) <= -1.0

    price_above_alma = close > alma_now
    alma_rising = alma_now > alma_prev
    price_cross_alma = close > alma_now and float(prev["Close"]) <= alma_prev
    green_candle = close > open_price
    distance_alma_pct = (close / alma_now - 1.0) * 100.0 if alma_now else 999.0

    # Ana video sinyali: Fisher yukarı kesişimi + ALMA üzerinde/yukarı dönüş.
    if not (fisher_cross_up and fisher_dip and price_above_alma and alma_rising):
        return None

    # Geç kalmış / aşırı yükselmiş adayları ele.
    if daily_change >= MAX_DAILY_CHANGE_PCT:
        return None
    if distance_alma_pct > MAX_DISTANCE_FROM_ALMA_PCT:
        return None
    if rise3 >= MAX_3DAY_RISE_PCT or rise5 >= MAX_5DAY_RISE_PCT:
        return None

    score = 50
    if deep_fisher:
        score += 15
    elif min(fisher_prev, trigger_prev) <= -0.5:
        score += 10

    if price_cross_alma:
        score += 15
    else:
        score += 8

    if green_candle:
        score += 8
    if volume > vol20:
        score += 7
    if distance_alma_pct <= 2.0:
        score += 5
    score = min(score, 100)

    if score < MINIMUM_SCORE:
        return None

    recent_low = float(frame["Low"].tail(5).min())
    stop = min(recent_low, low) - 0.15 * atr_now
    stop = min(stop, close * 0.995)
    target = min(max(close + 2.0 * atr_now, close * 1.05), close * 1.10)
    gain_pct = (target / close - 1.0) * 100.0

    signal = "ALMA + FISHER DİP KESİŞİM" if deep_fisher else "ALMA + FISHER KESİŞİM"
    decision = "GÜÇLÜ AL" if score >= 85 else "AL" if score >= 72 else "TAKİP"

    return {
        "symbol": symbol.replace(".IS", ""),
        "signal": signal,
        "score": int(score),
        "entry": close,
        "stop": stop,
        "target": target,
        "gain_pct": gain_pct,
        "decision": decision,
        "fisher": fisher_now,
        "trigger": trigger_now,
        "distance_alma_pct": distance_alma_pct,
    }


def format_table(signals: List[Dict]) -> str:
    headers = ["HİSSE", "SİNYAL", "PUAN", "GİRİŞ", "STOP", "HEDEF", "KAZANÇ %", "KARAR"]
    rows: List[List[str]] = []
    for s in signals:
        rows.append([
            s["symbol"],
            s["signal"],
            str(s["score"]),
            f"{s['entry']:.2f}",
            f"{s['stop']:.2f}",
            f"{s['target']:.2f}",
            f"%{s['gain_pct']:.2f}",
            s["decision"],
        ])

    widths = [max(len(headers[i]), max((len(r[i]) for r in rows), default=0)) for i in range(len(headers))]
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    out = [sep, "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |", sep]
    for row in rows:
        out.append("| " + " | ".join(row[i].ljust(widths[i]) for i in range(len(row))) + " |")
    out.append(sep)
    return "\n".join(out)


def run_video5_scan() -> List[Dict]:
    symbols = get_bist_symbols()
    results: List[Dict] = []
    analyzed = 0
    failed = 0
    started = time.perf_counter()

    batches = list(split_batches(symbols, BATCH_SIZE))
    for batch_no, batch in enumerate(batches, start=1):
        print(f"Grup {batch_no}/{len(batches)} indiriliyor ({len(batch)} hisse)...")
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

    results.sort(key=lambda x: (x["score"], -x["distance_alma_pct"]), reverse=True)
    results = results[:MAX_RESULTS]
    elapsed = time.perf_counter() - started

    print("\n" + "=" * 100)
    print("BIST | VİDEO 5 TARAMASI | GÜNLÜK")
    print(f"Analiz: {analyzed} | Alınamayan: {failed} | Bulunan: {len(results)} | Süre: {elapsed:.1f} sn")
    print("Koşul: ALMA(9,0.85,6) yukarı yön + Fisher(9) dipte yukarı kesişim")
    print("Ek filtre: hareketini yapmış / ALMA'dan uzaklaşmış hisseler elenir")
    print("=" * 100)
    if results:
        print(format_table(results))
    else:
        print("Koşulları sağlayan hisse bulunmadı.")
    return results


if __name__ == "__main__":
    run_video5_scan()
