from __future__ import annotations

from hashlib import sha1
import numpy as np
import pandas as pd


TARGETS = (5, 7, 9)


def candidate_id(signal_date, motor, symbol, slot):
    """Ayni aday tekrar taransa da degismeyen kisa kimlik."""
    raw = f"{signal_date}|{motor}|{symbol}|{slot}".upper().encode("utf-8")
    return sha1(raw).hexdigest()[:16].upper()


def initialise_rows(frame, motor, now, slot):
    """Motor secimini degistirmeden izleme alanlarini ekler."""
    out = frame.copy()
    signal_date = now.strftime("%Y-%m-%d")
    out["ADAY_ID"] = [candidate_id(signal_date, motor, s, slot) for s in out["HISSE"]]
    out["ADAY_DURUMU"] = "ADAY"
    out["SON_DEGERLENDIRME"] = ""
    out["MFE_%"] = np.nan
    out["MAE_%"] = np.nan
    out["HEDEFTEN_GERI_VERME_%"] = np.nan
    out["ILK_5_ZAMANI"] = ""
    out["ILK_7_ZAMANI"] = ""
    out["ILK_9_ZAMANI"] = ""
    out["STOP_ZAMANI"] = ""
    out["ILK_SONUC"] = "BEKLIYOR"
    return out


def _first_time(mask):
    hits = mask[mask]
    return "" if hits.empty else pd.Timestamp(hits.index[0]).strftime("%Y-%m-%d %H:%M:%S")


def evaluate_path(row, bars, entry, evaluated_at):
    """Tamamlanmis barlardan MFE/MAE ve ilk hedef/stop olaylarini hesaplar.

    Ayni bar icinde hedef ve stop gorulurse OHLC sirayi gostermedigi icin
    ihtiyatli sonuc STOP kabul edilir.
    """
    result = {}
    if bars is None or bars.empty or not np.isfinite(entry) or entry <= 0:
        return result

    x = bars.sort_index().copy()
    highs = pd.to_numeric(x["High"], errors="coerce")
    lows = pd.to_numeric(x["Low"], errors="coerce")
    closes = pd.to_numeric(x["Close"], errors="coerce")
    mfe = 100 * (float(highs.max()) / entry - 1)
    mae = 100 * (float(lows.min()) / entry - 1)
    final_return = 100 * (float(closes.iloc[-1]) / entry - 1)
    result.update({
        "MFE_%": mfe,
        "MAE_%": mae,
        "HEDEFTEN_GERI_VERME_%": mfe - final_return,
        "SON_DEGERLENDIRME": evaluated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "ADAY_DURUMU": "IZLENIYOR",
    })

    target_times = {}
    for target in TARGETS:
        key = f"ILK_{target}_ZAMANI"
        target_times[target] = _first_time(highs >= entry * (1 + target / 100))
        result[key] = target_times[target]

    stop = pd.to_numeric(pd.Series([row.get("STOP", np.nan)]), errors="coerce").iloc[0]
    stop_time = _first_time(lows <= stop) if np.isfinite(stop) and stop > 0 else ""
    result["STOP_ZAMANI"] = stop_time

    first_target = next((target_times[t] for t in TARGETS if target_times[t]), "")
    if stop_time and first_target:
        stop_ts, target_ts = pd.Timestamp(stop_time), pd.Timestamp(first_target)
        # Esit zaman ayni OHLC baridir; konservatif olarak STOP.
        result["ILK_SONUC"] = "STOP_ONCE" if stop_ts <= target_ts else "HEDEF_ONCE"
        result["ADAY_DURUMU"] = "SONUCLANDI"
    elif first_target:
        result["ILK_SONUC"] = "HEDEF_ONCE"
    elif stop_time:
        result["ILK_SONUC"] = "STOP_ONCE"
        result["ADAY_DURUMU"] = "SONUCLANDI"
    else:
        result["ILK_SONUC"] = "BEKLIYOR"
    return result


def apply_result(frame, idx, values):
    for key, value in values.items():
        if key not in frame.columns:
            frame[key] = np.nan
        frame.at[idx, key] = value

