from __future__ import annotations

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import pandas as pd

from v19_paths import results_dir, result_file

VERSION = 'TARAMA-HAFIZASI-V1'
MEMORY_FILE = 'TARAMA_HAFIZASI.csv'
RUN_FILE = 'TARAMA_CALISMA_GUNLUGU.csv'

_SYMBOL_KEYS = ['HISSE','symbol','SYMBOL','Sembol','sembol','Ticker','ticker']
_SCORE_KEYS = ['ERKEN3G_SKOR','BALINA_IZI_SKOR','V33_SKOR','PATLAMA_PUANI','BIRLESIK_SKOR','PUAN','score','SKOR','avg_score']
_PRICE_KEYS = ['TETIK_GIRIS','CANLI_GIRIS','GIRIS','FIYAT','KAPANIS','entry','Close','close','ANLIK_FIYAT','SON_FIYAT']
_TYPE_KEYS = ['ADAY_TIPI','EVRE','KARAR','decision','SINYAL','signal','ETIKET','STAGE']
_DATE_KEYS = ['VERI_TARIHI','TARIH','DATE','Date','date']


def _pick(row, keys, default=''):
    for k in keys:
        if k in row and pd.notna(row[k]):
            return row[k]
    return default


def _as_records(result):
    if result is None:
        return []
    if isinstance(result, pd.DataFrame):
        if result.empty:
            return []
        return result.to_dict('records')
    if isinstance(result, dict):
        return [result]
    if isinstance(result, (list, tuple)):
        out=[]
        for x in result:
            if isinstance(x, dict): out.append(x)
            elif hasattr(x,'_asdict'): out.append(dict(x._asdict()))
        return out
    return []


def _symbol(row):
    s=str(_pick(row,_SYMBOL_KEYS,'')).strip().upper().replace('.IS','')
    return s


def _safe_float(v):
    try:
        if v is None or v == '': return ''
        x=float(v)
        if pd.isna(x): return ''
        return round(x,4)
    except Exception:
        return ''


def _data_date(row, fallback):
    v=_pick(row,_DATE_KEYS,'')
    if v == '': return fallback
    try:
        return pd.to_datetime(v).strftime('%Y-%m-%d')
    except Exception:
        return str(v)[:10]


def _compact_detail(row):
    preferred = [
        'ADAY_TIPI','EVRE','ZAMANLAMA_3G','PARA_GIRISI','ERKEN3G_SKOR','V33_SKOR',
        'PATLAMA_PUANI','BIRLESIK_SKOR','PUAN','score','RVOL','VOL_WAKE','RET1','RET3',
        'RET5','TEPKI_%','3G_HEDEF','KISA_NOT','SINYAL','signal','decision','KARAR'
    ]
    d={}
    for k in preferred:
        if k in row and pd.notna(row[k]):
            v=row[k]
            if hasattr(v,'item'):
                try: v=v.item()
                except Exception: pass
            d[k]=v
    try:
        return json.dumps(d, ensure_ascii=False, default=str, separators=(',',':'))[:1200]
    except Exception:
        return ''


def _load_csv(path):
    if not path.exists(): return pd.DataFrame()
    try: return pd.read_csv(path, encoding='utf-8-sig')
    except Exception:
        try: return pd.read_csv(path)
        except Exception: return pd.DataFrame()


def record_scan(engine: str, result=None, source: str='MENU', note: str=''):
    """Her tarama calismasini ve adaylari kalici hafizaya ekler."""
    now=datetime.now(ZoneInfo("Europe/Istanbul"))
    ts=now.strftime('%Y-%m-%d %H:%M:%S')
    day=now.strftime('%Y-%m-%d')
    records=_as_records(result)

    run_id=hashlib.sha1(f'{engine}|{ts}|{len(records)}'.encode('utf-8')).hexdigest()[:12]
    run_row=pd.DataFrame([{
        'RUN_ID':run_id,'TARAMA_ZAMANI':ts,'MOTOR':engine,'KAYNAK':source,
        'ADAY_SAYISI':len(records),'NOT':note,'VERSIYON':VERSION
    }])
    run_path=result_file(RUN_FILE)
    run_old=_load_csv(run_path)
    pd.concat([run_old,run_row],ignore_index=True).to_csv(run_path,index=False,encoding='utf-8-sig')

    norm=[]
    rank=0
    for r in records:
        if not isinstance(r,dict): continue
        sym=_symbol(r)
        if not sym: continue
        rank += 1
        norm.append({
            'RUN_ID':run_id,
            'TARAMA_ZAMANI':ts,
            'VERI_TARIHI':_data_date(r,day),
            'MOTOR':engine,
            'SIRA':rank,
            'HISSE':sym,
            'SKOR':_safe_float(_pick(r,_SCORE_KEYS,'')),
            'FIYAT':_safe_float(_pick(r,_PRICE_KEYS,'')),
            'ADAY_TIPI':str(_pick(r,_TYPE_KEYS,'')),
            'DETAY':_compact_detail(r),
            'GIRIS_DURUMU':str(r.get('GIRIS_DURUMU','')),
            'BALINA_DURUMU':str(r.get('BALINA_DURUMU','')),
            'BALINA_IZI_SKOR':_safe_float(r.get('BALINA_IZI_SKOR')),
            'GIRIS_NEDENI':str(r.get('GIRIS_NEDENI','')),
            'HISSE_BAR_ZAMANI':str(r.get('HISSE_BAR_ZAMANI','')),
            'D1_MAX_%':'','D2_MAX_%':'','D3_MAX_%':'',
            'D1_KAPANIS_%':'','D2_KAPANIS_%':'','D3_KAPANIS_%':'',
            'D3_BASARI':'',
            **{k:_safe_float(r.get(k)) for k in ('H1','H2','H3','YAPI_BOZULMA')},
        })
    if norm:
        mem_path=result_file(MEMORY_FILE)
        old=_load_csv(mem_path)
        all_df=pd.concat([old,pd.DataFrame(norm)],ignore_index=True)
        all_df.to_csv(mem_path,index=False,encoding='utf-8-sig')

        # Gunluk, okunabilir kopya
        daily_dir=results_dir()/'TARAMA_HAFIZASI_GUNLUK'/day
        daily_dir.mkdir(parents=True,exist_ok=True)
        safe=''.join(c if c.isalnum() or c in '-_' else '_' for c in engine)[:60]
        pd.DataFrame(norm).to_csv(daily_dir/f'{now:%H%M%S}_{safe}.csv',index=False,encoding='utf-8-sig')
    return run_id


def search_symbol(symbol: str, limit: int=40):
    sym=str(symbol).strip().upper().replace('.IS','')
    df=_load_csv(result_file(MEMORY_FILE))
    if df.empty or 'HISSE' not in df.columns:
        print('\nTarama hafizasi henuz bos.')
        return pd.DataFrame()
    x=df[df['HISSE'].astype(str).str.upper()==sym].copy()
    if x.empty:
        print(f'\n{sym} icin hafizada kayit yok.')
        return x
    x=x.sort_values(['TARAMA_ZAMANI','MOTOR'],ascending=[False,True]).head(limit)
    cols=[c for c in ['TARAMA_ZAMANI','VERI_TARIHI','MOTOR','SIRA','SKOR','FIYAT','ADAY_TIPI','D3_BASARI'] if c in x.columns]
    print('\n'+'='*115)
    print(f'TARAMA HAFIZASI | {sym} | SON {len(x)} KAYIT')
    print('='*115)
    print(x[cols].to_string(index=False))
    print('='*115)
    return x


def recent(limit: int=50):
    df=_load_csv(result_file(MEMORY_FILE))
    if df.empty:
        print('\nTarama hafizasi henuz bos.')
        return df
    x=df.sort_values(['TARAMA_ZAMANI','SIRA'],ascending=[False,True]).head(limit)
    cols=[c for c in ['TARAMA_ZAMANI','MOTOR','SIRA','HISSE','SKOR','FIYAT','ADAY_TIPI'] if c in x.columns]
    print('\n'+'='*115)
    print(f'TARAMA HAFIZASI | SON {len(x)} ADAY')
    print('='*115)
    print(x[cols].to_string(index=False))
    print('='*115)
    return x


def main():
    print('\nTARAMA HAFIZASI')
    print('[1] Hisse ara (ornek: MRSHL)')
    print('[2] Son 50 aday')
    print('[3] Kalici uyuyan hisse havuzu')
    print('[4] Uyuyan hisse gecis gecmisi')
    ch=input('Secim: ').strip()
    if ch=='1':
        s=input('Hisse: ').strip()
        if s: search_symbol(s)
    elif ch=='2':
        recent(50)
    elif ch=='4':
        from sleeper_pool import history
        symbol=input('Hisse kodu: ').strip()
        if symbol: history(symbol)
    elif ch=='3':
        pool=_load_csv(result_file('UYUYAN_HISSE_KALICI_HAVUZ.csv'))
        if pool.empty: print('Havuz bos; Menu 20 taramasini calistirin.')
        else:
            cols=[k for k in ['HISSE','VERI_TARIHI','ASAMA','HAVUZ_DURUMU','GECIS','ILK_FIYAT','SON_FIYAT','BALINA_DURUMU'] if k in pool]
            print(pool[cols].to_string(index=False))
    else:
        print('Gecersiz secim.')

def snapshot_results():
    snap={}
    root=results_dir()
    for p in root.glob('*.csv'):
        if p.name in {MEMORY_FILE,RUN_FILE}: continue
        try: snap[str(p)]=p.stat().st_mtime_ns
        except Exception: pass
    return snap


def record_changed_csvs(before: dict, engine_prefix: str='OTOMATIK'):
    """Bir ust otomasyonun uretdigi yeni/degisen CSV'leri hafizaya indeksler."""
    root=results_dir(); count=0
    for p in root.glob('*.csv'):
        if p.name in {MEMORY_FILE,RUN_FILE}: continue
        try: mt=p.stat().st_mtime_ns
        except Exception: continue
        if before.get(str(p)) == mt: continue
        try:
            df=pd.read_csv(p,encoding='utf-8-sig')
        except Exception:
            try: df=pd.read_csv(p)
            except Exception: continue
        # Performans/ozet dosyalarinda hisse yoksa sadece atla.
        cols={str(c).lower() for c in df.columns}
        if not any(k.lower() in cols for k in _SYMBOL_KEYS):
            continue
        record_scan(f'{engine_prefix}:{p.stem}',df,source='CSV_AUTO',note=str(p.name))
        count += 1
    return count
