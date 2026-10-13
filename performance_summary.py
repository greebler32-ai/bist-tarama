"""Hafiza sonuc ozeti; tekrar taramalari ayri basari gibi saymaz."""
import pandas as pd
from v19_paths import result_file


def summarise(df):
    x=df.copy()
    if x.empty:return pd.DataFrame()
    x=x[~x.MOTOR.astype(str).str.contains('KOR_TEST',regex=False)].copy()
    x['SINYAL_GUNU']=pd.to_datetime(x.TARAMA_ZAMANI).dt.strftime('%Y-%m-%d')
    x=x.sort_values('TARAMA_ZAMANI').drop_duplicates(['SINYAL_GUNU','MOTOR','HISSE'],keep='first')
    rows=[]
    for (motor,typ),g in x.groupby(['MOTOR','ADAY_TIPI'],dropna=False):
        complete=g[g.get('SONUC_DURUMU',pd.Series('',index=g.index))=='TAMAMLANDI']
        high=pd.to_numeric(complete.get('D3_MAX_%',pd.Series(dtype=float)),errors='coerce')
        # D1..D3 icindeki en yuksek hareket; yalniz D3 gunu degil.
        values=complete.reindex(columns=['D1_MAX_%','D2_MAX_%','D3_MAX_%']).apply(pd.to_numeric,errors='coerce').max(axis=1)
        close=pd.to_numeric(complete.get('D3_KAPANIS_%',pd.Series(dtype=float)),errors='coerce')
        rows.append({'MOTOR':motor,'ADAY_TIPI':typ,'BENZERSIZ_ADAY_GUN':len(g),'TAMAMLANAN':len(complete),'BEKLEYEN_EKSIK':len(g)-len(complete),'UC_SEANS_5PLUS_%':round(100*(values>=5).mean(),2) if len(complete) else None,'UC_SEANS_7PLUS_%':round(100*(values>=7).mean(),2) if len(complete) else None,'ORT_D3_KAPANIS_%':round(close.mean(),2) if len(complete) else None})
    return pd.DataFrame(rows)


def main():
    p=result_file('TARAMA_HAFIZASI.csv')
    if not p.exists(): print('Hafiza bos.');return
    df=summarise(pd.read_csv(p,encoding='utf-8-sig'))
    df.to_csv(result_file('MOTOR_PATERN_BASARI_OZETI.csv'),index=False,encoding='utf-8-sig')
    print('Ilk gunluk kayit esas alinir. Once Menu 25 ile sonuclari guncelleyin.')
    print('Dagitim izi icin yukselis orani alim basarisi degildir; tipler ayri gosterilir.')
    print(df.to_string(index=False))
    return df
