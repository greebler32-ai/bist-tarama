from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import time
import numpy as np
import pandas as pd
import yfinance as yf
from symbols import get_bist_symbols
from v19_paths import result_file

IST=ZoneInfo('Europe/Istanbul')

def _flat(d):
    if d is None or d.empty: return pd.DataFrame()
    x=d.copy()
    if isinstance(x.columns,pd.MultiIndex): x.columns=[c[0] for c in x.columns]
    x.columns=[str(c).title() for c in x.columns]
    idx=pd.DatetimeIndex(x.index)
    if idx.tz is not None: idx=idx.tz_convert('Europe/Istanbul').tz_localize(None)
    x.index=idx
    return x

def _ema(s,n): return s.ewm(span=n,adjust=False).mean()

def _features(d):
    from data_quality import completed_daily
    x=completed_daily(_flat(d))
    if len(x)<150: return x
    c,h,l,v=x.Close,x.High,x.Low,x.Volume
    x['RET1']=c.pct_change()*100
    x['RET5']=(c/c.shift(5)-1)*100
    x['EMA9']=_ema(c,9); x['EMA21']=_ema(c,21); x['EMA50']=_ema(c,50)
    x['EMA9_SLOPE']=100*(x.EMA9/x.EMA9.shift(3)-1)
    x['EMA21_SLOPE']=100*(x.EMA21/x.EMA21.shift(5)-1)
    x['VMA20']=v.rolling(20).mean(); x['RVOL']=v/x.VMA20.replace(0,np.nan)
    x['VOL5_20']=v.rolling(5).mean()/x.VMA20.replace(0,np.nan)
    x['HIGH20_PRE']=h.shift(1).rolling(20).max()
    x['HIGH60_PRE']=h.shift(1).rolling(60).max()
    x['PEAK120_PRE']=h.shift(20).rolling(120).max()
    x['LOW20_PRE']=l.shift(1).rolling(20).min()
    x['BASE20_RANGE']=100*(x.HIGH20_PRE/x.LOW20_PRE-1)
    x['DRAWDOWN']=100*(x.LOW20_PRE/x.PEAK120_PRE-1)
    x['DIST_R20']=100*(c/x.HIGH20_PRE-1)
    x['CLV']=(c-l)/(h-l).replace(0,np.nan)
    mid=c.rolling(20).mean(); sd=c.rolling(20).std(ddof=0)
    x['BBW']=4*sd/mid.replace(0,np.nan)
    x['BBW_Q40']=x.BBW.rolling(120,min_periods=60).quantile(.40)
    return x

def _score(x):
    if x is None or x.empty or len(x)<150: return None
    r=x.iloc[-1]
    need=['Close','RET1','RET5','EMA9','EMA21','EMA50','EMA9_SLOPE','EMA21_SLOPE','RVOL','VOL5_20','HIGH20_PRE','BASE20_RANGE','DRAWDOWN','DIST_R20','CLV','BBW','BBW_Q40']
    if any(pd.isna(r.get(k)) for k in need): return None
    score=0; tags=[]
    # 1) DUSUS BITISI / DINLENME: sabit 3-4 ay şartı yok; karakter değişimi aranır.
    if r.DRAWDOWN <= -20: score+=18; tags.append('DERIN_DUSUS')
    elif r.DRAWDOWN <= -12: score+=10; tags.append('DUSUS')
    if r.BASE20_RANGE <= 15: score+=14; tags.append('20G_SIKISMA')
    elif r.BASE20_RANGE <= 22: score+=7
    if r.BBW <= r.BBW_Q40: score+=8; tags.append('VOLATILITE_DINLENME')
    # 2) UYANIS / PARA-HACIM PROXY
    if 1.25 <= r.RVOL <= 3.5: score+=16; tags.append('RVOL_GIRIS')
    elif 1.05 <= r.RVOL < 1.25: score+=8
    elif r.RVOL > 5: score-=8; tags.append('ASIRI_HACIM')
    if r.VOL5_20 >= 1.10: score+=8; tags.append('HACIM_DEVAM')
    # 3) TREND DONUSU
    if r.EMA9 > r.EMA21: score+=8; tags.append('EMA9_21')
    if r.EMA9_SLOPE > 0 and r.EMA21_SLOPE >= -0.3: score+=8; tags.append('EMA_DONUS')
    # 4) KIRILIM HAZIR / ILK KIRILIM
    if -3.0 <= r.DIST_R20 < 0: score+=12; tags.append('KIRILIM_HAZIR')
    elif 0 <= r.DIST_R20 <= 3.5: score+=14; tags.append('ILK_KIRILIM')
    elif r.DIST_R20 > 7: score-=12; tags.append('GEC_KALDI')
    if r.CLV >= .70: score+=8; tags.append('GUCLU_KAPANIS')
    if 0 <= r.RET1 <= 5: score+=8; tags.append('ERKEN_HAREKET')
    elif r.RET1 > 7: score-=10; tags.append('GEC_CEZA')
    score=int(max(0,min(100,round(score))))
    if r.DIST_R20>7 or r.RET1>8: stage='GEC_KALDI'
    elif score>=72 and -3<=r.DIST_R20<=3.5 and r.RVOL>=1.05: stage='KIRILIM_HAZIR'
    elif score>=62 and r.EMA9_SLOPE>0: stage='UYANIS'
    elif r.BASE20_RANGE<=18 and r.DRAWDOWN<=-12: stage='DINLENME'
    else: stage='TAKIP'
    return {'PUAN':score,'DURUM':stage,'SINYAL':'+'.join(tags),'GIRIS':float(r.Close),'RET1_%':float(r.RET1),'RET5_%':float(r.RET5),'RVOL':float(r.RVOL),'VOL5_20':float(r.VOL5_20),'DRAWDOWN_%':float(r.DRAWDOWN),'BASE20_RANGE_%':float(r.BASE20_RANGE),'DIST_R20_%':float(r.DIST_R20),'CLV':float(r.CLV)}

def main():
    print("\nV32 GUN SONU HAZIRLIK HAVUZU - UYARI: D1 TOP10 V31 TESTI RED; CANLI TEYIT ZORUNLU")
    now=datetime.now(IST)
    print('\n'+'='*120)
    print('TREND DEVAM V2 | DUSUS -> DINLENME -> UYANIS -> KIRILIM HAZIR')
    print(f'Tarama zamani: {now:%Y-%m-%d %H:%M}')
    print('='*120)
    print('Amaç: MARTI/NIBAS/KARSN tipi karakter degisimini hareket gec kalmadan yakalamak.')
    print('Not: RVOL gercek para akisi degil, hacim proxy\'sidir; tek basina AL sinyali sayilmaz.\n')
    rows=[]; syms=get_bist_symbols()
    for i,s in enumerate(syms,1):
        print(f'\r[{i}/{len(syms)}] {s:<14}',end='',flush=True)
        try:
            d=yf.download(s,period='18mo',interval='1d',auto_adjust=False,progress=False,threads=False,timeout=12)
            rec=_score(_features(d))
            if rec:
                rec['HISSE']=s.replace('.IS',''); rows.append(rec)
        except Exception: pass
        time.sleep(.002)
    print()
    if not rows: print('Aday bulunamadi.'); return pd.DataFrame()
    df=pd.DataFrame(rows)
    order={'KIRILIM_HAZIR':4,'UYANIS':3,'DINLENME':2,'TAKIP':1,'GEC_KALDI':0}
    df['_S']=df.DURUM.map(order).fillna(0)
    df=df.sort_values(['_S','PUAN','RVOL'],ascending=False).drop(columns='_S')
    useful=df[df.DURUM!='GEC_KALDI'].head(30).copy()
    view=useful.head(10)[['HISSE','PUAN','DURUM','GIRIS','RET1_%','RVOL','DRAWDOWN_%','BASE20_RANGE_%','DIST_R20_%','SINYAL']]
    with pd.option_context('display.max_colwidth',52,'display.width',190):
        print('\nTREND DEVAM V2 TOP10'); print(view.to_string(index=False))
    fn=f'TREND_DEVAM_V2_{now:%Y%m%d_%H%M}.csv'
    useful.assign(TARAMA_ZAMANI=now.strftime('%Y-%m-%d %H:%M')).to_csv(result_file(fn),index=False,encoding='utf-8-sig')
    print('\nKaydedildi:',result_file(fn))
    return useful

if __name__=='__main__': main()
