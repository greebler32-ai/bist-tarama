"""Ayni tamamlanmis OHLCV verisinden ERKEN-3G ve balina izi kesisimi."""
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from v19_paths import result_file


def combine(early, whale, symbol):
    if not early or not whale: return None
    if whale.get('ADAY_TIPI') not in ('BIRIKIM_ADAYI','GUCLU_ALIM_IZI'): return None
    if str(early.get('VERI_TARIHI')) != str(whale.get('VERI_TARIHI')): return None
    out=dict(early)
    out.update({'HISSE':symbol.removesuffix('.IS'),'BALINA_DURUMU':whale['ADAY_TIPI'],'BALINA_IZI_SKOR':whale['BALINA_IZI_SKOR'],'CMF20':whale['CMF20'],'OBV5_ORAN':whale['OBV5_ORAN'],'BALINA_RVOL':whale['RVOL'],'KURUM_TEYIDI':'YOK','GIRIS_DURUMU':'CANLI_TEYIT_BEKLIYOR','REFERANS_FIYAT':early['GIRIS'],'FIYAT':early['GIRIS'],'VERI_TURU':'TAMAMLANMIS_GUNLUK_FIYAT_HACIM'})
    # Iki motor ayni veriyi kullandigi icin ek kesinlik/olasilik skoru uydurulmaz.
    return out


def attach_live(candidates, live_rows, now=None):
    from entry_status import classify
    if candidates is None or candidates.empty: return candidates
    out=candidates.copy()
    lookup={}
    if live_rows is not None and not live_rows.empty:
        for _,r in live_rows.iterrows(): lookup[str(r.HISSE).upper().removesuffix('.IS')]=r
    for idx,row in out.iterrows():
        match=lookup.get(str(row.HISSE).upper().removesuffix('.IS'))
        if match is None:
            out.at[idx,'GIRIS_DURUMU']='CANLI_TEYIT_BEKLIYOR'
            out.at[idx,'GIRIS_NEDENI']='Donus Avcisi teyidi yok veya veri alinamadi'
            continue
        rec=match.to_dict()
        rec['CANLI_GIRIS']=rec.get('GIRIS')
        rec['DONUS_PUAN']=rec.get('PUAN')
        state=classify(rec,now)
        if state['GIRIS_DURUMU']=='GIRIS_TETIKLENDI':
            for key in ('GIRIS','STOP','HEDEF','KAZANC_%'):
                if key in rec:out.at[idx,key]=rec[key]

        for key,value in state.items():out.at[idx,key]=value
        for key in ('HISSE_BAR_ZAMANI','CANLI_GIRIS','DONUS_PUAN','RVOL3','VWAP_%','DI_SPREAD','TEPKI_%'):
            if key in rec:out.at[idx,key]=rec[key]
        # Gecmis gunluk referans fiyatini koru. Canli sinyal icin ayri fiyat alani kullan.
    return out


def main():
    import yfinance as yf
    import erken3g_havuz as e3
    from balina_izi import analyse
    from symbols import get_bist_symbols
    today=datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%Y-%m-%d')
    rows=[];errors=[]
    symbols=get_bist_symbols()
    print('BALINA IZI + ERKEN-3G | Ayni tamamlanmis gunluk veri | Canli giris teyidi beklenir.')
    for i,s in enumerate(symbols,1):
        try:
            x=e3._flat(yf.download(s,period='18mo',interval='1d',auto_adjust=False,progress=False,threads=False,timeout=15))
            x=x[[str(d.date())<today for d in x.index]]
            if len(x)<140:raise ValueError('En az 140 tamamlanmis bar gerekir')
            early=e3._score(e3._features(x,completed=True))
            whale=analyse(x,s)
            row=combine(early,whale,s)
            if row: rows.append(row)
        except Exception as exc:errors.append({'HISSE':s,'HATA':str(exc)})
        if i%50==0:print(f'{i}/{len(symbols)} | Ortak aday: {len(rows)}')
    df=pd.DataFrame(rows)
    if not df.empty:df=df.sort_values(['ERKEN3G_SKOR','BALINA_IZI_SKOR','ZAMANLAMA_3G'],ascending=False)
    else:df=pd.DataFrame(columns=['HISSE','ADAY_TIPI','BALINA_DURUMU','ERKEN3G_SKOR','BALINA_IZI_SKOR','GIRIS_DURUMU'])
    if not df.empty:
        from datetime import time
        now=datetime.now(ZoneInfo('Europe/Istanbul'))
        if now.weekday()<5 and time(10,0)<=now.time()<=time(18,0):
            import v19_2_canli as live
            print('Ortak adaylarda canli 15dk Donus Avcisi teyidi taraniyor...')
            try:
                found=live.reversal_main(symbols=[s+'.IS' for s in df.HISSE])
                df=attach_live(df,found,now)
            except Exception as exc:
                df['GIRIS_DURUMU']='VERI_TEYIDI_BEKLIYOR'
                df['GIRIS_NEDENI']='Canli tarama hatasi: '+str(exc)
        else:
            df['GIRIS_DURUMU']='SEANS_DISI'
            df['GIRIS_NEDENI']='Canli teyit seans saatinde yapilir'
    stamp=datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%Y%m%d_%H%M%S')
    df.to_csv(result_file(f'BALINA_ERKEN3G_KESISIM_{stamp}.csv'),index=False,encoding='utf-8-sig')
    pd.DataFrame(errors,columns=['HISSE','HATA']).to_csv(result_file(f'BALINA_ERKEN3G_VERI_HATALARI_{stamp}.csv'),index=False,encoding='utf-8-sig')
    cols=[c for c in ['HISSE','VERI_TARIHI','REFERANS_FIYAT','ADAY_TIPI','BALINA_DURUMU','ERKEN3G_SKOR','BALINA_IZI_SKOR','GIRIS_DURUMU','TETIK_GIRIS','GIRIS_NEDENI'] if c in df]
    print(df[cols].head(20).to_string(index=False) if not df.empty else 'Ortak aday yok; zorla aday uretilmedi.')
    print(f'Tum ortak adaylar kaydedildi. Veri hatasi: {len(errors)}. Referans fiyat islem girisi degildir.')
    return df
