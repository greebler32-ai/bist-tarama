from __future__ import annotations
from v19_paths import result_file, results_dir
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import yfinance as yf

import os

# Windows terminalinde ANSI renklerini etkinleştir.
try:
    os.system("")
except Exception:
    pass

RESET="\033[0m"
BOLD="\033[1m"
CYAN="\033[96m"
GREEN="\033[92m"
RED="\033[91m"
YELLOW="\033[93m"
BLUE="\033[94m"
MAGENTA="\033[95m"
WHITE="\033[97m"
DIM="\033[90m"

def c(text, color):
    return f"{color}{text}{RESET}"

def center(text, width):
    s=str(text)
    if len(s)>=width:
        return s[:width]
    return s.center(width)

def pad(text, width, align="left"):
    s=str(text)
    if len(s)>width:
        s=s[:width]
    if align=="right":
        return s.rjust(width)
    if align=="center":
        return s.center(width)
    return s.ljust(width)
from symbols import get_bist_symbols

IST=ZoneInfo("Europe/Istanbul")
TOP_N=20

TF_CFG={
 "5m": ("5 DAKIKA","5m","10d"),
 "15m":("15 DAKIKA","15m","20d"),
 "1h": ("1 SAAT","60m","60d"),
 "2h": ("2 SAAT","60m","60d"),
 "4h": ("4 SAAT","60m","60d"),
 "1d": ("GUNLUK","1d","6mo"),
}

def flat(d):
    if d is None or d.empty:return pd.DataFrame()
    x=d.copy()
    if isinstance(x.columns,pd.MultiIndex):x.columns=[c[0] for c in x.columns]
    x.columns=[str(c).title() for c in x.columns]
    idx=pd.DatetimeIndex(x.index)
    if idx.tz is not None:idx=idx.tz_convert("Europe/Istanbul").tz_localize(None)
    x.index=idx
    return x

def resample_ohlcv(x,hours):
    if x.empty:return x
    rule=f"{hours}h"
    return x.resample(rule,origin="start_day",offset="10h").agg(
        {"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}
    ).dropna()

def ema(s,n):return s.ewm(span=n,adjust=False).mean()

def rsi(c,n=14):
    d=c.diff();up=d.clip(lower=0);dn=-d.clip(upper=0)
    au=up.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    ad=dn.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    return 100-100/(1+(au/ad.replace(0,np.nan)))

def atr(x,n=14):
    pc=x.Close.shift()
    tr=pd.concat([x.High-x.Low,(x.High-pc).abs(),(x.Low-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean()

def mfi(x,n=14):
    tp=(x.High+x.Low+x.Close)/3;mf=tp*x.Volume
    pos=mf.where(tp.diff()>0,0.0);neg=mf.where(tp.diff()<0,0.0).abs()
    return 100-100/(1+(pos.rolling(n).sum()/neg.rolling(n).sum().replace(0,np.nan)))

def adx_di(x,n=14):
    up=x.High.diff();dn=-x.Low.diff()
    pdm=up.where((up>dn)&(up>0),0.0);mdm=dn.where((dn>up)&(dn>0),0.0)
    pc=x.Close.shift()
    tr=pd.concat([x.High-x.Low,(x.High-pc).abs(),(x.Low-pc).abs()],axis=1).max(axis=1)
    a=tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    pdi=100*pdm.ewm(alpha=1/n,adjust=False,min_periods=n).mean()/a.replace(0,np.nan)
    mdi=100*mdm.ewm(alpha=1/n,adjust=False,min_periods=n).mean()/a.replace(0,np.nan)
    dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    return dx.ewm(alpha=1/n,adjust=False,min_periods=n).mean(),pdi,mdi

def features(d):
    x=flat(d)
    if len(x)<25:return x
    x["RET1"]=x.Close.pct_change()*100
    x["RET2"]=(x.Close/x.Close.shift(2)-1)*100
    x["RET3"]=(x.Close/x.Close.shift(3)-1)*100
    x["ATR_PCT"]=100*atr(x)/x.Close
    x["RANGE_PCT"]=100*(x.High-x.Low)/x.Close
    x["RVOL"]=x.Volume/x.Volume.rolling(20).mean()
    x["RVOL3"]=x.RVOL.rolling(3).mean()
    x["RSI"]=rsi(x.Close);x["MFI"]=mfi(x)
    adx,pdi,mdi=adx_di(x);x["ADX"]=adx;x["DI"]=pdi-mdi
    mid=x.Close.rolling(20).mean();sd=x.Close.rolling(20).std(ddof=0)
    up=mid+2*sd;lo=mid-2*sd
    x["BBW"]=(up-lo)/mid.replace(0,np.nan)
    tp=(x.High+x.Low+x.Close)/3
    vw=(tp*x.Volume).rolling(20).sum()/x.Volume.rolling(20).sum().replace(0,np.nan)
    x["VWAP_DIST"]=100*(x.Close/vw-1)
    x["EMA9"]=ema(x.Close,9);x["EMA21"]=ema(x.Close,21)
    x["TREND"]=100*(x.EMA9/x.EMA21-1)
    return x

def score(r):
    pts=0;tags=[]
    tests=[
      ("RANGE",12,r.RANGE_PCT>=2.0),("ATR",10,r.ATR_PCT>=2.0),
      ("RVOL3",16,r.RVOL3>=1.15),("RVOL",12,r.RVOL>=1.15),
      ("VWAP",14,r.VWAP_DIST>0),("DI",12,r.DI>5),
      ("MFI",8,58<=r.MFI<=92),("ADX",8,r.ADX>=20),
      ("TREND",8,r.TREND>0),("MOM",10,r.RET1>0 and r.RET2>0),
    ]
    for name,w,ok in tests:
        if bool(ok):pts+=w;tags.append(name)
    if r.RVOL>=1.5 and r.VWAP_DIST>0 and r.DI>0:
        pts+=10;tags.append("CANLI_TETIK")
    return min(100,pts),"+".join(tags)


def print_trade_table(view, title):
    """Dar terminale sigan, renkli ve okunakli trade tablosu."""
    widths = {
        "NO": 3,
        "HISSE": 7,
        "SINYAL": 29,
        "PUAN": 5,
        "GIRIS": 8,
        "STOP": 8,
        "HEDEF": 8,
        "KAZANC_%": 8,
        "KARAR": 13,
    }
    cols=["NO","HISSE","SINYAL","PUAN","GIRIS","STOP","HEDEF","KAZANC_%","KARAR"]

    def cell(v,w,align="center"):
        t=str(v)
        if len(t)>w:
            t=t[:max(1,w-2)]+".."
        if align=="left":
            return t.ljust(w)
        if align=="right":
            return t.rjust(w)
        return t.center(w)

    def border():
        return "+" + "+".join("-"*(widths[k]+2) for k in cols) + "+"

    total=len(border())
    print("\n"+c("="*total,DIM))
    print(c(center(title,total),BOLD+CYAN))
    print(c("="*total,DIM))

    labels={
        "NO":"#","HISSE":"HISSE","SINYAL":"SINYAL","PUAN":"PUAN",
        "GIRIS":"GIRIS","STOP":"STOP","HEDEF":"HEDEF","KAZANC_%":"KAZANC","KARAR":"KARAR"
    }
    hc={
        "NO":CYAN,"HISSE":CYAN,"SINYAL":MAGENTA,"PUAN":CYAN,
        "GIRIS":GREEN,"STOP":RED,"HEDEF":CYAN,"KAZANC_%":YELLOW,"KARAR":MAGENTA
    }

    header="|"
    for k in cols:
        header+=" "+c(cell(labels[k],widths[k]),BOLD+hc[k])+" |"
    print(header)
    print(c(border(),DIM))

    for no,(_,r) in enumerate(view.iterrows(),1):
        karar=str(r["KARAR"])
        if "COK GUCLU" in karar:
            kc=GREEN
        elif "GUCLU" in karar or "TAVAN ADAYI" in karar:
            kc=GREEN
        elif karar=="AL" or "ADAYI" in karar or karar=="IZLE":
            kc=YELLOW
        else:
            kc=BLUE

        raw_sig=str(r["SINYAL"]).upper().replace("_"," ")
        short=[]
        mapping=[
            ("CANLI TETIK","CT"),
            ("RV3++","RV3++"),("RV3+","RV3+"),("RV3","RV3"),
            ("VOL++","VOL++"),("VOL+","VOL+"),("VOL","VOL"),
            ("VW++","VW++"),("VW+","VW+"),("VWAP GERI ALDI","VW"),("VW","VW"),
            ("DI++","DI++"),("DI+","DI+"),("DI POZITIF","DI"),("DI","DI"),
            ("MOM++","MOM++"),("MOM+","MOM+"),("MOMENTUM","MOM"),("MOM","MOM"),
            ("TR++","TR++"),("TR+","TR+"),("TREND","TR"),("TR","TR"),
            ("MFI","MFI"),("RSI","RSI"),
            ("DIPTEN TEPKI","DIP"),("GUCLU TEPKI","GTP"),
            ("RNG","RNG"),("RANGE","RNG"),("ATR","ATR"),
        ]
        for needle,code in mapping:
            if needle in raw_sig and code not in short:
                short.append(code)
        sinyal="+".join(short[:7]) if short else raw_sig[:widths["SINYAL"]]
        sc=GREEN if any(x in short for x in ["CT","VW","VW+","VW++","RV3+","RV3++"]) else YELLOW

        vals={
            "NO":(no,CYAN+BOLD),
            "HISSE":(r["HISSE"],WHITE+BOLD),
            "SINYAL":(sinyal,sc),
            "PUAN":(int(r["PUAN"]),CYAN+BOLD),
            "GIRIS":(f'{float(r["GIRIS"]):.2f}',GREEN+BOLD),
            "STOP":(f'{float(r["STOP"]):.2f}',RED+BOLD),
            "HEDEF":(f'{float(r["HEDEF"]):.2f}',CYAN+BOLD),
            "KAZANC_%":(f'%{float(r["KAZANC_%"]):.2f}',YELLOW+BOLD),
            "KARAR":(karar,kc+BOLD),
        }

        row="|"
        for k in cols:
            v,col=vals[k]
            row+=" "+c(cell(v,widths[k],"left" if k=="SINYAL" else "center"),col)+" |"
        print(row)

    print(c(border(),DIM))

def choose_timeframe():
    print("\nCANLI TARAMA ZAMAN PERIYODU")
    print("[1] 5 DAKIKA")
    print("[2] 15 DAKIKA")
    print("[3] 1 SAAT")
    print("[4] 2 SAAT")
    print("[5] 4 SAAT")
    print("[6] GUNLUK")
    m={"1":"5m","2":"15m","3":"1h","4":"2h","5":"4h","6":"1d"}
    while True:
        c=input("Periyot seciminiz: ").strip()
        if c in m:return m[c]
        print("Gecersiz secim.")

def download_tf(s,tf):
    label,interval,period=TF_CFG[tf]
    d=yf.download(s,period=period,interval=interval,auto_adjust=False,
                  progress=False,threads=False)
    x=flat(d)
    if tf=="2h":x=resample_ohlcv(x,2)
    elif tf=="4h":x=resample_ohlcv(x,4)
    return x

def momentum_main(tf=None):
    tf=tf or choose_timeframe()
    label=TF_CFG[tf][0]
    now=datetime.now(IST)
    print("\n"+"="*118)
    print(f"V19.2 CANLI -> BUGUN KALAN SEANS %5-%10 TRADE ADAYLARI | {label}")
    print("Tarama zamani:",now.strftime("%Y-%m-%d %H:%M"))
    print("="*118)

    rows=[]
    syms=get_bist_symbols()
    for i,s in enumerate(syms,1):
        print(f"\r[{i}/{len(syms)}] {s:<14}",end="",flush=True)
        try:
            x=features(download_tf(s,tf))
            if x.empty:continue
            r=x.iloc[-1]
            sc,tags=score(r)
            rows.append([
              s.replace(".IS",""),sc,float(r.Close),r.RANGE_PCT,r.ATR_PCT,
              r.RVOL3,r.RVOL,r.VWAP_DIST,r.DI,r.MFI,r.ADX,r.RSI,r.TREND,tags
            ])
        except Exception:
            pass
        time.sleep(.004)
    print()

    if not rows:
        print("CANLI VERI BULUNAMADI.");return pd.DataFrame()

    df=pd.DataFrame(rows,columns=[
      "HISSE","PUAN","FIYAT","RANGE_%","ATR_%","RVOL3","RVOL","VWAP_%","DI_SPREAD",
      "MFI14","ADX14","RSI14","TREND_%","TETIKLER"
    ])

    # Canlı aday: hacim + VWAP + pozitif DI zorunlu. Top20 üst sınır.
    good=df[(df.PUAN>=62)&(df.RVOL3>=1.05)&(df["VWAP_%"]>0)&(df.DI_SPREAD>0)].copy()
    good=good.sort_values(["PUAN","RVOL3","DI_SPREAD"],ascending=False).head(TOP_N)

    if good.empty:
        print("\nADAY YOK - secilen periyotta canli teyit esiklerini gecen hisse yok.")
        return pd.DataFrame()

    # Kullaniciya sade trade tablosu göster.
    # Teknik sütunlar CSV'de korunur; ana ekranda sadece istenen başlıklar görünür.
    def signal_text(tags):
        names={
            "RVOL3":"RVOL3 HACIM",
            "RVOL":"HACIM",
            "VWAP":"VWAP USTU",
            "DI":"DI POZITIF",
            "MFI":"MFI",
            "ADX":"ADX",
            "TREND":"TREND",
            "MOM":"MOMENTUM",
            "CANLI_TETIK":"CANLI TETIK",
            "RANGE":"RANGE",
            "ATR":"ATR",
        }
        parts=[names.get(x,x) for x in str(tags).split("+") if x]
        # En anlamlı ilk 5 sinyali göster; ekran taşmasını azalt.
        priority=["CANLI TETIK","RVOL3 HACIM","HACIM","VWAP USTU","DI POZITIF",
                  "MOMENTUM","TREND","MFI","ADX","RANGE","ATR"]
        chosen=[x for x in priority if x in parts][:5]
        return " + ".join(chosen)

    def decision(score):
        if score >= 90:
            return "COK GUCLU"
        if score >= 80:
            return "GUCLU AL"
        if score >= 70:
            return "AL"
        return "TAKIP"

    # Stop: ATR bazlı yaklaşık 1 ATR aşağı; aşırı genişlemeyi sınırlıyoruz.
    stop_pct=np.clip(good["ATR_%"].fillna(1.5), 1.0, 4.0)

    # Hedef puana göre %5-%10 bandında; puan olasılık değildir.
    target_pct=np.clip(5.0 + (good["PUAN"]-62.0)*(5.0/38.0), 5.0, 10.0)

    view=pd.DataFrame({
        "HISSE":good["HISSE"],
        "SINYAL":good["TETIKLER"].map(signal_text),
        "PUAN":good["PUAN"].astype(int),
        "GIRIS":good["FIYAT"],
        "STOP":good["FIYAT"]*(1-stop_pct/100),
        "HEDEF":good["FIYAT"]*(1+target_pct/100),
        "KAZANC_%":target_pct,
        "KARAR":good["PUAN"].map(decision),
    })

    print_trade_table(view, f"V19.2 CANLI TRADE LISTESI | {label}")

    print("\nNOT: HEDEF ve STOP tarama modelinin teknik seviyeleridir; garanti fiyat/olasılık değildir.")
    print("Teknik indikator detaylari CSV dosyasinda korunur.")

    stamp=now.strftime("%Y%m%d_%H%M")
    export=good.copy()
    export["SINYAL"]=export["TETIKLER"].map(signal_text)
    export["GIRIS"]=export["FIYAT"]
    export["STOP"]=export["FIYAT"]*(1-stop_pct/100)
    export["HEDEF"]=export["FIYAT"]*(1+target_pct/100)
    export["KAZANC_%"]=target_pct
    export["KARAR"]=export["PUAN"].map(decision)
    export["TARAMA_ZAMANI"]=now.strftime("%Y-%m-%d %H:%M:%S")
    export["PERIYOT"]=label

    # İstenen sütunlar CSV'nin başında; teknik detaylar arkada.
    first=["HISSE","SINYAL","PUAN","GIRIS","STOP","HEDEF","KAZANC_%","KARAR"]
    rest=[c for c in export.columns if c not in first]
    export=export[first+rest]

    if dtime(9,40) <= now.time() <= dtime(18,10):
        out=f"V19_2_CANLI_{stamp}.csv"
        export.to_csv(result_file(out),index=False,encoding="utf-8-sig")
        print("\nKaydedildi:",result_file(out))
        print("Bu kayit seans kapanisinda CANLI FORWARD TEST ile olculebilir.")
    else:
        print("\nSEANS KAPALI - bu tarama forward test kaydi olarak kaydedilmedi.")
    return export


def reversal_score(x):
    """V20 Dönüş Avcısı: -%7/-10 düşüş bölgesinde teyitli dip dönüşü."""
    if x is None or len(x)<22:
        return None

    r=x.iloc[-1]
    prev=x.iloc[-2]
    today=x[x.index.date==x.index[-1].date()]
    if today.empty:
        return None

    day_open=float(today.iloc[0].Open)
    day_low=float(today.Low.min())
    last=float(r.Close)
    if day_open<=0 or day_low<=0:
        return None

    low_drop=100*(day_low/day_open-1)
    rebound=100*(last/day_low-1)

    # Otopsi: -%7 altı aday havuzu; -%8/-9.5 ana tatlı bölge.
    if low_drop>-7.0:
        return None

    pts=0
    tags=[]

    # Düşüş derinliği artık kör biçimde "daha sert = daha iyi" sayılmıyor.
    if -9.5 <= low_drop <= -8.0:
        pts+=18; tags.append("TATLI_BOLGE")
    elif -8.0 < low_drop <= -7.0:
        pts+=10; tags.append("ERKEN_BOLGE")
    elif -10.5 <= low_drop < -9.5:
        pts+=8; tags.append("DERIN_BOLGE")
    else:
        # -%10.5 ve daha sert: ekstra teyit gerekecek.
        pts-=8; tags.append("ASIRI_SATIS")

    # Tepki başladı mı? Ham otopside +%5 tepki tabanı ~%40-48.
    if rebound>=2.0: pts+=14; tags.append("DIPTEN_TEPKI")
    if rebound>=3.0: pts+=8; tags.append("TEPKI3")
    if rebound>=4.0: pts+=8; tags.append("GUCLU_TEPKI")

    price_turn = float(r.Close)>float(prev.Close)
    mom_turn = pd.notna(r.RET1) and float(r.RET1)>0
    if price_turn:
        pts+=10; tags.append("FIYAT_DONUS")
    if mom_turn:
        pts+=8; tags.append("MOMENTUM_DONUS")

    vol_confirm=False
    if pd.notna(r.RVOL3) and r.RVOL3>=1.10:
        pts+=13; tags.append("RVOL3"); vol_confirm=True
    if pd.notna(r.RVOL) and r.RVOL>=1.20:
        pts+=8; tags.append("HACIM"); vol_confirm=True

    vwap_confirm=False
    if pd.notna(r.VWAP_DIST) and r.VWAP_DIST>=0:
        pts+=18; tags.append("VWAP_GERI_ALDI"); vwap_confirm=True
    elif pd.notna(r.VWAP_DIST) and r.VWAP_DIST>=-1.0:
        pts+=6; tags.append("VWAP_YAKIN")

    di_confirm=False
    if pd.notna(r.DI) and r.DI>0:
        pts+=10; tags.append("DI_POZITIF"); di_confirm=True
    elif pd.notna(r.DI) and r.DI>-4:
        pts+=4; tags.append("DI_TOPARLIYOR")

    if pd.notna(r.RSI) and 30<=r.RSI<=60:
        pts+=6; tags.append("RSI_DONUS")
    if pd.notna(r.MFI) and 25<=r.MFI<=65:
        pts+=5; tags.append("MFI_DONUS")

    # -%10.5 altındaki çöküşlerde tek bir küçük tepki yeterli değil.
    if low_drop < -10.5:
        strong_confirms = sum([rebound>=3.0, price_turn, mom_turn, vol_confirm, vwap_confirm, di_confirm])
        if strong_confirms < 3:
            return None

    return {
        "PUAN":max(0,min(100,pts)),
        "DUSUS_%":low_drop,
        "TEPKI_%":rebound,
        "FIYAT":last,
        "ATR_%":float(r.ATR_PCT) if pd.notna(r.ATR_PCT) else 2.0,
        "TETIKLER":"+".join(tags),
        "RVOL3":float(r.RVOL3) if pd.notna(r.RVOL3) else np.nan,
        "VWAP_%":float(r.VWAP_DIST) if pd.notna(r.VWAP_DIST) else np.nan,
        "DI_SPREAD":float(r.DI) if pd.notna(r.DI) else np.nan,
    }

def reversal_main(symbols=None):
    # Dönüş Avcısı sabit 15 dakika: kullanıcı menüde ayrıca periyot seçmek zorunda kalmaz.
    tf="15m"
    label=TF_CFG[tf][0]
    now=datetime.now(IST)

    print("\n"+"="*118)
    print(f"V20 DONUS AVCISI | {label} | -%7/-10 DIP DONUS MODELI")
    print("Ana bolge: -%8 ile -%9.5 | -%10.5 alti icin ekstra teyit zorunlu")
    print("Tarama zamani:",now.strftime("%Y-%m-%d %H:%M"))
    print("="*118)

    rows=[]; data_errors=[]
    syms=get_bist_symbols() if symbols is None else list(dict.fromkeys(symbols))
    for i,s in enumerate(syms,1):
        print(f"\r[{i}/{len(syms)}] {s:<14}",end="",flush=True)
        try:
            x=features(download_tf(s,tf))
            if x is None or x.empty:
                raise ValueError("15dk veri bos; saglayici/baglanti siniri olabilir")
            rec=reversal_score(x)
            if rec is None:
                continue
            rec["HISSE"]=s.replace(".IS","")
            rec["HISSE_BAR_ZAMANI"]=str(x.index[-1])
            rows.append(rec)
        except Exception as exc:
            data_errors.append({"HISSE":s,"HATA":str(exc)})
        time.sleep(.004)
    print()
    pd.DataFrame(data_errors,columns=["HISSE","HATA"]).to_csv(result_file(f"DONUS_VERI_HATALARI_{now:%Y%m%d_%H%M%S}.csv"),index=False,encoding="utf-8-sig")
    if data_errors: print(f"VERI HATASI: {len(data_errors)}/{len(syms)} hisse. Hatalar ayri CSV kaydedildi.")

    if not rows:
        print("\nADAY YOK - -%7 veya daha sert dusup teyitli donus baslatan hisse yok.")
        return pd.DataFrame()

    df=pd.DataFrame(rows)

    # V20: sadece "düştü" diye seçme; en az +%2 tepki ve 62 puan.
    good=df[(df.PUAN>=62)&(df["TEPKI_%"]>=2.0)].copy()
    good=good.sort_values(["PUAN","TEPKI_%","RVOL3"],ascending=False).head(20)

    if good.empty:
        print("\nADAY YOK - sert dusus var fakat V20 donus teyidi yeterli degil.")
        return pd.DataFrame()

    def karar(s):
        if s>=88:return "COK GUCLU DONUS"
        if s>=76:return "GUCLU DONUS"
        if s>=66:return "DONUS ADAYI"
        return "TAKIP"

    def sig(t):
        priority=["TATLI_BOLGE","VWAP_GERI_ALDI","GUCLU_TEPKI","TEPKI3",
                  "DIPTEN_TEPKI","RVOL3","HACIM","FIYAT_DONUS",
                  "MOMENTUM_DONUS","DI_POZITIF","RSI_DONUS","MFI_DONUS"]
        parts=str(t).split("+")
        return " + ".join([x for x in priority if x in parts][:5])

    stop_pct=np.clip(good["ATR_%"].fillna(2.0)*0.75,0.8,3.5)
    target_pct=np.clip(5.0+(good.PUAN-62)*(3.0/38),5.0,8.0)

    view=pd.DataFrame({
        "HISSE":good.HISSE,
        "SINYAL":good.TETIKLER.map(sig),
        "PUAN":good.PUAN.astype(int),
        "DUSUS_%":good["DUSUS_%"],
        "TEPKI_%":good["TEPKI_%"],
        "GIRIS":good.FIYAT,
        "STOP":good.FIYAT*(1-stop_pct/100),
        "HEDEF":good.FIYAT*(1+target_pct/100),
        "KAZANC_%":target_pct,
        "KARAR":good.PUAN.map(karar),
    })

    print_trade_table(view, f"V20 DONUS AVCISI TRADE LISTESI | {label}")

    stamp=now.strftime("%Y%m%d_%H%M")
    export=good.copy()
    export["SINYAL"]=export.TETIKLER.map(sig)
    export["GIRIS"]=export.FIYAT
    export["STOP"]=export.FIYAT*(1-stop_pct/100)
    export["HEDEF"]=export.FIYAT*(1+target_pct/100)
    export["KAZANC_%"]=target_pct
    export["KARAR"]=export.PUAN.map(karar)
    export["TARAMA_ZAMANI"]=now.strftime("%Y-%m-%d %H:%M:%S")
    export["PERIYOT"]=label
    first=["HISSE","SINYAL","PUAN","DUSUS_%","TEPKI_%","GIRIS","STOP","HEDEF","KAZANC_%","KARAR"]
    export=export[first+[c for c in export.columns if c not in first]]
    out=f"V20_DONUS_AVCISI_15M_{stamp}.csv"
    export.to_csv(result_file(out),index=False,encoding="utf-8-sig")
    print("\nKaydedildi:",result_file(out))
    return export

def tavan_main(tf=None):
    """V19.2 CANLI TAVAN AVCISI V4 - hacim/fiyat ivmesi ana puan, RSI/MFI destek."""
    tf=tf or choose_timeframe()
    label=TF_CFG[tf][0]
    now=datetime.now(IST)

    print("\n"+"="*118)
    print(f"V19.2 CANLI TAVAN AVCISI TOP10 | {label}")
    print(f"Tarama zamani: {now:%Y-%m-%d %H:%M}")
    print("="*118)

    rows=[]
    syms=get_bist_symbols()

    for i,symbol in enumerate(syms,1):
        print(f"\r[{i}/{len(syms)}] {symbol:<14}",end="",flush=True)
        try:
            x=features(download_tf(symbol,tf))
            if x.empty or len(x)<30: continue
            r=x.iloc[-1]

            def val(name,default=0.0):
                z=r.get(name,default)
                return default if pd.isna(z) else float(z)

            rv3=val("RVOL3"); rvol=val("RVOL")
            vwap=val("VWAP_DIST"); di=val("DI")
            mfi=val("MFI",50); rsi=val("RSI",50)
            trend=val("TREND"); mom=val("RET1"); rng=val("RANGE_PCT")
            entry=val("Close")
            if entry<=0: continue

            # ANA PUAN: maksimum 88
            puan=0; tags=[]

            # Hacim 30
            if rv3>=2.0: puan+=18; tags.append("RV3++")
            elif rv3>=1.5: puan+=14; tags.append("RV3+")
            elif rv3>=1.2: puan+=9; tags.append("RV3")
            if rvol>=1.8: puan+=12; tags.append("VOL++")
            elif rvol>=1.3: puan+=8; tags.append("VOL+")
            elif rvol>=1.05: puan+=4; tags.append("VOL")

            # VWAP 18
            if vwap>=2.0: puan+=18; tags.append("VW++")
            elif vwap>=1.0: puan+=14; tags.append("VW+")
            elif vwap>0: puan+=8; tags.append("VW")

            # Yon gucu 16
            if di>=30: puan+=16; tags.append("DI++")
            elif di>=18: puan+=12; tags.append("DI+")
            elif di>=8: puan+=7; tags.append("DI")

            # Anlik momentum 14
            if mom>=2.0: puan+=14; tags.append("MOM++")
            elif mom>=1.0: puan+=10; tags.append("MOM+")
            elif mom>0: puan+=5; tags.append("MOM")

            # Trend 10
            if trend>=2.0: puan+=10; tags.append("TR++")
            elif trend>=1.0: puan+=7; tags.append("TR+")
            elif trend>0: puan+=4; tags.append("TR")

            # DESTEK: RSI/MFI toplam maksimum 8; tek basina aday yaratamaz.
            destek=0
            if 60<=mfi<=88: destek+=4; tags.append("MFI")
            elif 52<=mfi<60: destek+=2
            if 58<=rsi<=80: destek+=4; tags.append("RSI")
            elif 52<=rsi<58: destek+=2
            puan+=destek

            # Range yalnız tie-break/destek.
            if rng>=1.2:
                puan+=4; tags.append("RNG")

            # Gercek tavan profili icin hacim + VWAP + yon + ivme zorunlu.
            hacim_ok=(rv3>=1.2 and rvol>=1.05)
            fiyat_ok=(vwap>0 and di>=8)
            ivme_ok=(mom>0 and trend>0)
            core=hacim_ok and fiyat_ok and ivme_ok

            # Her zaman TOP10 verebilmek icin zayiflar da siralanir,
            # fakat TAVAN ADAYI etiketi core olmadan verilmez.
            if core and puan>=86:
                karar="TAVAN COK GUCLU"
            elif core and puan>=72:
                karar="TAVAN ADAYI"
            elif puan>=58:
                karar="IZLE"
            else:
                karar="TAKIP"

            target_pct=min(10.0,max(5.0,5.0+max(0,puan-50)*0.10))
            stop_pct=1.0 if core and puan>=80 else 1.35

            rows.append({
                "HISSE":symbol.replace(".IS",""),
                "SINYAL":"+ ".join([]) if False else "+".join(tags),
                "PUAN":min(100,int(round(puan))),
                "GIRIS":entry,
                "STOP":entry*(1-stop_pct/100),
                "HEDEF":entry*(1+target_pct/100),
                "KAZANC_%":target_pct,
                "KARAR":karar,
                "CORE":core,
                "RVOL3":rv3,"RVOL":rvol,"VWAP_%":vwap,"DI_SPREAD":di,
                "MFI14":mfi,"RSI14":rsi,"RET1":mom,"TREND_%":trend,"RANGE_%":rng
            })
        except Exception:
            pass
        time.sleep(.004)

    print()
    if not rows:
        print("Veri alinabilen aday bulunamadi.")
        return pd.DataFrame()

    all_df=pd.DataFrame(rows).sort_values(
        ["CORE","PUAN","RVOL3","RVOL","RET1"],ascending=False
    ).reset_index(drop=True)
    view=all_df.head(10).copy()

    print_trade_table(
        view[["HISSE","SINYAL","PUAN","GIRIS","STOP","HEDEF","KAZANC_%","KARAR"]],
        f"V19.2 CANLI TAVAN AVCISI TOP10 | {label}"
    )

    stamp=now.strftime("%Y%m%d_%H%M")
    fn=f"V19_2_TAVAN_CANLI_{stamp}.csv"
    view.assign(
        TARAMA_ZAMANI=now.strftime("%Y-%m-%d %H:%M"),
        PERIYOT=label
    ).to_csv(result_file(fn),index=False,encoding="utf-8-sig")
    print("\nKaydedildi:",result_file(fn))
    print("TAVAN etiketi icin RVOL3+RVOL+VWAP+DI+MOM+TREND birlikte zorunludur.")
    return view


def main():
    print("\nV19.2 CANLI MOD")
    print("[1] NORMAL %5-%10 MOMENTUM")
    print("[2] DONUS AVCISI (-%7/-10 VE DAHA SERT DUSUSTEN DONUS)")
    while True:
        c=input("Canli mod seciminiz: ").strip()
        if c=="1":
            return momentum_main()
        if c=="2":
            return reversal_main()
        print("Gecersiz secim.")

if __name__=="__main__":
    main()
