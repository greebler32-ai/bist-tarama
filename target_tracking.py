"""Sabit sinyal hedeflerini sonraki gunluk mumlarda izler."""
import numpy as np
import pandas as pd


def evaluate_targets(row, bars, sessions=None):
    levels = [pd.to_numeric(row.get(k), errors='coerce') for k in ('FIYAT','H1','H2','H3','YAPI_BOZULMA')]
    if any(pd.isna(v) or not np.isfinite(v) for v in levels):
        return {'HEDEF_DURUMU':'HEDEF_VERISI_EKSIK'}
    entry,h1,h2,h3,stop=levels
    if not 0 < stop < entry < h1 < h2 < h3:
        return {'HEDEF_DURUMU':'GECERSIZ_SEVIYE'}
    day=pd.Timestamp(row['TARAMA_ZAMANI']).normalize()
    x=bars.sort_index().loc[lambda d:d.index>day]
    result={'HEDEF_DURUMU':'BEKLIYOR','YAPI_BOZULMA_GUNU':'','HEDEF_SON_BAR':str(x.index[-1].date()) if not x.empty else ''}
    for n in (1,2,3):
        result[f'H{n}_DURUM']='BEKLIYOR';result[f'H{n}_GUN']=''
    if sessions is not None and not x.empty:
        expected=[pd.Timestamp(d) for d in sessions if day<pd.Timestamp(d)<=x.index[-1]]
        if any(d not in x.index for d in expected):
            return dict(result,HEDEF_DURUMU='VERI_EKSIK')
    for date, b in x.iterrows():
        if not np.isfinite(b.High) or not np.isfinite(b.Low):
            result['HEDEF_DURUMU']='VERI_EKSIK';break
        # Ayni gun hedef-stop sirasi bilinmez: stop oncelikli ihtiyatli olcum.
        if float(b.Low)<=stop:
            result['HEDEF_DURUMU']='YAPI_BOZULDU'
            result['YAPI_BOZULMA_GUNU']=str(date.date())
            for n,level in enumerate((h1,h2,h3),1):
                if result[f'H{n}_DURUM']=='BEKLIYOR':
                    result[f'H{n}_DURUM']='AYNI_BAR_BELIRSIZ' if float(b.High)>=level else 'IPTAL'
            break
        for n,level in enumerate((h1,h2,h3),1):
            if result[f'H{n}_DURUM']=='BEKLIYOR' and float(b.High)>=level:
                result[f'H{n}_DURUM']='ULASTI';result[f'H{n}_GUN']=str(date.date())
        if result['H3_DURUM']=='ULASTI':
            result['HEDEF_DURUMU']='H3_TAMAMLANDI';break
        if result['H2_DURUM']=='ULASTI': result['HEDEF_DURUMU']='H2_ULASTI'
        elif result['H1_DURUM']=='ULASTI': result['HEDEF_DURUMU']='H1_ULASTI'
    result['HEDEF_OLCUMU']='SONRAKI_GUNLUK_MUMLAR_STOP_ONCELIKLI'
    return result
