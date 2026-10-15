"""OHLCV birikim/dagitim izi; kurum veya kisi kimligi tespit etmez."""
import numpy as np
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from v19_paths import result_file


def analyse(bars, symbol):
    x = bars[['Open','High','Low','Close','Volume']].apply(pd.to_numeric, errors='coerce').dropna()
    x = x[(x.Close > 0) & (x.Volume >= 0) & (x.High >= x.Low)]
    if len(x) < 60: return None
    c,h,l,v = x.Close,x.High,x.Low,x.Volume
    avg = v.iloc[-21:-1].mean()
    if avg <= 0: return None
    rvol = float(v.iloc[-1]/avg)
    spread = (h-l).replace(0,np.nan)
    flow = ((2*c-h-l)/spread).fillna(0)*v
    cmf = float(flow.tail(20).sum()/v.tail(20).sum()) if v.tail(20).sum() else 0
    obv_delta = float((np.sign(c.diff()).fillna(0)*v).tail(5).sum()/v.tail(5).sum()) if v.tail(5).sum() else 0
    ret = float((c.iloc[-1]/c.iloc[-6]-1)*100)
    pos = float(((c.iloc[-1]-l.iloc[-1])/(h.iloc[-1]-l.iloc[-1]))) if h.iloc[-1]>l.iloc[-1] else .5
    score = int(25*(rvol>=1.5)+25*(cmf>=.10)+20*(obv_delta>=.20)+15*(pos>=.65)+15*(0<=ret<=7))
    distribution = rvol>=1.5 and cmf<-.10 and obv_delta<-.20 and pos<=.35
    state = 'DAGITIM_IZI' if distribution else 'GUCLU_ALIM_IZI' if score>=85 else 'BIRIKIM_ADAYI' if score>=60 else 'BELIRGIN_IZ_YOK'
    if state == 'BELIRGIN_IZ_YOK': return None
    from daily_trade_plan import trade_plan
    plan=trade_plan(x) if state in ('BIRIKIM_ADAYI','GUCLU_ALIM_IZI') else {}
    return {**plan,'HISSE':symbol.removesuffix('.IS'),'VERI_TARIHI':str(x.index[-1].date()),'FIYAT':round(float(c.iloc[-1]),4), 'BALINA_IZI_SKOR':score,'ADAY_TIPI':state,'RVOL':round(rvol,3),'CMF20':round(cmf,3),'OBV5_ORAN':round(obv_delta,3),'RET5':round(ret,3),'VERI_TURU':'FIYAT_HACIM_PROXY','KURUM_TEYIDI':'YOK'}


def main():
    import yfinance as yf
    from symbols import get_bist_symbols
    today = datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%Y-%m-%d')
    rows=[]; errors=[]
    print('BALINA IZI | Tamamlanmis gunluk mumlar | Kurum teyidi yok; AL sinyali degildir.')
    for s in get_bist_symbols():
        try:
            x=yf.download(s,period='6mo',interval='1d',auto_adjust=False,progress=False,threads=False,timeout=15)
            if isinstance(x.columns,pd.MultiIndex): x.columns=x.columns.get_level_values(0)
            x=x[[str(d.date())<today for d in x.index]]
            if x.empty: raise ValueError('Veri bos')
            row=analyse(x,s)
            if row: rows.append(row)
        except Exception as exc: errors.append({'HISSE':s,'HATA':str(exc)})
    df=pd.DataFrame(rows)
    if not df.empty: df=df.sort_values('BALINA_IZI_SKOR',ascending=False)
    else: df=pd.DataFrame(columns=['HISSE','FIYAT','BALINA_IZI_SKOR','ADAY_TIPI'])
    df.to_csv(result_file('BALINA_IZI_ADAYLARI.csv'),index=False,encoding='utf-8-sig')
    pd.DataFrame(errors,columns=['HISSE','HATA']).to_csv(result_file('BALINA_IZI_VERI_HATALARI.csv'),index=False,encoding='utf-8-sig')
    print(df.head(20).to_string(index=False) if not df.empty else 'Belirgin aday yok.')
    print(f'Veri hatasi: {len(errors)}. Tum adaylar CSV dosyasina kaydedildi.')
    return df
