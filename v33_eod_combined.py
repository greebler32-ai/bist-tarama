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
VERSION='V33-FIX4-ERKEN-PATLAMA-TAVAN-DEVAM'
SESSION_END_HOUR=18
SESSION_END_MINUTE=10

def _flat(d):
    if d is None or d.empty: return pd.DataFrame()
    x=d.copy()
    if isinstance(x.columns,pd.MultiIndex): x.columns=[c[0] for c in x.columns]
    x.columns=[str(c).title() for c in x.columns]
    idx=pd.DatetimeIndex(x.index)
    if idx.tz is not None: idx=idx.tz_convert('Europe/Istanbul').tz_localize(None)
    x.index=idx
    return x

def _completed_daily(d, now=None):
    from data_quality import completed_daily
    return completed_daily(_flat(d), now)


def _ema(s,n): return s.ewm(span=n,adjust=False).mean()

def _features(d, completed=False):
    x=_flat(d) if completed else _completed_daily(d)
    if len(x)<150: return x
    o,h,l,c,v=x.Open,x.High,x.Low,x.Close,x.Volume
    x['RET1']=c.pct_change()*100
    for n in (2,3,5,10,20): x[f'RET{n}']=(c/c.shift(n)-1)*100
    x['RANGE']=100*(h-l)/c.shift(1).replace(0,np.nan)
    x['BODY']=100*(c-o)/o.replace(0,np.nan)
    x['CLV']=(c-l)/(h-l).replace(0,np.nan)
    x['LOWER_WICK']=(np.minimum(o,c)-l)/(h-l).replace(0,np.nan)
    for n in (9,21,50): x[f'EMA{n}']=_ema(c,n)
    x['EMA9_SLOPE']=100*(x.EMA9/x.EMA9.shift(3)-1)
    x['EMA21_SLOPE']=100*(x.EMA21/x.EMA21.shift(5)-1)
    x['VMA20']=v.rolling(20).mean(); x['RVOL']=v/x.VMA20.replace(0,np.nan)
    x['VOL5_20']=v.rolling(5).mean()/x.VMA20.replace(0,np.nan)
    x['H20']=h.shift(1).rolling(20).max(); x['L20']=l.shift(1).rolling(20).min()
    x['H40']=h.shift(1).rolling(40).max(); x['L40']=l.shift(1).rolling(40).min()
    x['R20']=100*(x.H20/x.L20-1); x['R40']=100*(x.H40/x.L40-1)
    x['DIST_R20']=100*(c/x.H20-1)
    x['RANGE5']=x.RANGE.rolling(5).mean(); x['RANGE20']=x.RANGE.rolling(20).mean()
    x['CONTRACT']=x.RANGE5/x.RANGE20.replace(0,np.nan)
    return x

def _score(x):
    if x is None or x.empty or len(x)<150: return None
    r=x.iloc[-1]
    need=['Close','RET1','RET3','RET5','RET10','RANGE','BODY','CLV','LOWER_WICK','EMA9','EMA21','EMA50','EMA9_SLOPE','EMA21_SLOPE','RVOL','VOL5_20','R20','R40','DIST_R20','CONTRACT']
    if any(pd.isna(r.get(k)) for k in need): return None

    A=B=C=D=E=0.0; tags=[]
    # A: DUSUS -> TEPKI. Tek mum degil, onceki cok-gunluk dusus + satisin kesilmesi.
    if r.RET5 <= -4: A += 18
    if r.RET10 <= -6: A += 10
    if r.RET1 > -1.5: A += 8
    if r.CLV >= .65: A += 12
    if r.LOWER_WICK >= .25: A += 8
    if r.EMA9_SLOPE > 0: A += 12
    if r.RVOL >= 1.15: A += 10
    if A >= 45: tags.append('DUSUS_TEPKI')

    # B: KIRILIM -> ONAY. Dirence yakin/ilk kirilim, guclu kapanis, hacim ve trend teyidi.
    if -3.0 <= r.DIST_R20 <= 4.5: B += 22
    if r.CLV >= .70: B += 12
    if r.RVOL >= 1.20: B += 14
    if r.VOL5_20 >= 1.05: B += 8
    if r.EMA9 > r.EMA21: B += 10
    if r.EMA9_SLOPE > 0 and r.EMA21_SLOPE >= -.25: B += 10
    if 0 <= r.RET1 <= 6.5: B += 8
    if B >= 50: tags.append('KIRILIM_ONAY')

    # C: DARALMA sadece teyitli ise katkida bulunur; tek basina aday secmez.
    compressed = (r.CONTRACT <= .78) or (r.R20 <= 14) or (r.R40 <= 22)
    confirmed = (r.RVOL >= 1.15 and r.CLV >= .62 and r.EMA9_SLOPE > 0)
    if compressed and confirmed:
        C=24
        if -4 <= r.DIST_R20 <= 4.5: C += 10
        if r.VOL5_20 >= 1.05: C += 8
        tags.append('DARALMA_TEYIT')

    # D: PATLAMA_ERKEN. A/B henuz guclenmeden once, sikisma + satisin durmasi + hacim uyanisi.
    early_compressed = (r.CONTRACT <= .86) or (r.R20 <= 16) or (r.R40 <= 25)
    fall_stopped = (r.RET5 <= 3.0 and r.RET3 >= -2.5 and r.RET1 > -2.2)
    volume_wake = (r.RVOL >= 1.25) or (r.RVOL >= 1.05 and r.VOL5_20 >= 1.08)
    close_ok = r.CLV >= .62
    near_res = -6.0 <= r.DIST_R20 <= 5.0
    turn_ok = (r.EMA9_SLOPE > 0) or (r.Close >= r.EMA9)

    if early_compressed: D += 16
    if fall_stopped: D += 14
    if volume_wake: D += 16
    if close_ok: D += 10
    if near_res: D += 10
    if turn_ok: D += 8
    if r.RVOL >= 1.75: D += 6
    if D >= 52: tags.append('PATLAMA_ERKEN')

    # E: TAVAN_DEVAM. Ilk sert gunu otomatik 'gec' sayma; devam yapisini ayri puanla.
    first_burst = r.RET1 >= 8.0
    locked_close = r.CLV >= .84
    continuation_vol = r.RVOL >= 1.35
    breakout_hold = r.DIST_R20 >= -1.0
    trend_hold = (r.EMA9 > r.EMA21 and r.EMA9_SLOPE > 0)

    if first_burst: E += 18
    if locked_close: E += 16
    if continuation_vol: E += 14
    if breakout_hold: E += 12
    if trend_hold: E += 10
    if r.VOL5_20 >= 1.10: E += 6
    if E >= 56: tags.append('TAVAN_DEVAM')

    # Birlesik siralama: eski V33 omurgasi korunur; D/E sadece eksik kalan iki paterni tamamlar.
    score = .42*A + .58*B + .32*C + .34*D + .38*E
    if A>=45 and B>=50: score += 16; tags.append('A+B')
    if B>=58 and r.RVOL>=1.5: score += 10; tags.append('9PLUS_BONUS')

    # Eski gec kalma cezasi sadece devam yapisi YOKSA uygulanir.
    if r.RET1 > 8.0 and E < 56:
        score -= 18; tags.append('GEC_CEZA')
    elif r.RET1 > 8.0 and E >= 56:
        tags.append('GEC_CEZA_IPTAL')

    if r.RVOL > 6.0: score -= 8
    score=max(0,min(100,score))

    # Eski A/B kapisi korunur; bunun yanina iki kontrollu alternatif eklenir.
    base_pass = (A >= 38 or B >= 42)
    early_pass = D >= 52
    continuation_pass = E >= 56
    if not (base_pass or early_pass or continuation_pass): return None

    if continuation_pass:
        aday_tipi='TAVAN_DEVAM'
    elif early_pass and not base_pass:
        aday_tipi='PATLAMA_ERKEN'
    elif early_pass:
        aday_tipi='V33+PATLAMA_ERKEN'
    else:
        aday_tipi='V33_KLASIK'

    return {'V33_SKOR':round(score,2),'MOTOR_A':round(A,1),'MOTOR_B':round(B,1),'MOTOR_C':round(C,1),
            'MOTOR_D_ERKEN':round(D,1),'MOTOR_E_DEVAM':round(E,1),'ADAY_TIPI':aday_tipi,
            'SINYAL':'+'.join(tags) or 'TAKIP','GIRIS':float(r.Close),'RET1_%':float(r.RET1),
            'RET5_%':float(r.RET5),'RET10_%':float(r.RET10),'RVOL':float(r.RVOL),
            'DIST_R20_%':float(r.DIST_R20),'CLV':float(r.CLV),'CONTRACT':float(r.CONTRACT),
            'VERI_TARIHI':pd.Timestamp(r.name).strftime('%Y-%m-%d')}

def main():
    now=datetime.now(IST)
    print('\n'+'='*128)
    print(f'{VERSION} | V33 BIRLESIK GUN SONU TOP10')
    print(f'Tarama zamani: {now:%Y-%m-%d %H:%M}')
    print('Kural: Seans icinde hareket eden SON GUNLUK SATIR kosulsuz silinir.')
    print('Yeni: PATLAMA_ERKEN + TAVAN_DEVAM kapilari; klasik V33 A/B/C korunur.')
    print('='*128)
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
    if not rows:
        print('V33 adayi bulunamadi.'); return pd.DataFrame()
    df=pd.DataFrame(rows).sort_values(['V33_SKOR','MOTOR_E_DEVAM','MOTOR_D_ERKEN','MOTOR_B','MOTOR_A','RVOL'],ascending=False)
    top=df.head(10).copy()
    # Terminal karar ekrani: teknik detaylar CSV'de kalir, ekranda sadece karar bilgisi gorunur.
    def _kisa_not(r):
        sig=str(r.get('SINYAL',''))
        tip=str(r.get('ADAY_TIPI',''))
        if 'DUSUS_TEPKI' in sig and 'KIRILIM_ONAY' in sig:
            return 'Tepki + kirilim'
        if 'DARALMA_TEYIT' in sig and ('PATLAMA_ERKEN' in sig or 'PATLAMA_ERKEN' in tip):
            return 'Daralma + kirilim'
        if tip == 'TAVAN_DEVAM':
            return 'Guclu devam'
        if 'KIRILIM_ONAY' in sig:
            return 'Kirilim'
        if 'PATLAMA_ERKEN' in tip:
            return 'Erken patlama'
        return 'Takip'

    print('\nV33 - YARININ EN GUCLU 10 ADAYI')
    print('-'*72)
    print(f"{'#':>2}  {'HISSE':<7} {'FIYAT':>9} {'SKOR':>6}  {'ADAY TIPI':<18} KISA NOT")
    print('-'*72)
    for no, (_,r) in enumerate(top.iterrows(),1):
        print(f"{no:>2}  {str(r['HISSE']):<7} {float(r['GIRIS']):>9.2f} {float(r['V33_SKOR']):>6.1f}  {str(r['ADAY_TIPI']):<18} {_kisa_not(r)}")
    print('-'*72)
    print('Teknik motor detaylari ve sinyaller CSV dosyasinda kayitlidir.')
    fn=f'V33_GUN_SONU_TOP10_{now:%Y%m%d_%H%M}.csv'
    df.assign(TARAMA_ZAMANI=now.strftime('%Y-%m-%d %H:%M')).to_csv(result_file(fn),index=False,encoding='utf-8-sig')
    print('\nKaydedildi:',result_file(fn))
    return df

if __name__=='__main__': main()
