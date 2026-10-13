from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

import erken3g_havuz as e3
import v19_2_canli as live
from v19_paths import result_file

IST = ZoneInfo('Europe/Istanbul')
VERSION = 'ERKEN3G-DONUS-KESISIM-V1'


def _norm(s):
    return str(s).replace('.IS','').strip().upper()


def _grade(row):
    e = float(row.get('ERKEN3G_SKOR',0) or 0)
    z = float(row.get('ZAMANLAMA_3G',0) or 0)
    p = float(row.get('PARA_GIRISI',0) or 0)
    d = float(row.get('DONUS_PUAN',0) or 0)
    tepki = float(row.get('TEPKI_%',0) or 0)
    # Gün sonu hazırlığı ana, canlı dönüş teyidi güçlendirici.
    score = 0.44*e + 0.20*z + 0.12*p + 0.24*d
    if d >= 76: score += 6
    if z >= 62: score += 5
    if p >= 45: score += 4
    if tepki >= 3: score += 3
    return min(100.0, score)


def main():
    now = datetime.now(IST)
    print('\n'+'='*130)
    print(f'{VERSION} | GUN SONU ERKEN-3G + CANLI DONUS AVCISI KESISIMI')
    print('Amaç: Önceden hazırlanmış hisselerden hangisi canlıda gerçekten dönüyor?')
    print('='*130)

    print('\n[1/2] ERKEN-3G havuzu taranıyor...')
    e = e3.main()
    if e is None or e.empty:
        print('ERKEN-3G havuzunda aday yok; kesişim üretilemedi.')
        return pd.DataFrame()
    e = e.copy()
    e['HISSE'] = e['HISSE'].map(_norm)
    e = e.sort_values(['ERKEN3G_SKOR','ZAMANLAMA_3G','PARA_GIRISI'],ascending=False).head(20)

    print('\n[2/2] Dönüş Avcısı canlı teyidi çalışıyor...')
    d = live.reversal_main()
    if d is None or d.empty:
        print('Dönüş Avcısı canlı aday üretmedi; kesişim yok.')
        return pd.DataFrame()
    d = d.copy()
    d['HISSE'] = d['HISSE'].map(_norm)
    d = d.rename(columns={'PUAN':'DONUS_PUAN','SINYAL':'DONUS_SINYAL','GIRIS':'CANLI_GIRIS'})

    cols_d = [c for c in ['HISSE','DONUS_PUAN','DONUS_SINYAL','DUSUS_%','TEPKI_%','CANLI_GIRIS','HISSE_BAR_ZAMANI','RVOL3','VWAP_%','DI_SPREAD'] if c in d.columns]
    out = e.merge(d[cols_d], on='HISSE', how='inner')
    if out.empty:
        print('\nKESISIM YOK: ERKEN-3G Top20 ile Dönüş Avcısı adayları şu anda örtüşmüyor.')
        return out

    from entry_status import classify
    statuses=pd.DataFrame([classify(r,now) for _,r in out.iterrows()],index=out.index)
    for col in statuses: out[col]=statuses[col]
    out['BIRLESIK_SKOR'] = out.apply(_grade, axis=1)
    out['TEYIT'] = out['BIRLESIK_SKOR'].apply(lambda x: 'COK GUCLU' if x>=82 else ('GUCLU' if x>=72 else ('ORTA' if x>=62 else 'TAKIP')))
    out = out.sort_values(['BIRLESIK_SKOR','DONUS_PUAN','ZAMANLAMA_3G','ERKEN3G_SKOR'],ascending=False)

    show = [c for c in ['HISSE','BIRLESIK_SKOR','TEYIT','GIRIS_DURUMU','TETIK_GIRIS','GIRIS_NEDENI','ERKEN3G_SKOR','ADAY_TIPI','ASAMA','ZAMANLAMA_3G','PARA_GIRISI','DONUS_PUAN','DUSUS_%','TEPKI_%','CANLI_GIRIS','DONUS_SINYAL'] if c in out.columns]
    print('\nERKEN-3G + DONUS AVCISI | CANLI KESISIM')
    with pd.option_context('display.width',240,'display.max_colwidth',60):
        print(out[show].head(10).to_string(index=False))

    fn = f'ERKEN3G_DONUS_KESISIM_{now:%Y%m%d_%H%M}.csv'
    out.to_csv(result_file(fn),index=False,encoding='utf-8-sig')
    print('\nKaydedildi:', result_file(fn))
    print('Not: Bu liste otomatik alım emri değildir; gün sonu hazırlığı + canlı dönüş teyididir.')
    return out

if __name__=='__main__':
    main()
