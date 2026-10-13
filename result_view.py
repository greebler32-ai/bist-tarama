"""Tarama sonucunda yalniz kullanicinin istedigi bes alan."""
import numpy as np
import pandas as pd

def trade_view(frame):
    frame=frame.copy()
    # Teknik puan gorunmez; liste sirasi puana gore belirlenir.
    score=next((c for c in ['V33_SKOR','BIRLESIK_SKOR','ERKEN3G_SKOR','PATLAMA_PUANI','BALINA_IZI_SKOR','PUAN','score','avg_score','SKOR'] if c in frame),None)
    if score:
        frame['_sirala']=pd.to_numeric(frame[score],errors='coerce')
        frame=frame.sort_values('_sirala',ascending=False,kind='stable',na_position='last')
    if 'V33_SKOR' in frame:frame=frame.head(10)
    frame=frame.reset_index(drop=True)
    out=pd.DataFrame(index=frame.index)
    out['Sıra']=range(1,len(frame)+1)
    def first(names,numeric=True):
        value=pd.Series(np.nan if numeric else '',index=frame.index)
        for name in names:
            if name not in frame:continue
            source=pd.to_numeric(frame[name],errors='coerce') if numeric else frame[name].replace('',np.nan)
            if numeric:source=source.where(np.isfinite(source))
            value=value.where(value.notna() if numeric else (value.notna() & value.ne('')),source)
        return value
    out['Hisse']=first(['HISSE','symbol','SYMBOL','Sembol','ticker'],False)
    out['Puan']=pd.to_numeric(frame[score],errors='coerce') if score else np.nan
    out['Giriş Fiyatı']=first(['TETIK_GIRIS','CANLI_GIRIS','GIRIS','entry','FIYAT','KAPANIS'])
    out['Hedef Fiyatı']=first(['HEDEF','target','H1'])
    out['Stop Loss']=first(['STOP','stop','YAPI_BOZULMA'])
    entry=out['Giriş Fiyatı'];target=out['Hedef Fiyatı']
    out['Kazanç %']=((target/entry.where(entry>0))-1)*100
    return out
