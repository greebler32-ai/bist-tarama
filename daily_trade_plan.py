"""Tamamlanmis mumlardan teknik referans giris/hedef/yapi stopu."""
import numpy as np
import pandas as pd

def trade_plan(bars):
    x=bars[['High','Low','Close']].apply(pd.to_numeric,errors='coerce')
    if len(x)<20:return {}
    last=x.tail(20)
    if not np.isfinite(last.to_numpy()).all():return {}
    if not ((last.Low>0)&(last.High>=last.Low)&(last.Close>=last.Low)&(last.Close<=last.High)).all():return {}
    entry=float(x.Close.iloc[-1])
    tr=pd.concat([x.High-x.Low,(x.High-x.Close.shift()).abs(),(x.Low-x.Close.shift()).abs()],axis=1).max(axis=1)
    atr=float(tr.tail(14).mean())
    if not np.isfinite(atr) or atr<=0 or entry<=0:return {}
    # Son 5 tamamlanmis mumun dip yapisi altina ATR tamponu.
    stop=max(entry*.01,min(float(x.Low.tail(5).min())-.25*atr,entry-.5*atr))
    # Onceki 20/40/60 mum tepelerinden fiyat ustundeki en yakin direnc.
    resistance=sorted({float(x.High.iloc[-n-1:-1].max()) for n in (20,40,60) if len(x)>n})
    valid=[r for r in resistance if np.isfinite(r) and r>=entry+.5*atr]
    target=valid[0] if valid else entry+2*atr
    rounded=[round(v,4) for v in (stop,entry,target)]
    if not 0<rounded[0]<rounded[1]<rounded[2]:return {}
    return {'GIRIS':round(entry,4),'HEDEF':round(target,4),'STOP':round(stop,4),'KAZANC_%':round(100*(target/entry-1),2),'HEDEF_YONTEMI':'ESKI_DIRENC' if valid else '2_ATR_UZATMA','STOP_YONTEMI':'5_MUM_DIP_EKSI_025_ATR','GIRIS_TURU':'SON_TAMAMLANMIS_KAPANIS'}
