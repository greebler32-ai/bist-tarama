from __future__ import annotations
import math,time
from typing import Dict,Iterable,List,Optional
import numpy as np
import pandas as pd
import yfinance as yf
from symbols import get_bist_symbols

# VIDEO 6 — AYRI TARAMA | GUNLUK | Fisher(5) + MA Deviation(21)

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

SOURCE_INTERVAL='1d'; DOWNLOAD_PERIOD='1y'; MINIMUM_CANDLES=80; BATCH_SIZE=60
DOWNLOAD_TIMEOUT_SECONDS=20; MAX_RESULTS=25; MINIMUM_SCORE=65
FISHER_LENGTH=5; MA_LENGTH=21; ATR_PERIOD=14
MAX_DAILY_CHANGE_PCT=6.0; MAX_3DAY_RISE_PCT=12.0; MAX_5DAY_RISE_PCT=18.0
MAX_POSITIVE_DEVIATION_PCT=4.0

def split_batches(items,size):
    for i in range(0,len(items),size): yield items[i:i+size]

def download_batch(symbols):
    try: return yf.download(tickers=symbols,period=DOWNLOAD_PERIOD,interval=SOURCE_INTERVAL,group_by='ticker',auto_adjust=False,prepost=False,progress=False,threads=True,timeout=DOWNLOAD_TIMEOUT_SECONDS)
    except Exception as e: print(f'İndirme hatası: {e}'); return pd.DataFrame()

def extract_symbol_data(d,symbol,count):
    if d is None or d.empty:return pd.DataFrame()
    try:
        if isinstance(d.columns,pd.MultiIndex):
            l0=d.columns.get_level_values(0); l1=d.columns.get_level_values(1)
            if symbol in l0:f=d[symbol].copy()
            elif symbol in l1:f=d.xs(symbol,axis=1,level=1,drop_level=True).copy()
            else:return pd.DataFrame()
        elif count==1:f=d.copy()
        else:return pd.DataFrame()
    except (KeyError,ValueError):return pd.DataFrame()
    req=['Open','High','Low','Close','Volume']
    if any(x not in f.columns for x in req):return pd.DataFrame()
    f=f[req].apply(pd.to_numeric,errors='coerce').dropna(subset=['Open','High','Low','Close'])
    return f[~f.index.duplicated(keep='last')].sort_index()

def fisher_transform(high,low,length=FISHER_LENGTH):
    med=(high+low)/2; hi=med.rolling(length).max(); lo=med.rolling(length).min()
    val=pd.Series(index=med.index,dtype=float); fish=pd.Series(index=med.index,dtype=float)
    pv=0.; pf=0.
    for i in range(len(med)):
        if i<length-1 or pd.isna(hi.iloc[i]) or pd.isna(lo.iloc[i]): val.iloc[i]=np.nan; fish.iloc[i]=np.nan; continue
        rng=float(hi.iloc[i]-lo.iloc[i]); raw=0. if rng==0 else 2*((float(med.iloc[i])-float(lo.iloc[i]))/rng-.5)
        v=max(min(.33*raw+.67*pv,.999),-.999); f=.5*math.log((1+v)/(1-v))+.5*pf
        val.iloc[i]=v; fish.iloc[i]=f; pv=v; pf=f
    return fish,fish.shift(1)

def atr(d,p=ATR_PERIOD):
    pc=d['Close'].shift(1); tr=pd.concat([d['High']-d['Low'],(d['High']-pc).abs(),(d['Low']-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/p,adjust=False,min_periods=p).mean()

def add_indicators(d):
    f=d.copy(); fish,trig=fisher_transform(f['High'],f['Low']); f['FISHER']=fish; f['TRIGGER']=trig
    f['MA21']=f['Close'].rolling(MA_LENGTH).mean(); f['MADEV']=(f['Close']/f['MA21']-1)*100
    f['ATR']=atr(f); f['VOL20']=f['Volume'].rolling(20).mean(); f['CHG1']=f['Close'].pct_change()*100
    f['RISE3']=(f['Close']/f['Close'].shift(3)-1)*100; f['RISE5']=(f['Close']/f['Close'].shift(5)-1)*100
    return f.replace([np.inf,-np.inf],np.nan)

def analyze_symbol(symbol,d):
    if len(d)<MINIMUM_CANDLES:return None
    f=add_indicators(d).dropna();
    if len(f)<4:return None
    c,p=f.iloc[-1],f.iloc[-2]
    close=float(c.Close); op=float(c.Open); low=float(c.Low); fish=float(c.FISHER); fishp=float(p.FISHER); trig=float(c.TRIGGER); trigp=float(p.TRIGGER)
    dev=float(c.MADEV); devp=float(p.MADEV); a=float(c.ATR); chg=float(c.CHG1); r3=float(c.RISE3); r5=float(c.RISE5); vol=float(c.Volume); v20=float(c.VOL20)
    cross=fish>trig and fishp<=trigp; fisher_dip=min(fishp,trigp)<=0; deep=min(fishp,trigp)<=-1
    dev_rising=dev>devp; dev_negative=dev<0; dev_cross=dev>=0 and devp<0
    # Videoya en yakin ana sinyal: Fisher(5) dipten yukari keser, MA Deviation(21) negatif bolgeden yukari doner.
    if not (cross and fisher_dip and dev_rising and (dev_negative or dev_cross)):return None
    # Hareketini yapmis hisseleri ele
    if chg>=MAX_DAILY_CHANGE_PCT or r3>=MAX_3DAY_RISE_PCT or r5>=MAX_5DAY_RISE_PCT:return None
    if dev>MAX_POSITIVE_DEVIATION_PCT:return None
    score=50
    if deep:score+=15
    elif min(fishp,trigp)<=-.5:score+=10
    if dev_cross:score+=15
    elif dev<0:score+=10
    if dev-devp>=.5:score+=8
    if close>op:score+=5
    if vol>v20:score+=7
    score=min(score,100)
    if score<MINIMUM_SCORE:return None
    recent_low=float(f.Low.tail(5).min()); stop=min(recent_low,low)-.15*a; stop=min(stop,close*.995)
    target=min(max(close+2*a,close*1.05),close*1.10); gain=(target/close-1)*100
    sig='FISHER5 + MADEV21 DİP DÖNÜŞ' if dev<0 else 'FISHER5 + MADEV21 SIFIR KIRILIM'
    dec='GÜÇLÜ AL' if score>=85 else 'AL' if score>=72 else 'TAKİP'
    return {'symbol':symbol.replace('.IS',''),'signal':sig,'score':int(score),'entry':close,'stop':stop,'target':target,'gain_pct':gain,'decision':dec,'dev':dev}

def format_table(ss):
    h=['HİSSE','SİNYAL','PUAN','GİRİŞ','STOP','HEDEF','KAZANÇ %','KARAR']; rows=[]
    for s in ss:rows.append([s['symbol'],s['signal'],str(s['score']),f"{s['entry']:.2f}",f"{s['stop']:.2f}",f"{s['target']:.2f}",f"%{s['gain_pct']:.2f}",s['decision']])
    w=[max(len(h[i]),max((len(r[i]) for r in rows),default=0)) for i in range(len(h))]; sep='+'+'+'.join('-'*(x+2) for x in w)+'+'
    out=[sep,'| '+' | '.join(h[i].ljust(w[i]) for i in range(len(h)))+' |',sep]
    out += ['| '+' | '.join(r[i].ljust(w[i]) for i in range(len(r)))+' |' for r in rows]; out.append(sep); return '\n'.join(out)

def run_video6_scan():
    symbols=get_bist_symbols(); res=[]; analyzed=failed=0; started=time.perf_counter(); batches=list(split_batches(symbols,BATCH_SIZE))
    for no,b in enumerate(batches,1):
        print(f'Grup {no}/{len(batches)} indiriliyor ({len(b)} hisse)...'); dl=download_batch(b)
        for s in b:
            d=extract_symbol_data(dl,s,len(b))
            if d.empty:failed+=1; continue
            analyzed+=1; x=analyze_symbol(s,d)
            if x:res.append(x)
    res.sort(key=lambda x:(x['score'],-abs(x['dev'])),reverse=True); res=res[:MAX_RESULTS]; elapsed=time.perf_counter()-started
    print('\n'+'='*100); print('BIST | VİDEO 6 TARAMASI | GÜNLÜK'); print(f'Analiz: {analyzed} | Alınamayan: {failed} | Bulunan: {len(res)} | Süre: {elapsed:.1f} sn')
    print('Koşul: Fisher(5) dipte yukarı kesişim + MA Deviation(21) negatif bölgede yukarı dönüş'); print('Ek filtre: hareketini yapmış / aşırı yükselmiş hisseler elenir'); print('='*100)
    print(format_table(res) if res else 'Koşulları sağlayan hisse bulunmadı.'); return res

if __name__=='__main__':run_video6_scan()
