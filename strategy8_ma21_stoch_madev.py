from __future__ import annotations
import math, time
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
import yfinance as yf
from symbols import get_bist_symbols


# --- MASTER SECILEBILIR ZAMAN DILIMI ---
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
    required = [c for c in ["Open","High","Low","Close"] if c in out.columns]
    return out.dropna(subset=required)
# --- /MASTER SECILEBILIR ZAMAN DILIMI ---

BIST_SYMBOLS = get_bist_symbols()
PERIOD = "1y"
INTERVAL = "1d"
MAX_RESULTS = 30

# Videoda net görünen yapı:
# MA 21 Close + Stoch RSI 3,3,14,14 + MA Deviation 21
MA_LEN = 21
RSI_LEN = 14
STOCH_LEN = 14
K_SMOOTH = 3
D_SMOOTH = 3
DEV_LEN = 21

# Hareketini yapmış hisseleri ele
MAX_DAILY_GAIN = 6.0
MAX_3BAR_GAIN = 12.0
MAX_5BAR_GAIN = 18.0
MAX_MA_DISTANCE = 7.0

def _s(x):
    return x.iloc[:,0] if isinstance(x, pd.DataFrame) else x

def rsi(s, n=14):
    s=_s(s).astype(float)
    d=s.diff()
    g=d.clip(lower=0)
    l=-d.clip(upper=0)
    ag=g.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    al=l.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    rs=ag/al.replace(0,np.nan)
    return 100-(100/(1+rs))

def stoch_rsi(close):
    r=rsi(close, RSI_LEN)
    lo=r.rolling(STOCH_LEN).min()
    hi=r.rolling(STOCH_LEN).max()
    raw=100*(r-lo)/(hi-lo).replace(0,np.nan)
    k=raw.rolling(K_SMOOTH).mean()
    d=k.rolling(D_SMOOTH).mean()
    return k,d

def pct(a,b):
    return (a/b-1)*100 if b else 0.0

def analyze_symbol(symbol: str) -> Optional[Dict]:
    ticker=symbol if symbol.endswith(".IS") else symbol+".IS"
    try:
        _dl_period, _dl_interval = _tf_params()
        df=yf.download(ticker, period=_dl_period, interval=_dl_interval,
                       auto_adjust=False, progress=False, threads=False)
        df=_tf_resample(df)
    except Exception:
        return None
    if df is None or len(df)<80:
        return None
    if isinstance(df.columns,pd.MultiIndex):
        df.columns=df.columns.get_level_values(0)
    req=["Open","High","Low","Close","Volume"]
    if any(c not in df.columns for c in req):
        return None
    df=df.dropna(subset=req).copy()
    close=_s(df["Close"]).astype(float)
    high=_s(df["High"]).astype(float)
    low=_s(df["Low"]).astype(float)

    # Videodaki siyah MA çizgisine en yakın standart eşdeğer: EMA21.
    df["MA21"]=close.ewm(span=MA_LEN,adjust=False).mean()
    k,d=stoch_rsi(close)
    df["K"],df["D"]=k,d

    # MA Deviation: fiyatın 21 MA'dan yüzde sapması.
    df["DEV"]=100*(close-df["MA21"])/df["MA21"]
    df["DEV_SIG"]=df["DEV"].ewm(span=5,adjust=False).mean()

    df=df.dropna().copy()
    if len(df)<10:
        return None

    x=df.iloc[-1]; p=df.iloc[-2]
    c=float(x["Close"]); ma=float(x["MA21"])
    kval=float(x["K"]); dval=float(x["D"])
    dev=float(x["DEV"]); devsig=float(x["DEV_SIG"])

    stoch_cross = float(p["K"]) <= float(p["D"]) and kval > dval
    stoch_rising = kval > dval and kval > float(p["K"])
    stoch_dip = min(kval,dval) < 35

    dev_cross = float(p["DEV"]) <= float(p["DEV_SIG"]) and dev > devsig
    dev_turn = dev > float(p["DEV"]) and dev < 1.5
    dev_negative_turn = dev < 0 and dev > float(p["DEV"])

    ma_reclaim = float(p["Close"]) <= float(p["MA21"]) and c > ma
    above_ma = c > ma and ma >= float(p["MA21"])

    daily=pct(c,float(p["Close"]))
    g3=pct(c,float(df.iloc[-4]["Close"])) if len(df)>=4 else 0
    g5=pct(c,float(df.iloc[-6]["Close"])) if len(df)>=6 else 0
    madist=pct(c,ma)

    if daily>=MAX_DAILY_GAIN or g3>=MAX_3BAR_GAIN or g5>=MAX_5BAR_GAIN:
        return None
    if madist>MAX_MA_DISTANCE:
        return None

    # Videodaki ana fikir: Stoch RSI dipten yukarı + MA Deviation negatif/dip bölgeden yukarı,
    # tercihen fiyatın MA21'i geri alması veya MA21 üzerinde güçlenmesi.
    momentum = stoch_cross and stoch_dip
    deviation = dev_cross or dev_negative_turn or dev_turn
    trend = ma_reclaim or above_ma
    if not (momentum and deviation and trend):
        return None

    score=55
    labels=["STOCH RSI DİP KESİŞİM"]
    if stoch_cross and min(kval,dval)<20:
        score+=10
    if dev_cross:
        score+=15; labels.append("MADEV21 KESİŞİM")
    elif dev_negative_turn:
        score+=10; labels.append("MADEV21 DİP DÖNÜŞ")
    if ma_reclaim:
        score+=15; labels.append("MA21 GERİ ALIM")
    elif above_ma:
        score+=8; labels.append("MA21 ÜSTÜ")
    score=min(100,score)

    tr=pd.concat([high-low,(high-close.shift()).abs(),(low-close.shift()).abs()],axis=1).max(axis=1)
    atr=float(tr.rolling(14).mean().iloc[-1])
    entry=c
    stop=max(ma*0.985, c-1.5*atr)
    if stop>=entry: stop=entry*0.96
    risk=max(entry-stop,entry*0.025)
    target=entry+2*risk
    gain=pct(target,entry)
    decision="GÜÇLÜ AL" if score>=85 else ("AL" if score>=75 else "TAKİP")
    return dict(symbol=symbol.replace(".IS",""), signal=" + ".join(labels),
                score=int(score), entry=entry, stop=stop, target=target,
                gain_pct=gain, decision=decision)

def format_table(rows):
    headers=["HİSSE","SİNYAL","PUAN","GİRİŞ","STOP","HEDEF","KAZANÇ %","KARAR"]
    data=[[r["symbol"],r["signal"],str(r["score"]),f'{r["entry"]:.2f}',
           f'{r["stop"]:.2f}',f'{r["target"]:.2f}',f'%{r["gain_pct"]:.2f}',r["decision"]] for r in rows]
    widths=[max(len(headers[i]),max((len(x[i]) for x in data),default=0)) for i in range(len(headers))]
    sep="+"+"+".join("-"*(w+2) for w in widths)+"+"
    out=[sep,"| "+" | ".join(headers[i].ljust(widths[i]) for i in range(len(headers)))+" |",sep]
    for row in data:
        out.append("| "+" | ".join(row[i].ljust(widths[i]) for i in range(len(row)))+" |")
    out.append(sep)
    return "\n".join(out)

def run_video8_scan() -> List[Dict]:
    results=[]; errors=0; start=time.time()
    print("="*100)
    print("BIST | VİDEO 8 TARAMASI | GÜNLÜK")
    print("Koşul: MA21 + STOCH RSI(3,3,14,14) dip kesişim + MA DEVIATION(21) yukarı dönüş")
    print("Aşırı yükselmiş / hareketini yapmış hisseler elenir.")
    print("="*100)
    total=len(BIST_SYMBOLS)
    for i,symbol in enumerate(BIST_SYMBOLS,1):
        try:
            hit=analyze_symbol(symbol)
            if hit: results.append(hit)
        except Exception:
            errors+=1
        if i%50==0 or i==total:
            print(f"Taranıyor: {i}/{total} | Bulunan: {len(results)}",end="\r")
    results.sort(key=lambda x:(x["score"],x["gain_pct"]),reverse=True)
    results=results[:MAX_RESULTS]
    print(" "*100,end="\r")
    print(f"Analiz: {total} | Hata: {errors} | Bulunan: {len(results)} | Süre: {time.time()-start:.1f} sn")
    if results: print(format_table(results))
    else: print("Koşulları sağlayan hisse bulunamadı.")
    return results

if __name__=="__main__":
    run_video8_scan()
