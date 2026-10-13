from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import time
import numpy as np
import pandas as pd
import yfinance as yf

from symbols import get_bist_symbols
from v19_paths import result_file

IST = ZoneInfo('Europe/Istanbul')
VERSION = 'ERKEN-3G-V4-DINLENME-SIKISMA-MERDIVEN'
SESSION_END_HOUR = 18
SESSION_END_MINUTE = 10


def _flat(d):
    if d is None or d.empty:
        return pd.DataFrame()
    x = d.copy()
    if isinstance(x.columns, pd.MultiIndex):
        x.columns = [c[0] for c in x.columns]
    x.columns = [str(c).title() for c in x.columns]
    idx = pd.DatetimeIndex(x.index)
    if idx.tz is not None:
        idx = idx.tz_convert('Europe/Istanbul').tz_localize(None)
    x.index = idx
    return x


def _completed_daily(d, now=None):
    from data_quality import completed_daily
    return completed_daily(_flat(d), now)


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _features(d, completed=False):
    x = _flat(d) if completed else _completed_daily(d)
    if len(x) < 120:
        return x

    o, h, l, c, v = x.Open, x.High, x.Low, x.Close, x.Volume
    x['RET1'] = c.pct_change() * 100
    for n in (2, 3, 5, 10, 20):
        x[f'RET{n}'] = (c / c.shift(n) - 1) * 100

    prev_close = c.shift(1).replace(0, np.nan)
    x['RANGE'] = 100 * (h - l) / prev_close
    x['CLV'] = (c - l) / (h - l).replace(0, np.nan)
    x['LOWER_WICK'] = (np.minimum(o, c) - l) / (h - l).replace(0, np.nan)
    x['UPPER_WICK'] = (h - np.maximum(o, c)) / (h - l).replace(0, np.nan)

    for n in (9, 21, 50):
        x[f'EMA{n}'] = _ema(c, n)
    x['EMA9_SLOPE'] = 100 * (x.EMA9 / x.EMA9.shift(3) - 1)
    x['EMA21_SLOPE'] = 100 * (x.EMA21 / x.EMA21.shift(5) - 1)

    x['VMA20'] = v.rolling(20).mean()
    x['RVOL'] = v / x.VMA20.replace(0, np.nan)
    x['RVOL_PREV1'] = v.shift(1) / x.VMA20.shift(1).replace(0, np.nan)
    x['VOL3_20_PREV'] = v.shift(1).rolling(3).mean() / x.VMA20.shift(1).replace(0, np.nan)
    x['VOL5_20'] = v.rolling(5).mean() / x.VMA20.replace(0, np.nan)
    x['VOL_WAKE'] = x.RVOL / x.VOL3_20_PREV.replace(0, np.nan)

    x['H10'] = h.shift(1).rolling(10).max()
    x['L10'] = l.shift(1).rolling(10).min()
    x['H20'] = h.shift(1).rolling(20).max()
    x['L20'] = l.shift(1).rolling(20).min()
    x['H40'] = h.shift(1).rolling(40).max()
    x['L40'] = l.shift(1).rolling(40).min()
    x['R10'] = 100 * (x.H10 / x.L10 - 1)
    x['R20'] = 100 * (x.H20 / x.L20 - 1)
    x['R40'] = 100 * (x.H40 / x.L40 - 1)
    x['DIST_R10'] = 100 * (c / x.H10 - 1)
    x['DIST_R20'] = 100 * (c / x.H20 - 1)

    x['RANGE3'] = x.RANGE.rolling(3).mean()
    x['RANGE5'] = x.RANGE.rolling(5).mean()
    x['RANGE20'] = x.RANGE.rolling(20).mean()
    x['CONTRACT_5_20'] = x.RANGE5 / x.RANGE20.replace(0, np.nan)
    x['CONTRACT_3_20'] = x.RANGE3 / x.RANGE20.replace(0, np.nan)

    # Son 10 gundeki en guclu onceki mum: devam-dinlenme paterni icin.
    x['PREV10_MAX_RET1'] = x.RET1.shift(1).rolling(10).max()
    x['PREV5_MAX_RET1'] = x.RET1.shift(1).rolling(5).max()

    # MERDIVEN-YUKSELIS: ilk dalgadan sonra daha yuksek dip ve kontrollu dinlenme.
    x['LOW3'] = l.rolling(3).min()
    x['PREV_LOW5'] = l.shift(3).rolling(5).min()
    x['HIGHER_LOW_%'] = 100 * (x.LOW3 / x.PREV_LOW5.replace(0, np.nan) - 1)
    x['RET10_PREV3'] = (c.shift(3) / c.shift(13) - 1) * 100

    # Merdiven alt tipleri icin: son 15 gundeki trend ve dinlenme kalitesi.
    x['RET15'] = c.pct_change(15) * 100
    x['REST_RANGE3_%'] = 100 * (h.rolling(3).max() / l.rolling(3).min().replace(0, np.nan) - 1)
    x['REST_RANGE5_%'] = 100 * (h.rolling(5).max() / l.rolling(5).min().replace(0, np.nan) - 1)
    x['EMA9_DIST_%'] = 100 * (c / x.EMA9.replace(0, np.nan) - 1)

    # DIPTE-DINLENME: sert dusus sonrasi 2-4 seans yeni dip yapmadan tabanlama.
    # PRIOR5_RET_3D_AGO = bugunden 3 seans once biten 5 seanslik hareket.
    x['PRIOR5_RET_3D_AGO'] = (c.shift(3) / c.shift(8) - 1) * 100
    x['LOW4'] = l.rolling(4).min()
    x['PREV_LOW4'] = l.shift(4).rolling(4).min()
    x['LOW4_CHANGE_%'] = 100 * (x.LOW4 / x.PREV_LOW4.replace(0, np.nan) - 1)
    x['BOUNCE_FROM_LOW4_%'] = 100 * (c / x.LOW4.replace(0, np.nan) - 1)
    return x


def _score(x):
    if x is None or x.empty or len(x) < 120:
        return None
    r = x.iloc[-1]
    need = [
        'Close','RET1','RET3','RET5','RET10','CLV','LOWER_WICK','UPPER_WICK',
        'EMA9','EMA21','EMA9_SLOPE','EMA21_SLOPE','RVOL','VOL3_20_PREV','VOL5_20',
        'VOL_WAKE','R10','R20','R40','DIST_R10','DIST_R20','CONTRACT_5_20',
        'CONTRACT_3_20','PREV10_MAX_RET1','PREV5_MAX_RET1','HIGHER_LOW_%','RET10_PREV3','RET15','REST_RANGE3_%','REST_RANGE5_%','EMA9_DIST_%',
        'PRIOR5_RET_3D_AGO','LOW4_CHANGE_%','BOUNCE_FROM_LOW4_%'
    ]
    if any(pd.isna(r.get(k)) for k in need):
        return None

    # Kullanici hedefi: patladiktan sonra degil, 1-3 seans ONCE.
    # +7% ve ustu bugun kosmussa erken havuzdan cikar.
    if r.RET1 >= 7.0:
        return None
    # Son 3 gunde asiri kosmus hisseleri de FOMO olarak ele.
    if r.RET3 >= 16.0 and r.PREV5_MAX_RET1 < 7.5:
        return None

    base = fall = gradual = rest = dinlenme = merdiven = dipte = money = timing = 0.0
    tags = []

    # 1) TABAN-SIKISMA: YKSLN/KZGYO tipi sessiz hazirlik.
    if r.CONTRACT_5_20 <= 0.78: base += 18
    elif r.CONTRACT_5_20 <= 0.90: base += 10
    if r.R10 <= 8.0: base += 15
    elif r.R10 <= 12.0: base += 9
    if r.R20 <= 16.0: base += 10
    if r.VOL3_20_PREV <= 0.78: base += 16
    elif r.VOL3_20_PREV <= 0.95: base += 8
    if -6.0 <= r.DIST_R20 <= 1.5: base += 12
    if abs(r.RET5) <= 5.0: base += 8
    if r.CLV >= 0.55: base += 6
    if base >= 52: tags.append('TABAN_SIKISMA')

    # 2) DUSUS-DURDU: MIATK/SUWEN tipi satisin kesilmesi.
    if r.RET10 <= -5.0: fall += 16
    elif r.RET10 <= -2.5: fall += 8
    if r.RET5 <= 1.0: fall += 10
    if r.RET3 >= -2.5: fall += 12
    if r.RET1 > -1.8: fall += 10
    if r.LOWER_WICK >= 0.22: fall += 8
    if r.CLV >= 0.58: fall += 8
    if r.RVOL >= 1.05: fall += 10
    if r.EMA9_SLOPE > -0.35: fall += 6
    if fall >= 48: tags.append('DUSUS_DURDU')

    # 3) KADEMELI-UYANIS: KZGYO tipi tavan olmadan ivmelenme.
    if 0.5 <= r.RET3 <= 9.0: gradual += 13
    if 1.0 <= r.RET5 <= 13.0: gradual += 12
    if -1.0 <= r.RET1 <= 5.5: gradual += 10
    if r.Close >= r.EMA9: gradual += 10
    if r.EMA9_SLOPE > 0: gradual += 10
    if r.RVOL >= 1.10: gradual += 10
    if r.VOL_WAKE >= 1.25: gradual += 10
    if -5.0 <= r.DIST_R20 <= 2.0: gradual += 10
    if gradual >= 52: tags.append('KADEMELI_UYANIS')

    # 4) DEVAM-DINLENME: ilk guclu hareketten sonra 1-3 gun sakinlesip ikinci dalga.
    recent_burst = r.PREV10_MAX_RET1 >= 7.5
    resting_now = (-3.0 <= r.RET1 <= 4.5 and -4.0 <= r.RET3 <= 8.0)
    if recent_burst: rest += 20
    if resting_now: rest += 16
    if r.CONTRACT_3_20 <= 0.95: rest += 10
    if r.CLV >= 0.55: rest += 8
    if r.Close >= r.EMA9: rest += 8
    if r.EMA9 > r.EMA21: rest += 8
    if r.RVOL >= 0.75: rest += 6
    if -5.0 <= r.DIST_R20 <= 3.0: rest += 8
    if rest >= 52: tags.append('DEVAM_DINLENME')

    # 5) DINLENME-BITIYOR: GRNYO tipi, 2-3 seans dar bantta oyalanip
    # fiyat bozulmadan hacmin yeniden canlanmasi. Ilk hareketi beklemeden zamanlama icin.
    quiet3 = (abs(r.RET3) <= 3.5 and r.CONTRACT_3_20 <= 0.90)
    price_holding = (r.RET1 >= -1.8 and r.CLV >= 0.50)
    near_trigger = (-5.0 <= r.DIST_R10 <= 1.5 or -5.0 <= r.DIST_R20 <= 1.5)
    if abs(r.RET3) <= 3.5: dinlenme += 16
    if r.CONTRACT_3_20 <= 0.90: dinlenme += 16
    elif r.CONTRACT_3_20 <= 1.00: dinlenme += 8
    if price_holding: dinlenme += 12
    if near_trigger: dinlenme += 14
    if r.VOL3_20_PREV <= 0.95: dinlenme += 10
    if r.VOL_WAKE >= 1.15: dinlenme += 10
    if r.EMA9_SLOPE > -0.20: dinlenme += 8
    if r.RET1 > 4.5: dinlenme -= 10
    if dinlenme >= 54: tags.append('DINLENME_BITIYOR')

    # 6) MERDIVEN-YUKSELIS: EGEEN/GIPTA tipi. Ilk dalga gelir, 1-3 gun
    # kontrollu dinlenir, dip onceki tabanin ustunde kalir ve yeni dalgaya hazirlanir.
    first_wave = (r.PREV10_MAX_RET1 >= 5.0 or r.RET10_PREV3 >= 7.0)
    controlled_rest = (-6.0 <= r.RET3 <= 6.0 and -5.5 <= r.RET1 <= 4.5)
    higher_low = (r['HIGHER_LOW_%'] >= 0.5)
    trend_alive = (r.Close >= r.EMA9 * 0.97 and r.EMA9_SLOPE > -0.50)
    if first_wave: merdiven += 20
    if controlled_rest: merdiven += 16
    if higher_low: merdiven += 18
    elif r['HIGHER_LOW_%'] >= -1.0: merdiven += 8
    if trend_alive: merdiven += 12
    if r.EMA9 > r.EMA21: merdiven += 10
    if r.CONTRACT_3_20 <= 1.05: merdiven += 8
    if r.CLV >= 0.48: merdiven += 6
    if 0.65 <= r.RVOL <= 3.50: merdiven += 6
    if r.RET3 > 10.0 or r.RET1 >= 7.0: merdiven -= 18
    if merdiven >= 56: tags.append('MERDIVEN_YUKSELIS')


    # MERDIVEN ALT TIPLERI: ayni paterni sadece sert tavan hisselerine gore egitmemek icin.
    # HIZLI: EGEEN/PATEK tipi; ilk dalga sert, dinlenme kisa ve yuksek dip korunuyor.
    mer_hizli = 0.0
    if r.PREV10_MAX_RET1 >= 7.5: mer_hizli += 24
    elif r.PREV10_MAX_RET1 >= 5.0: mer_hizli += 14
    if -5.5 <= r.RET3 <= 4.0: mer_hizli += 16
    if r['HIGHER_LOW_%'] >= 0.5: mer_hizli += 18
    if r['REST_RANGE3_%'] <= 8.0: mer_hizli += 12
    if r.Close >= r.EMA9 * 0.97: mer_hizli += 10
    if r.RET1 < 5.5: mer_hizli += 8

    # DUZENLI: KRDMD/KORDS tipi; 5-15 gunluk pozitif egim, arada dar dinlenmeler ve yuksek dip.
    mer_duzenli = 0.0
    if 3.0 <= r.RET10 <= 18.0: mer_duzenli += 20
    if 4.0 <= r['RET15'] <= 25.0: mer_duzenli += 14
    if -3.5 <= r.RET3 <= 5.5: mer_duzenli += 14
    if r['HIGHER_LOW_%'] >= 0.0: mer_duzenli += 16
    if r['REST_RANGE3_%'] <= 7.0: mer_duzenli += 12
    if r.EMA9 > r.EMA21 and r.EMA9_SLOPE > -0.15: mer_duzenli += 12
    if abs(r['EMA9_DIST_%']) <= 5.0: mer_duzenli += 8

    # YAVAS: TCELL/TKFEN tipi; daha dusuk gunluk ivme ama trend bozulmadan dinlenerek ilerleme.
    mer_yavas = 0.0
    if 1.5 <= r.RET10 <= 12.0: mer_yavas += 18
    if -3.0 <= r.RET3 <= 4.0: mer_yavas += 16
    if r['HIGHER_LOW_%'] >= -0.5: mer_yavas += 14
    if r['REST_RANGE5_%'] <= 10.0: mer_yavas += 12
    if r.Close >= r.EMA21 * 0.98: mer_yavas += 10
    if r.EMA9_SLOPE > -0.20: mer_yavas += 10
    if 0.55 <= r.RVOL <= 2.5: mer_yavas += 8

    merdiven_alt = max(mer_hizli, mer_duzenli, mer_yavas)
    if merdiven_alt >= 58:
        merdiven = max(merdiven, merdiven_alt)
        if merdiven_alt == mer_hizli: tags.append('MERDIVEN_HIZLI')
        elif merdiven_alt == mer_duzenli: tags.append('MERDIVEN_DUZENLI')
        else: tags.append('MERDIVEN_YAVAS')

    # 7) DIPTE-DINLENME: MOGAN/AHSGY tipi. Once sert dusus, sonra 2-4 seans
    # yeni dip uretmeden tabanlama; hacim canlanirken fiyat artik kolay bozulmaz.
    sharp_fall_before = (r.PRIOR5_RET_3D_AGO <= -7.0 or r.RET10 <= -10.0)
    no_fresh_break = (r['LOW4_CHANGE_%'] >= -2.5)
    base_after_fall = (-4.0 <= r.RET3 <= 5.0 and r.RET1 >= -2.5)
    if sharp_fall_before: dipte += 22
    if no_fresh_break: dipte += 18
    elif r['LOW4_CHANGE_%'] >= -4.0: dipte += 8
    if base_after_fall: dipte += 16
    if r['BOUNCE_FROM_LOW4_%'] <= 8.0: dipte += 8
    if r.CLV >= 0.52: dipte += 8
    if r.LOWER_WICK >= 0.15: dipte += 6
    if r.VOL_WAKE >= 1.15: dipte += 10
    elif r.RVOL >= 1.05: dipte += 6
    if r.EMA9_SLOPE > -0.60: dipte += 6
    if r.RET1 > 5.5: dipte -= 12
    if dipte >= 56: tags.append('DIPTE_DINLENME')

    # PARA-GIRISI / HACIM GECISI: hacim tek basina degil, fiyat kabuluyla beraber.
    dry_then_wake = (r.VOL3_20_PREV <= 0.85 and r.RVOL >= 1.15)
    if dry_then_wake:
        money += 24
        tags.append('HACIM_KURUDU_UYANDI')
    if r.VOL_WAKE >= 1.50: money += 14
    elif r.VOL_WAKE >= 1.20: money += 8
    if r.RVOL >= 1.50: money += 12
    elif r.RVOL >= 1.10: money += 7
    if r.CLV >= 0.70: money += 12
    elif r.CLV >= 0.58: money += 6
    if r.LOWER_WICK >= 0.20: money += 7
    if r.UPPER_WICK <= 0.30: money += 6
    if r.RET1 < 5.5: money += 5
    if money >= 45: tags.append('PARA_GIRISI')

    # 3 GUN ZAMANLAMA: sadece guzel grafik degil, fitile yaklasmis aday.
    if -3.5 <= r.DIST_R20 <= 1.5: timing += 22
    elif -6.0 <= r.DIST_R20 < -3.5: timing += 12
    if r.CONTRACT_5_20 <= 0.85: timing += 14
    if dinlenme >= 54: timing += 10
    if merdiven >= 56: timing += 12
    if merdiven_alt >= 58: timing += 8
    if dipte >= 56: timing += 12
    if dry_then_wake: timing += 16
    elif r.VOL_WAKE >= 1.25: timing += 10
    if r.EMA9_SLOPE > 0: timing += 12
    elif r.EMA9_SLOPE > -0.25: timing += 6
    if r.CLV >= 0.65: timing += 12
    if -1.5 <= r.RET1 <= 4.5: timing += 10
    if r.RET3 <= 10.0: timing += 6
    if r.UPPER_WICK >= 0.55: timing -= 8
    if r.RVOL > 6.0: timing -= 8
    timing = max(0.0, timing)

    pattern_best = max(base, fall, gradual, rest, dinlenme, merdiven, dipte)
    if pattern_best < 42:
        return None

    # Nihai skor: patern + para girisi + zamanlama. 3-gun penceresine agirlik verilir.
    score = 0.48 * pattern_best + 0.24 * money + 0.38 * timing

    # Iki farkli patern ayni anda gucluyse bonus.
    strong_patterns = sum(v >= 48 for v in (base, fall, gradual, rest, dinlenme, merdiven, dipte))
    if strong_patterns >= 2:
        score += 7
        tags.append('COKLU_PATTERN')

    # Hacim uyandi ama fiyat henuz kosmadiysa ekstra erkenlik bonusu.
    if dry_then_wake and r.RET1 <= 4.0:
        score += 6
        tags.append('ERKENLIK_BONUS')

    score = max(0, min(100, score))

    vals = {
        'TABAN_SIKISMA': base,
        'DUSUS_DURDU': fall,
        'KADEMELI_UYANIS': gradual,
        'DEVAM_DINLENME': rest,
        'DINLENME_BITIYOR': dinlenme,
        'MERDIVEN_YUKSELIS': merdiven,
        'DIPTE_DINLENME': dipte,
    }
    aday_tipi = max(vals, key=vals.get)
    if aday_tipi == 'MERDIVEN_YUKSELIS' and merdiven_alt >= 58:
        if merdiven_alt == mer_hizli: aday_tipi = 'MERDIVEN_HIZLI'
        elif merdiven_alt == mer_duzenli: aday_tipi = 'MERDIVEN_DUZENLI'
        else: aday_tipi = 'MERDIVEN_YAVAS'

    if timing >= 62 and money >= 40:
        asama = 'UYANIS-GUCLU'
    elif timing >= 52:
        asama = 'UYANIS'
    elif base >= 52 and r.VOL3_20_PREV <= 0.85:
        asama = 'UYKU-SONU'
    else:
        asama = 'HAZIRLIK'

    return {
        'ERKEN3G_SKOR': round(score, 2),
        'ADAY_TIPI': aday_tipi,
        'ASAMA': asama,
        'TABAN': round(base, 1),
        'DUSUS_DURDU': round(fall, 1),
        'KADEMELI': round(gradual, 1),
        'DEVAM_DINLENME': round(rest, 1),
        'DINLENME_BITIYOR': round(dinlenme, 1),
        'MERDIVEN_YUKSELIS': round(merdiven, 1),
        'MERDIVEN_HIZLI': round(mer_hizli, 1),
        'MERDIVEN_DUZENLI': round(mer_duzenli, 1),
        'MERDIVEN_YAVAS': round(mer_yavas, 1),
        'DIPTE_DINLENME': round(dipte, 1),
        'PARA_GIRISI': round(money, 1),
        'ZAMANLAMA_3G': round(timing, 1),
        'GIRIS': float(r.Close),
        'RET1_%': float(r.RET1),
        'RET3_%': float(r.RET3),
        'RET5_%': float(r.RET5),
        'RVOL': float(r.RVOL),
        'VOL_WAKE': float(r.VOL_WAKE),
        'VOL3_20_PREV': float(r.VOL3_20_PREV),
        'DIST_R20_%': float(r.DIST_R20),
        'CONTRACT': float(r.CONTRACT_5_20),
        'CLV': float(r.CLV),
        'SINYAL': '+'.join(tags) if tags else 'HAZIRLIK',
        'VERI_TARIHI': pd.Timestamp(r.name).strftime('%Y-%m-%d'),
    }



def _hedef_3g(score, timing):
    # Sadece gorsel karar yardimi; garanti/hedef fiyat degildir.
    if score >= 93 and timing >= 65:
        return "%7-%12"
    if score >= 88:
        return "%6-%10"
    if score >= 82:
        return "%5-%9"
    return "%4-%8"


def _kisa_not(r):
    tags = str(r.get('SINYAL', ''))
    aday = str(r.get('ADAY_TIPI', ''))
    dist = float(r.get('DIST_R20_%', 0) or 0)
    if 'TABAN_SIKISMA' in tags or aday == 'TABAN_SIKISMA':
        return 'Yatay sikisma, hareket hazirligi'
    if 'DUSUS_DURDU' in tags or aday == 'DUSUS_DURDU':
        return 'Dususte durulma, hacim teyidi'
    if 'KADEMELI_UYANIS' in tags or aday == 'KADEMELI_UYANIS':
        if dist > -3:
            return 'Momentum gucleniyor, dirence yakin'
        return 'Hacim artisi, momentum gucleniyor'
    if 'MERDIVEN_YUKSELIS' in tags or aday == 'MERDIVEN_YUKSELIS':
        return 'Yuksek dip + dinlenme, yeni dalga adayi'
    if 'DEVAM_DINLENME' in tags or aday == 'DEVAM_DINLENME':
        return 'Dinlenme sonrasi ikinci dalga adayi'
    if 'DINLENME_BITIYOR' in tags or aday == 'DINLENME_BITIYOR':
        return 'Dar dinlenme bitiyor, tetige yakin'
    if 'DIPTE_DINLENME' in tags or aday == 'DIPTE_DINLENME':
        return 'Sert dusus bitti, dipte tabanlama + hacim'
    if float(r.get('PARA_GIRISI', 0) or 0) >= 65:
        return 'Guclu para girisi / hacim teyidi'
    return 'Hazirlik yapisi gucleniyor'


def _print_compact_top10(top):
    print('\n' + '=' * 112)
    print('ERKEN-3G | ONUMUZDEKI 3 SEANS ICIN EN GUCLU 10 ADAY')
    print('=' * 112)
    print(f"{'#':>2}  {'HISSE':<7} {'FIYAT':>10} {'SKOR':>6}  {'ADAY TIPI':<20} {'3G HEDEF':>10}  KISA NOT")
    print('-' * 112)
    for i, (_, r) in enumerate(top.iterrows(), 1):
        hisse = str(r['HISSE'])[:7]
        fiyat = float(r['GIRIS'])
        skor = float(r['ERKEN3G_SKOR'])
        aday = str(r['ADAY_TIPI']).replace('_', ' ')[:20]
        hedef = _hedef_3g(skor, float(r.get('ZAMANLAMA_3G', 0) or 0))
        note = _kisa_not(r)[:42]
        print(f"{i:>2}  {hisse:<7} {fiyat:>10.2f} {skor:>6.0f}  {aday:<20} {hedef:>10}  {note}")
    whale_cols=[c for c in ['HISSE','ASAMA','BALINA_DURUMU','BALINA_IZI_SKOR','BALINA_NOTU'] if c in top]
    if 'BALINA_DURUMU' in top:
        print('UYUYAN HAVUZ | BALINA IZI KATMANI')
        print(top[whale_cols].to_string(index=False))
    print('-' * 112)
    tarih = str(top.iloc[0].get('VERI_TARIHI', '')) if len(top) else ''
    print(f'Veri tarihi: {tarih} | Ana hedef: D+1 / D+2 / D+3 icinde guclu hareket')
    print('Not: 3G HEDEF teknik hareket araligidir; yatirim tavsiyesi veya garanti degildir.')
    print('=' * 112)

def main():
    now = datetime.now(IST)
    print('\n' + '=' * 150)
    print(f'{VERSION} | 3 GUN ICINDE PATLAMA ADAY HAVUZU | TOP10')
    print(f'Tarama zamani: {now:%Y-%m-%d %H:%M}')
    print('Basari hedefi: sinyalden sonraki D+1 / D+2 / D+3 icinde +5 / +7 / +9.5 hareket.')
    print('Erken havuz: bugun +7% ve ustu kosmus hisseler disarida; FOMO yerine hazirlik/uyanis aranir.')
    print('=' * 150)

    rows = []; checked = {}; failed = []
    syms = get_bist_symbols()
    for i, s in enumerate(syms, 1):
        print(f'\r[{i}/{len(syms)}] {s:<14}', end='', flush=True)
        try:
            d = yf.download(s, period='18mo', interval='1d', auto_adjust=False,
                            progress=False, threads=False, timeout=12)
            completed=_completed_daily(d,now)
            if len(completed)<120:raise ValueError('Yeterli tamamlanmis veri yok')
            checked[s.replace('.IS','')]=pd.Timestamp(completed.index[-1]).strftime('%Y-%m-%d')
            rec = _score(_features(completed,completed=True))
            if rec:
                rec['HISSE'] = s.replace('.IS', '')
                from sleeper_whale import annotate
                rec=annotate(rec,completed,s)
                rows.append(rec)
        except Exception:
            failed.append(s.replace(".IS",""))
        time.sleep(.002)
    print()

    from sleeper_pool import save_and_show
    save_and_show(pd.DataFrame(rows),checked,failed,now)
    pd.DataFrame({'HISSE':failed}).to_csv(result_file('ERKEN3G_VERI_EKSIK.csv'),index=False,encoding='utf-8-sig')
    if not rows:
        print('ERKEN-3G adayi bulunamadi.')
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values(
        ['ERKEN3G_SKOR', 'ZAMANLAMA_3G', 'PARA_GIRISI', 'RVOL'],
        ascending=False
    )
    top = df.head(10).copy()
    # Ekranda sadece karar icin gerekli sutunlari goster.
    # Ayrintili tum metrikler CSV dosyasinda korunur.
    _print_compact_top10(top)

    fn = f'ERKEN3G_TOP10_{now:%Y%m%d_%H%M}.csv'
    out = df.assign(TARAMA_ZAMANI=now.strftime('%Y-%m-%d %H:%M'))
    out.to_csv(result_file(fn), index=False, encoding='utf-8-sig')
    print('\nKaydedildi:', result_file(fn))
    return df


if __name__ == '__main__':
    main()
