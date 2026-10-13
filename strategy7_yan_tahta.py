from __future__ import annotations
from v19_report import start_txt_report, stop_txt_report

import math
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

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

BIST_SYMBOLS = get_bist_symbols()

INTERVAL = "1d"
PERIOD = "1y"
MAX_RESULTS = 30

# Videoda görünen ayarlar
SMA_LEN = 25
ALMA_FAST = 5
ALMA_SLOW = 11
ALMA_OFFSET = 0.85
ALMA_SIGMA = 6.0
BB_LEN = 20
BB_STD = 2.0
VOL_LEN = 20
RSI_LEN = 14
STOCH_RSI_LEN = 14
STOCH_K = 3
STOCH_D = 3
SMI_K = 10
SMI_D = 3
SMI_SIGNAL = 3

# Hareketini tamamlamış hisseleri ele
MAX_DAILY_GAIN = 6.0
MAX_3D_GAIN = 12.0
MAX_5D_GAIN = 18.0
MAX_ABOVE_ALMA = 6.0
MAX_ABOVE_BB_MID = 8.0


def _series(x):
    if isinstance(x, pd.DataFrame):
        return x.iloc[:, 0]
    return x


def alma(series: pd.Series, length: int, offset: float = 0.85, sigma: float = 6.0) -> pd.Series:
    s = _series(series).astype(float)
    m = offset * (length - 1)
    sd = length / sigma
    weights = np.array([math.exp(-((i - m) ** 2) / (2 * sd * sd)) for i in range(length)], dtype=float)
    weights /= weights.sum()

    def calc(x):
        return float(np.dot(x, weights))

    return s.rolling(length).apply(calc, raw=True)


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    s = _series(series).astype(float)
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def stoch_rsi(series: pd.Series):
    r = rsi(series, RSI_LEN)
    low = r.rolling(STOCH_RSI_LEN).min()
    high = r.rolling(STOCH_RSI_LEN).max()
    raw = 100 * (r - low) / (high - low).replace(0, np.nan)
    k = raw.rolling(STOCH_K).mean()
    d = k.rolling(STOCH_D).mean()
    return k, d


def smi(high: pd.Series, low: pd.Series, close: pd.Series):
    h = _series(high).astype(float)
    l = _series(low).astype(float)
    c = _series(close).astype(float)

    hh = h.rolling(SMI_K).max()
    ll = l.rolling(SMI_K).min()
    midpoint = (hh + ll) / 2.0
    diff = c - midpoint
    rng = hh - ll

    ds = diff.ewm(span=SMI_D, adjust=False).mean().ewm(span=SMI_D, adjust=False).mean()
    rs = rng.ewm(span=SMI_D, adjust=False).mean().ewm(span=SMI_D, adjust=False).mean()
    smi_val = 200 * ds / rs.replace(0, np.nan)
    signal = smi_val.ewm(span=SMI_SIGNAL, adjust=False).mean()
    return smi_val, signal


def cross_up(a: pd.Series, b: pd.Series) -> bool:
    if len(a) < 2 or len(b) < 2:
        return False
    return bool(a.iloc[-2] <= b.iloc[-2] and a.iloc[-1] > b.iloc[-1])


def pct_change(current: float, old: float) -> float:
    if not old:
        return 0.0
    return (current / old - 1.0) * 100.0


def analyze_symbol(symbol: str) -> Optional[Dict]:
    ticker = symbol if symbol.endswith(".IS") else f"{symbol}.IS"
    try:
        _dl_period, _dl_interval = _tf_params()
        df = yf.download(
            ticker,
            period=_dl_period,
            interval=_dl_interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        df = _tf_resample(df)
    except Exception:
        return None

    if df is None or len(df) < 80:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    needed = ["Open", "High", "Low", "Close", "Volume"]
    if any(c not in df.columns for c in needed):
        return None

    df = df.dropna(subset=needed).copy()
    if len(df) < 80:
        return None

    close = _series(df["Close"])
    high = _series(df["High"])
    low = _series(df["Low"])
    open_ = _series(df["Open"])
    volume = _series(df["Volume"])

    df["SMA25"] = close.rolling(SMA_LEN).mean()
    df["ALMA5"] = alma(close, ALMA_FAST, ALMA_OFFSET, ALMA_SIGMA)
    df["ALMA11"] = alma(close, ALMA_SLOW, ALMA_OFFSET, ALMA_SIGMA)

    basis = close.rolling(BB_LEN).mean()
    dev = close.rolling(BB_LEN).std(ddof=0)
    df["BB_MID"] = basis
    df["BB_UP"] = basis + BB_STD * dev
    df["BB_LOW"] = basis - BB_STD * dev
    df["VOL_MA20"] = volume.rolling(VOL_LEN).mean()

    df["RSI14"] = rsi(close, RSI_LEN)
    k, d = stoch_rsi(close)
    df["STO_K"] = k
    df["STO_D"] = d

    smi_val, smi_sig = smi(high, low, close)
    df["SMI"] = smi_val
    df["SMI_SIG"] = smi_sig

    df = df.dropna().copy()
    if len(df) < 10:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    c = float(last["Close"])
    o = float(last["Open"])
    h = float(last["High"])
    l = float(last["Low"])
    alma5 = float(last["ALMA5"])
    alma11 = float(last["ALMA11"])
    sma25 = float(last["SMA25"])
    bb_mid = float(last["BB_MID"])
    bb_up = float(last["BB_UP"])
    vol = float(last["Volume"])
    vol_ma = float(last["VOL_MA20"])
    rsi14 = float(last["RSI14"])
    sto_k = float(last["STO_K"])
    sto_d = float(last["STO_D"])
    smi_now = float(last["SMI"])
    smi_sig_now = float(last["SMI_SIG"])

    # Ana video mantığı: kısa ALMA uzun ALMA üstünde/yeni kesişim,
    # fiyat SMA25 ve Bollinger orta bandın üzerinde, momentum teyitleri yukarı.
    alma_cross = bool(prev["ALMA5"] <= prev["ALMA11"] and last["ALMA5"] > last["ALMA11"])
    alma_bull = alma5 > alma11 and alma5 > float(prev["ALMA5"])
    trend_ok = c > sma25 and c >= bb_mid

    stoch_cross = bool(prev["STO_K"] <= prev["STO_D"] and sto_k > sto_d)
    stoch_bull = sto_k > sto_d and sto_k < 80
    rsi_ok = 48 <= rsi14 <= 70 and rsi14 > float(prev["RSI14"])

    smi_cross = bool(prev["SMI"] <= prev["SMI_SIG"] and smi_now > smi_sig_now)
    smi_bull = smi_now > smi_sig_now and smi_now > float(prev["SMI"])

    volume_ok = vol_ma > 0 and vol >= vol_ma * 0.90
    volume_strong = vol_ma > 0 and vol >= vol_ma * 1.20

    # Aşırı yükselmiş / hareketini yapmış hisse filtresi
    daily_gain = pct_change(c, float(prev["Close"]))
    gain3 = pct_change(c, float(df.iloc[-4]["Close"])) if len(df) >= 4 else 0.0
    gain5 = pct_change(c, float(df.iloc[-6]["Close"])) if len(df) >= 6 else 0.0
    alma_dist = pct_change(c, alma11)
    bb_mid_dist = pct_change(c, bb_mid)

    if daily_gain >= MAX_DAILY_GAIN:
        return None
    if gain3 >= MAX_3D_GAIN or gain5 >= MAX_5D_GAIN:
        return None
    if alma_dist > MAX_ABOVE_ALMA or bb_mid_dist > MAX_ABOVE_BB_MID:
        return None
    if c > bb_up * 1.01:
        return None

    # En az üç blok aynı anda çalışmalı.
    blocks = [
        alma_cross or alma_bull,
        trend_ok,
        stoch_cross or stoch_bull,
        rsi_ok,
        smi_cross or smi_bull,
        volume_ok,
    ]
    if sum(bool(x) for x in blocks) < 5:
        return None

    # Momentum teyitlerinden en az biri yeni kesişim olsun.
    fresh_trigger = alma_cross or stoch_cross or smi_cross
    if not fresh_trigger:
        return None

    score = 0
    labels = []

    if alma_cross:
        score += 25
        labels.append("ALMA5/11 KESİŞİM")
    elif alma_bull:
        score += 15
        labels.append("ALMA TREND")

    if trend_ok:
        score += 15
        labels.append("SMA25+BB")

    if stoch_cross:
        score += 20
        labels.append("STOCH RSI")
    elif stoch_bull:
        score += 10

    if rsi_ok:
        score += 10

    if smi_cross:
        score += 20
        labels.append("SMI")
    elif smi_bull:
        score += 10

    if volume_strong:
        score += 10
        labels.append("HACİM")
    elif volume_ok:
        score += 5

    # Yeşil mum ama aşırı büyük değilse küçük katkı.
    candle_gain = pct_change(c, o)
    if 0 < candle_gain < 4.0:
        score += 5

    score = min(100, int(round(score)))

    if score < 65:
        return None

    # ATR benzeri risk ölçüsü
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1])

    entry = c
    stop = max(alma11, c - 1.5 * atr14)
    if stop >= entry:
        stop = entry * 0.96

    risk = max(entry - stop, entry * 0.025)
    target = entry + 2.0 * risk
    gain_pct = pct_change(target, entry)

    if score >= 85:
        decision = "GÜÇLÜ AL"
    elif score >= 75:
        decision = "AL"
    else:
        decision = "TAKİP"

    signal = " + ".join(labels[:4]) if labels else "YAN TAHTA MOMENTUM"

    return {
        "symbol": symbol.replace(".IS", ""),
        "signal": signal,
        "score": score,
        "entry": entry,
        "stop": stop,
        "target": target,
        "gain_pct": gain_pct,
        "decision": decision,
    }


def format_table(signals: List[Dict]) -> str:
    headers = ["HİSSE", "SİNYAL", "PUAN", "GİRİŞ", "STOP", "HEDEF", "KAZANÇ %", "KARAR"]
    rows = []
    for s in signals:
        rows.append([
            s["symbol"],
            s["signal"],
            str(s["score"]),
            f'{s["entry"]:.2f}',
            f'{s["stop"]:.2f}',
            f'{s["target"]:.2f}',
            f'%{s["gain_pct"]:.2f}',
            s["decision"],
        ])

    widths = [max(len(headers[i]), max((len(r[i]) for r in rows), default=0)) for i in range(len(headers))]
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    lines = [
        sep,
        "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |",
        sep,
    ]
    for row in rows:
        lines.append("| " + " | ".join(row[i].ljust(widths[i]) for i in range(len(row))) + " |")
    lines.append(sep)
    return "\n".join(lines)


def run_video7_scan() -> List[Dict]:
    results = []
    total = len(BIST_SYMBOLS)
    errors = 0
    started = time.time()

    print("=" * 100)
    print("BIST | VİDEO 7 TARAMASI | GÜNLÜK")
    print("Koşul: ALMA5/11 + SMA25 + Bollinger20 + Stoch RSI + RSI14 + SMI + Hacim")
    print("Aşırı yükselmiş / hareketini tamamlamış hisseler elenir.")
    print("=" * 100)

    for idx, symbol in enumerate(BIST_SYMBOLS, 1):
        try:
            hit = analyze_symbol(symbol)
            if hit:
                results.append(hit)
        except Exception:
            errors += 1

        if idx % 50 == 0 or idx == total:
            print(f"Taranıyor: {idx}/{total} | Bulunan: {len(results)}", end="\r")

    results.sort(key=lambda x: (x["score"], x["gain_pct"]), reverse=True)
    results = results[:MAX_RESULTS]

    print(" " * 100, end="\r")
    elapsed = time.time() - started
    print(f"Analiz: {total} | Hata: {errors} | Bulunan: {len(results)} | Süre: {elapsed:.1f} sn")
    if results:
        print(format_table(results))
    else:
        print("Koşulları sağlayan hisse bulunamadı.")
    return results


if __name__ == "__main__":
    run_video7_scan()
