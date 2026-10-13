"""Tarama hafizasinin sonraki uc piyasa seansini degerlendirir."""
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
from v19_paths import result_file


def evaluate(row, bars, sessions):
    out = {}
    stamp = pd.Timestamp(row['TARAMA_ZAMANI'])
    day = stamp.normalize()
    price = pd.to_numeric(row.get('FIYAT'), errors='coerce')
    if pd.isna(price) or not np.isfinite(price) or price <= 0:
        return {'SONUC_DURUMU': 'GIRIS_EKSIK'}
    days = [pd.Timestamp(d).normalize() for d in sessions if pd.Timestamp(d).normalize() > day][:3]
    missing = False
    for k, d in enumerate(days, 1):
        if d not in bars.index:
            missing = True
            continue
        b = bars.loc[d]
        if any(not np.isfinite(pd.to_numeric(b.get(k),errors='coerce')) for k in ('High','Low','Close')):
            missing=True
            continue
        out[f'D{k}_MAX_%'] = round((float(b.High)/price-1)*100, 4)
        out[f'D{k}_KAPANIS_%'] = round((float(b.Close)/price-1)*100, 4)
        out[f'D{k}_MIN_%'] = round((float(b.Low)/price-1)*100, 4)
    complete = len(days) == 3 and not missing
    out['SONUC_DURUMU'] = 'TAMAMLANDI' if complete else 'VERI_EKSIK' if missing else 'BEKLIYOR'
    out['D3_BASARI'] = ('EVET' if max(out[f'D{k}_MAX_%'] for k in (1,2,3)) >= 5 else 'HAYIR') if complete else ''
    out['OLCUM_TURU'] = 'SONRAKI_3_SEANS_FIYAT_HAREKETI'
    return out


def _daily(symbol, start, end):
    import yfinance as yf
    x = yf.download(symbol, start=start, end=end, auto_adjust=False, progress=False, threads=False, timeout=20)
    if x is None or x.empty: return pd.DataFrame()
    if isinstance(x.columns, pd.MultiIndex):
        x.columns = x.columns.get_level_values(0)
    idx=pd.DatetimeIndex(x.index)
    if idx.tz is not None: idx=idx.tz_convert("Europe/Istanbul").tz_localize(None)
    x.index=idx.normalize()
    x=x[~x.index.duplicated(keep="last")].sort_index()
    return x


def main():
    path = result_file('TARAMA_HAFIZASI.csv')
    if not path.exists():
        print('Tarama hafizasi bos.'); return
    df = pd.read_csv(path, encoding='utf-8-sig')
    if df.empty: return
    start = pd.to_datetime(df.TARAMA_ZAMANI).min().strftime('%Y-%m-%d')
    # Bugunun tamamlanmamis gunluk mumunu olcume katma.
    end = datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%Y-%m-%d')
    market = _daily('XU100.IS', start, end)
    if market.empty: raise RuntimeError('Piyasa seans verisi alinamadi; hafiza degistirilmedi.')
    cache = {}; errors = []
    for idx, row in df.iterrows():
        if 'KOR_TEST' in str(row.MOTOR): continue
        sym = str(row.HISSE).upper().removesuffix('.IS') + '.IS'
        try:
            if sym not in cache: cache[sym] = _daily(sym, start, end)
            if cache[sym].empty: raise ValueError('Hisse verisi bos')
            values = evaluate(row, cache[sym], market.index)
            if pd.notna(row.get('H1')):
                from target_tracking import evaluate_targets
                values.update(evaluate_targets(row, cache[sym],market.index))
            for key, value in values.items():
                if key not in df: df[key] = pd.Series('', index=df.index, dtype=object)
                df[key] = df[key].astype(object)
                df.at[idx,key] = value
        except Exception as exc:
            errors.append(f'{sym}: {exc}')
    pd.DataFrame({'HATA':sorted(set(errors))}).to_csv(result_file('HAFIZA_SONUC_VERI_HATALARI.csv'),index=False,encoding='utf-8-sig')
    backup = path.with_suffix('.onceki.csv')
    backup.write_bytes(path.read_bytes())
    temp = path.with_suffix('.tmp')
    df.to_csv(temp, index=False, encoding='utf-8-sig'); temp.replace(path)
    print('Hafiza sonuc guncellemesi tamamlandi. D3 basari = ilk 3 seansta en az %5 yuksek fiyat hareketi; gerceklesmis islem kari degildir.')
    for e in sorted(set(errors)): print('VERI HATASI:', e)
