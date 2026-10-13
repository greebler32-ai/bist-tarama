"""Uyuyan adaylari ardil tamamlanmis veri tarihlerinde izler."""
import pandas as pd
from v19_paths import result_file

COLUMNS=['HISSE','ILK_GORULME','SON_TARAMA','VERI_TARIHI','ONCEKI_ASAMA','ASAMA','HAVUZ_DURUMU','GECIS','ILK_FIYAT','SON_FIYAT','ERKEN3G_SKOR','ADAY_TIPI','BALINA_DURUMU','BALINA_IZI_SKOR']

def update_pool(previous, candidates, checked, failed, scanned_at):
    records={str(r.HISSE):r.to_dict() for _,r in previous.iterrows()} if previous is not None and not previous.empty else {}
    current={str(r.HISSE):r.to_dict() for _,r in candidates.iterrows()} if candidates is not None and not candidates.empty else {}
    for symbol in sorted(set(records)|set(current)):
        old=records.get(symbol); new=current.get(symbol)
        if symbol in failed:
            if old:records[symbol]=dict(old,SON_TARAMA=scanned_at,HAVUZ_DURUMU='VERI_KONTROL_EDILEMEDI',GECIS='VERI_EKSIK')
            continue
        if symbol not in checked:continue
        date=checked[symbol]
        if old and str(old.get('VERI_TARIHI',''))>date:continue
        if new:
            stage=str(new.get('ASAMA','HAZIRLIK'))
            prev=str(old.get('ASAMA','')) if old else ''
            # Ayni veri tekrar taraninca ayni uyanis tekrar bildirilmez.
            changed=bool(old and date>str(old.get('VERI_TARIHI','')) and stage!=prev)
            transition=(prev+' -> '+stage) if changed else 'YENI_ADAY' if not old else 'AYNI_ASAMA'
            records[symbol]={'HISSE':symbol,'ILK_GORULME':old.get('ILK_GORULME') if old else scanned_at,'SON_TARAMA':scanned_at,'VERI_TARIHI':date,'ONCEKI_ASAMA':prev,'ASAMA':stage,'HAVUZ_DURUMU':'AKTIF_ADAY','GECIS':transition,'ILK_FIYAT':old.get('ILK_FIYAT') if old else new.get('GIRIS'),'SON_FIYAT':new.get('GIRIS'),'ERKEN3G_SKOR':new.get('ERKEN3G_SKOR'),'ADAY_TIPI':new.get('ADAY_TIPI'),'BALINA_DURUMU':new.get('BALINA_DURUMU',''),'BALINA_IZI_SKOR':new.get('BALINA_IZI_SKOR','')}
        elif old:
            records[symbol]=dict(old,SON_TARAMA=scanned_at,VERI_TARIHI=date,HAVUZ_DURUMU='GUNCEL_KRITER_DISI',GECIS='KRITER_DISI')
    return pd.DataFrame(list(records.values()),columns=COLUMNS)


EVENT_COLUMNS=['OLAY_ID','TARAMA_ZAMANI','HISSE','VERI_TARIHI','OLAY','ONCEKI_ASAMA','YENI_ASAMA','ONCEKI_DURUM','YENI_DURUM','FIYAT','ERKEN3G_SKOR']


def build_events(previous, current, scanned_at):
    from hashlib import sha256
    old={str(r.HISSE):r.to_dict() for _,r in previous.iterrows()} if previous is not None and not previous.empty else {}
    rows=[]
    for _,r in current.iterrows():
        before=old.get(str(r.HISSE),{})
        before_state=str(before.get('HAVUZ_DURUMU',''))
        before_stage=str(before.get('ASAMA',''))
        if not before:kind='ILK_ADAY'
        elif before_state != str(r.HAVUZ_DURUMU):
            kind='VERI_EKSIK' if r.HAVUZ_DURUMU=='VERI_KONTROL_EDILEMEDI' else 'KRITER_DISI' if r.HAVUZ_DURUMU=='GUNCEL_KRITER_DISI' else 'HAVUZA_DONDU'
        elif before_stage != str(r.ASAMA):
            kind='ASAMA_DEGISIMI' if str(r.VERI_TARIHI)>str(before.get('VERI_TARIHI','')) else 'VERI_REVIZYONU'
        else:continue
        raw='|'.join([str(r.HISSE),str(r.VERI_TARIHI),kind,before_stage,str(r.ASAMA),before_state,str(r.HAVUZ_DURUMU)])
        rows.append({'OLAY_ID':sha256(raw.encode()).hexdigest()[:24],'TARAMA_ZAMANI':scanned_at,'HISSE':r.HISSE,'VERI_TARIHI':r.VERI_TARIHI,'OLAY':kind,'ONCEKI_ASAMA':before_stage,'YENI_ASAMA':r.ASAMA,'ONCEKI_DURUM':before_state,'YENI_DURUM':r.HAVUZ_DURUMU,'FIYAT':r.SON_FIYAT,'ERKEN3G_SKOR':r.ERKEN3G_SKOR})
    return pd.DataFrame(rows,columns=EVENT_COLUMNS)


def append_events(events):
    path=result_file('UYUYAN_HISSE_GECIS_GECMISI.csv')
    old=pd.read_csv(path,encoding='utf-8-sig') if path.exists() else pd.DataFrame(columns=EVENT_COLUMNS)
    combined=(events.copy() if old.empty else old.copy() if events.empty else pd.concat([old,events],ignore_index=True)).drop_duplicates('OLAY_ID',keep='first')
    temp=path.with_suffix('.tmp');combined.to_csv(temp,index=False,encoding='utf-8-sig');temp.replace(path)
    return combined


def history(symbol):
    path=result_file('UYUYAN_HISSE_GECIS_GECMISI.csv')
    if not path.exists():print('Gecis gecmisi bos; Menu 20 ile tarama yapin.');return pd.DataFrame()
    df=pd.read_csv(path,encoding='utf-8-sig').fillna('')
    sym=str(symbol).strip().upper().removesuffix('.IS')
    x=df[df.HISSE.astype(str).str.upper()==sym].sort_values('TARAMA_ZAMANI')
    print(x[['TARAMA_ZAMANI','VERI_TARIHI','OLAY','ONCEKI_ASAMA','YENI_ASAMA','FIYAT']].to_string(index=False) if not x.empty else f'{sym} gecis kaydi yok.')
    return x


def save_and_show(candidates, checked, failed, now):
    path=result_file('UYUYAN_HISSE_KALICI_HAVUZ.csv')
    previous=pd.read_csv(path,encoding='utf-8-sig') if path.exists() else pd.DataFrame(columns=COLUMNS)
    pool=update_pool(previous,candidates,checked,failed,now.strftime('%Y-%m-%d %H:%M:%S'))
    events=build_events(previous,pool,now.strftime('%Y-%m-%d %H:%M:%S'))
    append_events(events)
    if path.exists():path.with_suffix('.onceki.csv').write_bytes(path.read_bytes())
    temp=path.with_suffix('.tmp');pool.to_csv(temp,index=False,encoding='utf-8-sig');temp.replace(path)
    if pool.empty:print('Kalici uyuyan havuzu henuz bos.');return pool
    active=pool[pool.HAVUZ_DURUMU=='AKTIF_ADAY']
    sleeping=active[active.ASAMA.isin(['UYKU-SONU','HAZIRLIK'])]
    waking=active[active.ASAMA.isin(['UYANIS','UYANIS-GUCLU'])]
    print(f'KALICI HAVUZ | Uyku/hazirlik: {len(sleeping)} | Uyanis: {len(waking)} | Veri kontrol edilemedi: {int((pool.HAVUZ_DURUMU=="VERI_KONTROL_EDILEMEDI").sum())}')
    transitions=pool[pool.GECIS.astype(str).str.contains(' -> ',regex=False)]
    if not transitions.empty:print(transitions[['HISSE','VERI_TARIHI','GECIS']].head(20).to_string(index=False))
    print('GUNCEL_KRITER_DISI yapinin bozuldugu anlamina gelmez; aday filtresi artik saglanmiyor.')
    return pool
