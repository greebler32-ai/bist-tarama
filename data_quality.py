"""Ortak mum tamamlama ve seviye kontrolu."""
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
IST=ZoneInfo('Europe/Istanbul')


def completed_daily(data, now=None):
    if data is None or data.empty:return pd.DataFrame() if data is None else data.copy()
    x=data.copy(); idx=pd.DatetimeIndex(x.index)
    if idx.tz is not None:idx=idx.tz_convert(IST).tz_localize(None)
    x.index=idx.normalize();x=x[~x.index.duplicated(keep='last')].sort_index()
    now=now or datetime.now(IST)
    today=pd.Timestamp(now.date())
    # Gecmis kapanisi silme; sadece bugunun acik seans mumunu disla.
    x=x[x.index<=today]
    if (now.hour,now.minute)<(18,10):x=x[x.index<today]
    return x


def valid_long(entry, stop, target):
    try:return all(np.isfinite(float(v)) for v in (entry,stop,target)) and 0<float(stop)<float(entry)<float(target)
    except (TypeError,ValueError):return False
