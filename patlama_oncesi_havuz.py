from __future__ import annotations
from datetime import datetime
import math
import numpy as np
import pandas as pd
import yfinance as yf
from symbols import get_bist_symbols
from v19_paths import result_file

LOOKBACK="8mo"; MIN_BARS=85; TOP_N=40

def _safe(v, default=0.0):
    try:
        x=float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default

def _download(symbol):
    df=yf.download(symbol,period=LOOKBACK,interval="1d",auto_adjust=False,progress=False,threads=False)
    if df is None or df.empty: return None
    if isinstance(df.columns,pd.MultiIndex): df.columns=[c[0] for c in df.columns]
    need=["Open","High","Low","Close","Volume"]
    if any(c not in df.columns for c in need): return None
    from data_quality import completed_daily
    return completed_daily(df[need].dropna().copy())

def score_symbol(symbol):
    df=_download(symbol)
    if df is None or len(df)<MIN_BARS: return None
    c=df["Close"].astype(float); h=df["High"].astype(float); l=df["Low"].astype(float); v=df["Volume"].astype(float)
    last=_safe(c.iloc[-1]); prev=_safe(c.iloc[-2])
    if last<=0 or prev<=0: return None
    day_pct=(last/prev-1)*100
    # Amaç patlamadan önce yakalamak; zaten sert patlamış olanı alma.
    if day_pct>=7.0: return None

    r80_hi,r80_lo=_safe(h.tail(80).max()),_safe(l.tail(80).min())
    r20_hi,r20_lo=_safe(h.tail(20).max()),_safe(l.tail(20).min())
    range80=(r80_hi/r80_lo-1)*100 if r80_lo else 999
    range20=(r20_hi/r20_lo-1)*100 if r20_lo else 999
    compression=range20/range80 if range80>0 else 1.0

    ret20=(last/_safe(c.iloc[-21],last)-1)*100
    ret5=(last/_safe(c.iloc[-6],last)-1)*100
    ret3=(last/_safe(c.iloc[-4],last)-1)*100
    falling_stopped=(ret20<3.0 and ret5>-4.0 and ret3>-2.0)

    vol20=_safe(v.iloc[-21:-1].mean(),1)
    vol_ratio=_safe(v.iloc[-1])/vol20 if vol20>0 else 0

    o=_safe(df["Open"].iloc[-1],last); lo=_safe(l.iloc[-1],last); hi=_safe(h.iloc[-1],last)
    intraday_pos=(last-lo)/(hi-lo) if hi>lo else .5
    green=last>=o

    prior10_hi=_safe(h.iloc[-11:-1].max(),last)
    dist10=(prior10_hi/last-1)*100 if last else 999

    tr=(h-l)/c.replace(0,np.nan)*100
    tr5=_safe(tr.tail(5).mean(),99); tr20=_safe(tr.iloc[-25:-5].mean(),tr5)
    vol_contract=tr5/tr20 if tr20>0 else 1.0

    score=0; reasons=[]
    if range80>=18: score+=8; reasons.append("uzun_baz")
    if compression<=.55: score+=18; reasons.append("20g_daralma")
    elif compression<=.72: score+=10; reasons.append("daralma")
    if falling_stopped: score+=18; reasons.append("dusus_durdu")
    if ret3>0: score+=8; reasons.append("kisa_donus")
    if vol_contract<=.75: score+=12; reasons.append("volatilite_sikisma")
    elif vol_contract<=.90: score+=6; reasons.append("volatilite_azaldi")
    if vol_ratio>=2: score+=22; reasons.append("hacim_uyandi_2x")
    elif vol_ratio>=1.5: score+=16; reasons.append("hacim_uyandi")
    elif vol_ratio>=1.15: score+=8; reasons.append("hacim_artiyor")
    if green and intraday_pos>=.65: score+=8; reasons.append("guclu_kapanis")
    if dist10<=3: score+=12; reasons.append("dirence_yakin")
    elif dist10<=6: score+=6; reasons.append("dirence_yaklasiyor")
    if day_pct>5: score-=10

    if score>=72 and vol_ratio>=1.35 and falling_stopped: stage="ATESLEME"
    elif score>=58: stage="HAZIRLANIYOR"
    elif score>=45: stage="ERKEN"
    else: return None

    # HEDEF MOTORU V1: sadece bugune kadar gorulen veriyi kullanir.
    # H1 = en yakin anlamli eski direnç; H2 = baz/konsolidasyon olculu hareket;
    # H3 = momentum uzatma hedefi. Tek fiyat yerine hedef bolgesi verir.
    atr14=_safe((pd.concat([(h-l),(h-c.shift(1)).abs(),(l-c.shift(1)).abs()],axis=1).max(axis=1)).tail(14).mean(),0)
    atr_pct=(atr14/last*100) if last else 0
    prior20_hi=_safe(h.iloc[-21:-1].max(),last)
    prior40_hi=_safe(h.iloc[-41:-1].max(),prior20_hi)
    prior80_hi=_safe(h.iloc[-81:-1].max(),prior40_hi)
    resistances=sorted({x for x in (prior10_hi,prior20_hi,prior40_hi,prior80_hi) if x>last*1.005})
    h1=resistances[0] if resistances else last*(1+max(0.05,min(0.10,atr_pct*2/100)))

    # Son 20 gunluk baz yuksekligi: kirilim sonrasi klasik measured-move.
    base_hi=_safe(h.iloc[-21:-1].max(),last)
    base_lo=_safe(l.iloc[-21:-1].min(),last)
    base_height=max(0.0,base_hi-base_lo)
    measured=base_hi+base_height
    # H2 en az H1'in ustunde; asiri genis bazlarda hedefi kontrol et.
    h2=max(h1*1.025, measured)
    h2=max(h1*1.025,min(h2,last*1.35))
    # H3: H2 ustune ATR + baz genisliginin bir kismi; guclu hacimde biraz daha pay.
    ext=max(atr14*2.0,base_height*0.45,last*0.05)
    if vol_ratio>=2.0: ext*=1.15
    h3=max(h2*1.05,min(max(h2+ext,h2*1.05),last*1.55))
    # Hedef bolgesi toleransi: ATR'nin %35'i, min %0.8 max %2.5.
    zone_pct=max(0.8,min(2.5,atr_pct*0.35))
    def _zone(x):
        d=x*zone_pct/100
        return f"{x-d:.2f}-{x+d:.2f}"
    # Yapinin bozulma seviyesi: son 5 gun dip / 1.5 ATR'nin daha koruyucu olani.
    low5=_safe(l.tail(5).min(),last)
    invalid=max(low5,last-1.5*atr14) if atr14>0 else low5

    return {"HISSE":symbol.replace(".IS",""),"EVRE":stage,"PATLAMA_PUANI":int(round(score)),
            "VERI_TARIHI":str(df.index[-1].date()),"KAPANIS":round(last,4),"H1":round(h1,4),"H1_BOLGE":_zone(h1),
            "H2":round(h2,4),"H2_BOLGE":_zone(h2),"H3":round(h3,4),"H3_BOLGE":_zone(h3),
            "YAPI_BOZULMA":round(invalid,4),"ATR14_%":round(atr_pct,2),
            "GUN_%":round(day_pct,2),"20G_%":round(ret20,2),
            "5G_%":round(ret5,2),"HACIM_ORAN":round(vol_ratio,2),"20G_DARALMA_%":round(range20,2),
            "DARALMA_ORAN":round(compression,2),"VOL_SIKISMA":round(vol_contract,2),
            "10G_DIRENC_MESAFE_%":round(dist10,2),"NEDEN":"+".join(reasons)}

def main():
    print("\n"+"="*100)
    print("PATLAMA ONCESI HAVUZ | Uzun dinlenme -> dusus durur -> daralma -> hacim uyanisi")
    print("MIATK tipi yapıyı ilk buyuk hareketten ONCE arar. AL/SAT emri degildir.")
    print("="*100)
    rows=[]; symbols=get_bist_symbols()
    for i,symbol in enumerate(symbols,1):
        try:
            r=score_symbol(symbol)
            if r: rows.append(r)
        except Exception: pass
        if i%50==0: print(f"[{i}/{len(symbols)}] tarandi | havuz: {len(rows)}")
    if not rows:
        print("Bugun kriterlere uyan aday bulunamadi."); return []
    out=pd.DataFrame(rows)
    rank={"ATESLEME":3,"HAZIRLANIYOR":2,"ERKEN":1}
    out["_rank"]=out["EVRE"].map(rank).fillna(0)
    out=out.sort_values(["_rank","PATLAMA_PUANI","HACIM_ORAN"],ascending=[False,False,False]).drop(columns="_rank").head(TOP_N)
    # Ekranda sadece karar icin gerekli alanlari goster; tum teknik kolonlar CSV'de kalir.
    def _kisa_not(row):
        neden=str(row.get("NEDEN", ""))
        notlar=[]
        if "hacim_uyandi_2x" in neden: notlar.append("Hacim 2x+ uyandi")
        elif "hacim_uyandi" in neden: notlar.append("Hacim uyandi")
        elif "hacim_artiyor" in neden: notlar.append("Hacim artiyor")
        if "20g_daralma" in neden or "volatilite_sikisma" in neden: notlar.append("Sikisma")
        if "dusus_durdu" in neden: notlar.append("Dusus durdu")
        if "dirence_yakin" in neden: notlar.append("Dirence yakin")
        elif "dirence_yaklasiyor" in neden: notlar.append("Dirence yaklasiyor")
        if "guclu_kapanis" in neden: notlar.append("Guclu kapanis")
        return ", ".join(notlar[:3]) or "Hazirlik yapisi"

    print("\nPATLAMA ONCESI HAVUZ | SADE LISTE")
    print("-"*86)
    print(f"{'#':>2}  {'HISSE':<7} {'FIYAT':>9} {'PUAN':>5} {'EVRE':<12} {'H1':>9} {'H2':>9} {'H3':>9}  KISA NOT")
    print("-"*104)
    for no, (_, r) in enumerate(out.iterrows(), 1):
        print(f"{no:>2}  {str(r['HISSE']):<7} {float(r['KAPANIS']):>9.2f} {int(r['PATLAMA_PUANI']):>5} {str(r['EVRE']):<12} {float(r['H1']):>9.2f} {float(r['H2']):>9.2f} {float(r['H3']):>9.2f}  {_kisa_not(r)}")
    print("-"*104)
    print("H1=ilk direnç | H2=ana olculu hedef | H3=momentum uzatma. Hedefler garanti degildir.")
    print("Detay kolonlari ekranda gizlendi; CSV dosyasinda eksiksiz kaydedilir.")
    stamp=datetime.now().strftime("%Y%m%d_%H%M")
    path=result_file(f"PATLAMA_ONCESI_HAVUZ_{stamp}.csv")
    out.to_csv(path,index=False,encoding="utf-8-sig")
    print(f"\nKaydedildi: {path}")
    return out.to_dict("records")

if __name__=="__main__": main()
