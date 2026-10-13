from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf


IST = ZoneInfo("Europe/Istanbul")


def _flat(data):
    if data is None or data.empty:
        return pd.DataFrame()
    out = data.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [c[0] for c in out.columns]
    out.columns = [str(c).title() for c in out.columns]
    idx = pd.DatetimeIndex(out.index)
    if idx.tz is not None:
        idx = idx.tz_convert(IST).tz_localize(None)
    out.index = idx
    return out


def market_snapshot(now=None):
    """Yahoo verisinin tazeligi ve BIST100 kisa rejimi; hata halinde nötr kalır."""
    now = now or datetime.now(IST)
    result = {
        "PIYASA_REJIMI": "BILINMIYOR",
        "PIYASA_RET_%": np.nan,
        "VERI_SON_ZAMANI": "",
        "VERI_GECIKME_DK": np.nan,
        "VERI_KALITESI": "KONTROL_EDILEMEDI",
    }
    try:
        x = pd.DataFrame()
        for ticker in ("XU100.IS", "^XU100", "XU030.IS"):
            x = _flat(yf.download(ticker, period="5d", interval="15m",
                                  auto_adjust=False, progress=False,
                                  threads=False, timeout=15))
            if len(x) >= 21:
                break
        if len(x) < 21:
            return result
        last = x.iloc[-1]
        ema20 = x.Close.ewm(span=20, adjust=False).mean().iloc[-1]
        ret = 100 * (float(last.Close) / float(x.Close.iloc[-2]) - 1)
        slope = 100 * (float(last.Close) / float(ema20) - 1)
        if ret > 0 and slope > 0:
            regime = "POZITIF"
        elif ret < -0.35 and slope < 0:
            regime = "NEGATIF"
        else:
            regime = "NOTR"

        last_at = pd.Timestamp(x.index[-1]).to_pydatetime().replace(tzinfo=IST)
        delay = max(0.0, (now - last_at).total_seconds() / 60.0)
        # 15 dakikalık sağlayıcıda 25 dakikayı aşan veri ayrıca bayraklanır.
        quality = "GECIKMELI" if delay <= 25 else "BAYAT_VERI"
        result.update({
            "PIYASA_REJIMI": regime,
            "PIYASA_RET_%": ret,
            "VERI_SON_ZAMANI": last_at.strftime("%Y-%m-%d %H:%M:%S"),
            "VERI_GECIKME_DK": delay,
            "VERI_KALITESI": quality,
        })
    except Exception:
        pass
    return result


def _number(row, *names, default=np.nan):
    for name in names:
        if name in row and pd.notna(row[name]):
            try:
                return float(row[name])
            except (TypeError, ValueError):
                pass
    return default


def _state(score, signal, regime, rr):
    text = str(signal).upper()
    trigger = any(x in text for x in ("CANLI", "VWAP", "FIYAT_DONUS", "KIRILIM", "GUCLU_TEPKI"))
    if score >= 82 and trigger and regime != "NEGATIF" and rr >= 1.25:
        return "GUCLU_TETIK"
    if score >= 70 and trigger:
        return "TETIK"
    if score >= 60:
        return "TETIK_BEKLIYOR"
    return "HAZIRLIK"


def enrich_candidates(found, motor, now=None):
    """Motor sonucunu bozmadan açıklanabilir V34 karar alanları ekler."""
    if found is None or found.empty:
        return found
    now = now or datetime.now(IST)
    snap = market_snapshot(now)
    out = found.copy()
    rows = []
    for _, row in out.iterrows():
        raw = _number(row, "PUAN", "V33_SKOR", default=0.0)
        entry = _number(row, "GIRIS", "FIYAT", default=np.nan)
        stop = _number(row, "STOP", default=np.nan)
        target = _number(row, "HEDEF", default=np.nan)
        risk = entry - stop if np.isfinite(entry) and np.isfinite(stop) else np.nan
        reward = target - entry if np.isfinite(entry) and np.isfinite(target) else np.nan
        rr = reward / risk if np.isfinite(risk) and risk > 0 and np.isfinite(reward) else np.nan
        rr_for_state = rr if np.isfinite(rr) else 1.0

        adjusted = raw
        if snap["PIYASA_REJIMI"] == "POZITIF":
            adjusted += 4
        elif snap["PIYASA_REJIMI"] == "NEGATIF":
            adjusted -= 7
        if np.isfinite(rr):
            adjusted += 3 if rr >= 1.5 else (-4 if rr < 1.0 else 0)
        if snap["VERI_KALITESI"] == "BAYAT_VERI":
            adjusted -= 8
        adjusted = max(0.0, min(100.0, adjusted))

        signal = row.get("SINYAL", row.get("TETIKLER", ""))
        state = _state(adjusted, signal, snap["PIYASA_REJIMI"], rr_for_state)
        if np.isfinite(stop):
            cancel = f"{stop:.2f} altinda periyot kapanisi"
        else:
            cancel = "Tetik seviyesi kaybi / hacim teyidi bozulmasi"
        if np.isfinite(target):
            positive = f"{target:.2f} hedefi; hacim ve VWAP korunmali"
        else:
            positive = "Onceki tepe kirilimi ve hacim devam teyidi"
        rows.append({
            "HAM_PUAN": raw,
            "V34_GUVEN": round(adjusted, 2),
            "SINYAL_DURUMU": state,
            "RISK_ODUL": round(rr, 2) if np.isfinite(rr) else np.nan,
            "OLUMLU_SENARYO": positive,
            "IPTAL_SARTI": cancel,
            **snap,
            "V34_NOT": "Ham motor puani korunur; V34 piyasa, risk/odul ve veri tazeligini ekler",
        })
    extra = pd.DataFrame(rows, index=out.index)
    for col in extra.columns:
        out[col] = extra[col]
    out["MOTOR"] = motor
    return out
