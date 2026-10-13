from datetime import datetime
from zoneinfo import ZoneInfo
import time
import numpy as np
import pandas as pd

import v19_2_canli as live
from symbols import get_bist_symbols
from v19_paths import result_file

IST=ZoneInfo("Europe/Istanbul")

def _v(v, default=0.0):
    try:
        if pd.isna(v):
            return default
        return float(v)
    except:
        return default

def _score(x):
    if x is None or x.empty or len(x)<30:
        return None

    r=x.iloc[-1]
    p=x.iloc[-2]

    close=_v(r.get("Close"))
    if close<=0:
        return None

    rv3=_v(r.get("RVOL3"))
    rvol=_v(r.get("RVOL"))
    vwap=_v(r.get("VWAP_DIST"))
    di=_v(r.get("DI"))
    di_prev=_v(p.get("DI"))
    rsi=_v(r.get("RSI"),50)
    rsi_prev=_v(p.get("RSI"),50)
    trend=_v(r.get("TREND"))
    mom=_v(r.get("RET1"))
    rng=_v(r.get("RANGE_PCT"))

    # Hacim ivmesi: son mum hacmi / onceki mum hacmi
    vol_now=_v(r.get("Volume"))
    vol_prev=_v(p.get("Volume"))
    vol_acc=(vol_now/vol_prev) if vol_prev>0 else 0.0

    # Son 20 bar tepe kirilimina mesafe
    prev20=x.iloc[-21:-1] if len(x)>=21 else x.iloc[:-1]
    high20=_v(prev20["High"].max()) if not prev20.empty else close
    breakout_dist=((close/high20)-1)*100 if high20>0 else 0.0
    breakout=close>high20

    # VWAP egimi: son iki VWAP_DIST artiyor mu?
    vwap_prev=_v(p.get("VWAP_DIST"))
    vwap_rising=vwap>vwap_prev

    # DI farki buyuyor mu?
    di_acc=di-di_prev

    # RSI yukari mi?
    rsi_rising=rsi>rsi_prev

    score=0
    tags=[]

    # Hacim / para girisi 30
    if vol_acc>=1.5:
        score+=15; tags.append("VOLACC")
    elif vol_acc>=1.2:
        score+=8; tags.append("VOLACC")

    if rvol>=1.8:
        score+=15; tags.append("RVOL")
    elif rvol>=1.35:
        score+=9; tags.append("RVOL")

    # VWAP 15
    if vwap>0:
        score+=10; tags.append("VW")
    if vwap_rising:
        score+=5; tags.append("VWUP")

    # DI / momentum 15
    if di>0 and di_acc>0:
        score+=10; tags.append("DIACC")
    elif di>0:
        score+=5; tags.append("DI")

    if mom>0:
        score+=5; tags.append("MOM")

    # Breakout 15
    if breakout:
        score+=15; tags.append("BRK20")
    elif breakout_dist>=-2.0:
        score+=8; tags.append("NEAR20")

    # RSI 5
    if 45<=rsi<=70 and rsi_rising:
        score+=5; tags.append("RSI")

    # Trend 10
    if trend>0:
        score+=7; tags.append("TR")
    if rng>=1.0:
        score+=3; tags.append("RNG")

    # SERIES tipi: onceki 2-3 mumda cok guclu momentum varsa ayri bonus
    ret2=_v(r.get("RET2"))
    ret3=_v(r.get("RET3"))
    series_bonus=0
    if ret2>=4 and ret3>=6 and rvol>=1.2:
        series_bonus=8
        tags.append("SERIES")

    total=min(100, score+series_bonus)

    # Ana tavan teyidi: hacim + VWAP + yon/momentum
    core=(rvol>=1.2 and vwap>0 and (di>0 or mom>0))

    if total>=80 and core:
        karar="TAVAN RADARI"
    elif total>=70 and core:
        karar="GUCLU TAVAN"
    elif total>=60:
        karar="TAVAN ON ADAY"
    elif total>=50:
        karar="IZLE"
    else:
        karar="TAKIP"

    target_pct=min(10.0,max(5.0,5.0+(total-50)*0.10))
    stop_pct=1.0 if total>=80 and core else 1.35

    return {
        "PUAN":int(round(total)),
        "SINYAL":"+".join(tags),
        "GIRIS":close,
        "STOP":close*(1-stop_pct/100),
        "HEDEF":close*(1+target_pct/100),
        "KAZANC_%":target_pct,
        "KARAR":karar,
        "RVOL":rvol,
        "RVOL3":rv3,
        "VOL_ACCEL":vol_acc,
        "VWAP_%":vwap,
        "DI":di,
        "DI_ACCEL":di_acc,
        "RSI":rsi,
        "TREND_%":trend,
        "RET1":mom,
        "BREAKOUT_DIST_%":breakout_dist,
        "CORE":core,
    }

def main(tf=None):
    tf=tf or live.choose_timeframe()
    label=live.TF_CFG[tf][0]
    now=datetime.now(IST)

    print("\n"+"="*118)
    print(f"V19.3 TAVAN RADAR - TEST | {label}")
    print(f"Tarama zamani: {now:%Y-%m-%d %H:%M}")
    print("="*118)

    rows=[]
    syms=get_bist_symbols()

    for i,s in enumerate(syms,1):
        print(f"\r[{i}/{len(syms)}] {s:<14}",end="",flush=True)
        try:
            x=live.features(live.download_tf(s,tf))
            rec=_score(x)
            if rec is None:
                continue
            rec["HISSE"]=s.replace(".IS","")
            rows.append(rec)
        except:
            pass
        time.sleep(.004)

    print()
    if not rows:
        print("Aday bulunamadi.")
        return pd.DataFrame()

    df=pd.DataFrame(rows)
    df=df.sort_values(
        ["PUAN","CORE","VOL_ACCEL","RVOL","DI_ACCEL"],
        ascending=[False,False,False,False,False]
    ).reset_index(drop=True)

    # Akşam/erken radar mantigi icin TOP20, fakat ekranda en iyi 10.
    top20=df.head(20).copy()
    view=top20.head(10)[["HISSE","SINYAL","PUAN","GIRIS","STOP","HEDEF","KAZANC_%","KARAR"]].copy()

    live.print_trade_table(view,f"V19.3 TAVAN RADAR TOP10 | {label}")

    stamp=now.strftime("%Y%m%d_%H%M")
    fn=f"V19_3_TAVAN_RADAR_{stamp}.csv"
    top20.assign(
        TARAMA_ZAMANI=now.strftime("%Y-%m-%d %H:%M"),
        PERIYOT=label
    ).to_csv(result_file(fn),index=False,encoding="utf-8-sig")

    print("\nKaydedildi:",result_file(fn))
    print("Not: CSV'de ilk 20 on-aday saklanir; ekranda en guclu 10 gosterilir.")
    return top20

if __name__=="__main__":
    main()
