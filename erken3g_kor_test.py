from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import yfinance as yf

from symbols import get_bist_symbols
from v19_paths import result_file
import erken3g_havuz as e3

IST = ZoneInfo('Europe/Istanbul')
VERSION = 'ERKEN-3G-KOR-TEST-V3-FIX19'
# FIX19: historical feature parity with live FIX17 + full Sep reference window
DOWNLOAD_START = '2025-01-01'
TEST_START = pd.Timestamp('2026-06-01')
TEST_END = pd.Timestamp('2026-09-10')  # Sep10 reference signals included; D+3 needs data through Sep15
DOWNLOAD_END = '2026-09-16'


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
    x.index = idx.normalize()
    return x[~x.index.duplicated(keep='last')].sort_index()


def _features_hist(d):
    return e3._features(_flat(d),completed=True)


def _download_all(download_start=DOWNLOAD_START, download_end=DOWNLOAD_END):
    syms = get_bist_symbols()
    raw, feat = {}, {}
    print(f'\n{VERSION} | veri indiriliyor...')
    for i,s in enumerate(syms,1):
        print(f'\r[{i}/{len(syms)}] {s:<14}',end='',flush=True)
        try:
            d = yf.download(s,start=download_start,end=download_end,interval='1d',auto_adjust=False,
                            progress=False,threads=False,timeout=15)
            d = _flat(d)
            if len(d) >= 140:
                raw[s] = d
                feat[s] = _features_hist(d)
        except Exception:
            pass
    print()
    return raw, feat


def _forward3(rd, signal_day, all_days):
    if signal_day not in all_days or signal_day not in rd.index:
        return None
    pos = all_days.index(signal_day)
    future_market_days = all_days[pos+1:pos+4]
    future = [d for d in future_market_days if d in rd.index]
    if len(future_market_days) != 3 or len(future) != 3:
        return None
    entry = float(rd.loc[signal_day,'Close'])
    if not np.isfinite(entry) or entry <= 0:
        return None
    max_high = -999.0; max_close = -999.0; min_low = 999.0
    first5 = first7 = first95 = None
    day_rows=[]
    for k,d in enumerate(future,1):
        high=float(rd.loc[d,'High']); low=float(rd.loc[d,'Low']); close=float(rd.loc[d,'Close'])
        rh=(high/entry-1)*100; rl=(low/entry-1)*100; rc=(close/entry-1)*100
        max_high=max(max_high,rh); max_close=max(max_close,rc); min_low=min(min_low,rl)
        if first5 is None and rh >= 5.0: first5=k
        if first7 is None and rh >= 7.0: first7=k
        if first95 is None and rh >= 9.5: first95=k
        day_rows.append((k,d,rh,rc))
    return {
        'D3_MAX_HIGH_%':max_high,'D3_MAX_CLOSE_%':max_close,'D3_MAE_%':min_low,
        'D3_5PLUS':max_high>=5.0,'D3_7PLUS':max_high>=7.0,'D3_9_5PLUS':max_high>=9.5,
        'ILK_5_GUN':first5,'ILK_7_GUN':first7,'ILK_9_5_GUN':first95,
        'D1_HIGH_%':day_rows[0][2] if len(day_rows)>0 else np.nan,
        'D2_HIGH_%':day_rows[1][2] if len(day_rows)>1 else np.nan,
        'D3_HIGH_%':day_rows[2][2] if len(day_rows)>2 else np.nan,
    }


def test_window(start, end):
    start=pd.Timestamp(start).normalize(); end=pd.Timestamp(end).normalize()
    today=pd.Timestamp(datetime.now(IST).date())
    if start > end or end >= today:
        raise ValueError('Baslangic bitisten sonra olamaz; bitis bugunden once olmali.')
    return start,end,(start-pd.Timedelta(days=550)).strftime('%Y-%m-%d'),min(end+pd.Timedelta(days=30),today).strftime('%Y-%m-%d')


def main(start=None, end=None):
    if start is None:
        start=input('Baslangic YYYY-AA-GG [2026-06-01]: ').strip() or '2026-06-01'
    if end is None:
        end=input('Bitis YYYY-AA-GG [2026-09-10]: ').strip() or '2026-09-10'
    test_start,test_end,download_start,download_end=test_window(start,end)
    raw, feat = _download_all(download_start,download_end)
    if not raw:
        print('Veri indirilemedi.')
        return
    market=_flat(yf.download('XU100.IS',start=download_start,end=download_end,interval='1d',auto_adjust=False,progress=False,threads=False,timeout=15))
    if market.empty:
        raise RuntimeError('XU100 seans verisi yok; kor test yapilamadi.')
    all_days=list(market.index)
    signal_days = [d for d in all_days if test_start <= d <= test_end and all_days.index(d)+3 < len(all_days)]
    detail=[]; daily=[]; excluded=[]

    print('\n'+'='*118)
    print('ERKEN-3G KOR TEST | SADECE SINYAL GUNUNE KADAR VERI | BASARI = D+1/D+2/D+3')
    print('='*118)
    for day in signal_days:
        scored=[]
        for s,f in feat.items():
            if day not in f.index or day not in raw[s].index:
                continue
            try:
                rec=e3._score(f.loc[:day])
                if rec:
                    rec=dict(rec); rec['HISSE']=s.replace('.IS',''); rec['SINYAL_GUNU']=day.strftime('%Y-%m-%d')
                    scored.append(rec)
            except Exception:
                pass
        if not scored:
            continue
        df=pd.DataFrame(scored).sort_values(
            ['ERKEN3G_SKOR','ZAMANLAMA_3G','PARA_GIRISI','RVOL'],ascending=False
        ).head(10).copy()
        rows=[]
        for _,r in df.iterrows():
            s=r['HISSE']+'.IS'
            fw=_forward3(raw[s],day,all_days)
            if fw is None:
                excluded.append({'HISSE':r['HISSE'],'SINYAL_GUNU':str(day.date()),'DURUM':'UC_SEANS_VERISI_EKSIK'})
                continue
            row=r.to_dict(); row.update(fw); rows.append(row); detail.append(row)
        if not rows: continue
        z=pd.DataFrame(rows)
        d5=int(z.D3_5PLUS.sum()); d7=int(z.D3_7PLUS.sum()); d95=int(z.D3_9_5PLUS.sum())
        daily.append({'SINYAL_GUNU':day.strftime('%Y-%m-%d'),'TOP10':len(z),'D3_5PLUS':d5,'D3_7PLUS':d7,'D3_9_5PLUS':d95,
                      'ORT_MAX_HIGH_%':float(z['D3_MAX_HIGH_%'].mean()),'ORT_MAE_%':float(z['D3_MAE_%'].mean())})
        print(f'{day:%d.%m} | Top10:{len(z):2d} | D+1..3 +5:{d5:2d} | +7:{d7:2d} | +9.5:{d95:2d} | ort.max %{z["D3_MAX_HIGH_%"].mean():5.2f}')

    det=pd.DataFrame(detail); daydf=pd.DataFrame(daily)
    print('\n'+'='*118)
    print('GENEL SONUC')
    print('='*118)
    if det.empty:
        pd.DataFrame(excluded,columns=['HISSE','SINYAL_GUNU','DURUM']).to_csv(result_file('ERKEN3G_KOR_TEST_EKSIK.csv'),index=False,encoding='utf-8-sig')
        print('Aday olusmadi / ileri veri yok.')
        return
    print(f'Eksik 3 seans nedeniyle olcum disi: {len(excluded)}')
    n=len(det)
    print(f'Toplam aday-gun        : {n}')
    print(f'D+1..D+3 >= +5%%       : {int(det.D3_5PLUS.sum())}  (%{100*det.D3_5PLUS.mean():.2f})')
    print(f'D+1..D+3 >= +7%%       : {int(det.D3_7PLUS.sum())}  (%{100*det.D3_7PLUS.mean():.2f})')
    print(f'D+1..D+3 >= +9.5%%     : {int(det.D3_9_5PLUS.sum())}  (%{100*det.D3_9_5PLUS.mean():.2f})')
    print(f'Ort. 3 gun max hareket : %{det["D3_MAX_HIGH_%"].mean():.2f}')
    print(f'Ort. 3 gun MAE         : %{det["D3_MAE_%"].mean():.2f}')

    # Hangi patern zamanlamada daha iyi?
    grp=det.groupby('ADAY_TIPI').agg(
        N=('HISSE','size'),
        PLUS5=('D3_5PLUS','mean'), PLUS7=('D3_7PLUS','mean'), PLUS95=('D3_9_5PLUS','mean'),
        AVG_MAX=('D3_MAX_HIGH_%','mean'), AVG_MAE=('D3_MAE_%','mean')
    ).sort_values('PLUS7',ascending=False)
    print('\nPATERN BAZINDA:')
    for typ,r in grp.iterrows():
        print(f'{typ:<20} n={int(r.N):4d} | +5 %{100*r.PLUS5:5.1f} | +7 %{100*r.PLUS7:5.1f} | +9.5 %{100*r.PLUS95:5.1f} | max %{r.AVG_MAX:5.2f}')

    # Kullanici tarafindan verilen referanslar. Bunlar optimizasyon icin DEGIL,
    # gercek kor testte hareket ONCESINDE yakalandi mi diye raporlama icindir.
    # target_day = hareketten once / ilk uyanis gunu olarak kabul edilen kontrol tarihi.
    references = {
        'MIATK':['2026-09-03'],
        'SUWEN':['2026-09-01'],
        'YKSLN':['2026-09-04'],
        'KZGYO':['2026-09-02'],
        'KARSN':['2026-08-27','2026-08-28'],
        'HALKB':['2026-08-25','2026-09-01'],
        'GIPTA':['2026-08-24','2026-08-25'],
        'ENERY':['2026-08-24','2026-08-25','2026-09-03'],
        'EGEEN':['2026-09-03','2026-09-07'],
        'PATEK':['2026-09-07','2026-09-09'],
        'KRDMD':['2026-09-03','2026-09-04'],
        'KORDS':['2026-09-03','2026-09-04'],
        'TCELL':['2026-09-03','2026-09-04'],
        'TKFEN':['2026-09-03','2026-09-04'],
        'RYSAS':['2026-08-26','2026-08-27'],
        'GRNYO':['2026-09-09'],
        'MOGAN':['2026-09-09','2026-09-10'],
        'AHSGY':['2026-09-08','2026-09-09'],
        'TSPOR':['2026-09-09','2026-09-10'],
        'TNZTP':['2026-09-07','2026-09-08'],
        'TTKOM':['2026-09-03','2026-09-04'],
    }
    print('\nREFERANS KOR KONTROLU (hareketten once / ilk uyanista Top10):')
    ref_rows=[]
    for sym, dates in references.items():
        if not all(test_start <= pd.Timestamp(ds) <= test_end for ds in dates):
            continue
        hits=[]
        for ds in dates:
            q=det[(det.HISSE==sym)&(det.SINYAL_GUNU==ds)]
            if not q.empty:
                r=q.iloc[0]
                hits.append((ds,r))
        if hits:
            ds,r=hits[0]
            # Ilk hedef tarihte bulunursa YAKALADI, sonraki alternatif tarihte bulunursa SINIRDA.
            status='YAKALADI' if ds==dates[0] else 'SINIRDA'
            print(f'{sym:<6} {status:<8} | {ds} | skor {r.ERKEN3G_SKOR:.1f} | {r.ADAY_TIPI:<20} | D3 max %{r["D3_MAX_HIGH_%"]:.2f}')
            ref_rows.append({'HISSE':sym,'DURUM':status,'SINYAL_GUNU':ds,'SKOR':r.ERKEN3G_SKOR,'ADAY_TIPI':r.ADAY_TIPI,'D3_MAX_HIGH_%':r['D3_MAX_HIGH_%']})
        else:
            print(f'{sym:<6} KACIRDI  | hedef gunlerde Top10 yok')
            ref_rows.append({'HISSE':sym,'DURUM':'KACIRDI','SINYAL_GUNU':'','SKOR':np.nan,'ADAY_TIPI':'','D3_MAX_HIGH_%':np.nan})

    refdf=pd.DataFrame(ref_rows)
    if not refdf.empty:
        yak=int((refdf.DURUM=='YAKALADI').sum()); sin=int((refdf.DURUM=='SINIRDA').sum()); kac=int((refdf.DURUM=='KACIRDI').sum())
        print(f'\nREFERANS OZET | YAKALADI {yak} | SINIRDA {sin} | KACIRDI {kac} | TAM BASARI %{100*yak/len(refdf):.1f}')

    now=datetime.now(IST)
    p1=result_file(f'ERKEN3G_KOR_TEST_GUNLUK_{now:%Y%m%d_%H%M}.csv')
    p2=result_file(f'ERKEN3G_KOR_TEST_TOP10_DETAY_{now:%Y%m%d_%H%M}.csv')
    pd.DataFrame(excluded,columns=['HISSE','SINYAL_GUNU','DURUM']).to_csv(result_file(f'ERKEN3G_KOR_TEST_EKSIK_{now:%Y%m%d_%H%M}.csv'),index=False,encoding='utf-8-sig')
    grp.to_csv(result_file(f'ERKEN3G_KOR_TEST_PATERN_{now:%Y%m%d_%H%M}.csv'),encoding='utf-8-sig')
    daydf.to_csv(p1,index=False,encoding='utf-8-sig')
    det.to_csv(p2,index=False,encoding='utf-8-sig')
    p3=result_file(f'ERKEN3G_REFERANS_KOR_TEST_{now:%Y%m%d_%H%M}.csv')
    try:
        refdf.to_csv(p3,index=False,encoding='utf-8-sig')
    except Exception:
        pass
    print(f'\nKayit: {p1}')
    print(f'Kayit: {p2}')
    print(f'Kayit: {p3}')

if __name__=='__main__':
    main()
