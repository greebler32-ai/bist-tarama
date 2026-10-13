"""Gecikmeli 15dk veriden acik giris durumu. Islem emri uretmez."""
import numpy as np
import pandas as pd
from datetime import datetime,time
from zoneinfo import ZoneInfo
IST=ZoneInfo('Europe/Istanbul')


def classify(row, now=None):
    now=now or datetime.now(IST)
    def number(k):
        try: return float(row.get(k,np.nan))
        except (TypeError,ValueError): return np.nan
    entry=number('CANLI_GIRIS')
    base={'GIRIS_DURUMU':'TEYIT_BEKLIYOR','TETIK_GIRIS':np.nan,'GIRIS_VERI_TURU':'GECIKMELI_15DK','GIRIS_NEDENI':''}
    if not now.weekday()<5 or not time(10,0)<=now.time()<=time(18,0):
        return dict(base,GIRIS_DURUMU='SEANS_DISI',GIRIS_NEDENI='Seans saati disinda')
    try:
        stamp=pd.Timestamp(row.get('HISSE_BAR_ZAMANI'))
        if pd.isna(stamp): raise ValueError('Veri zamani yok')
        stamp=stamp.tz_localize(IST) if stamp.tzinfo is None else stamp.tz_convert(IST)
        lag=(pd.Timestamp(now)-stamp).total_seconds()/60
        if lag<15 or lag>40:
            return dict(base,GIRIS_DURUMU='VERI_TEYIDI_BEKLIYOR',GIRIS_NEDENI='Bar tamamlanmamis, gelecekte veya bayat')
    except (ValueError,TypeError):
        return dict(base,GIRIS_DURUMU='VERI_TEYIDI_BEKLIYOR',GIRIS_NEDENI='Hisse bar zamani yok')
    if not np.isfinite(entry) or entry<=0:
        return dict(base,GIRIS_NEDENI='Giris fiyati eksik')
    gates={'DONUS_PUAN':(62,True),'RVOL3':(1.05,True),'VWAP_%':(0,False),'DI_SPREAD':(0,False),'TEPKI_%':(2,True)}
    failed=[]
    for key,(level,inclusive) in gates.items():
        value=number(key)
        if not np.isfinite(value) or not (value>=level if inclusive else value>level): failed.append(key)
    if failed:return dict(base,GIRIS_NEDENI='Eksik teyit: '+', '.join(failed))
    return dict(base,GIRIS_DURUMU='GIRIS_TETIKLENDI',TETIK_GIRIS=entry,GIRIS_NEDENI='Tamamlanmis 15dk mum: hacim + VWAP + yon + tepki')
