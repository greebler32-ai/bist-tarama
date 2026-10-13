from pathlib import Path
from datetime import date,timedelta
import os,uuid,hmac,re,io,zipfile
import pandas as pd
import streamlit as st
from web_catalog import SCANS,TIMEFRAMES
from web_jobs import Jobs
from result_view import trade_view

st.set_page_config(page_title='BIST · Sinyal Atölyesi',page_icon='📈',layout='wide')
st.markdown('''<style>
.stApp{background:#f5f7fb} .block-container{max-width:1400px;padding-top:2rem}
h1{letter-spacing:-1.6px} [data-testid="stMetric"]{background:white;border:1px solid #e3e8ef;border-radius:14px;padding:18px}
[data-testid="stSidebar"]{background:#fff}
textarea{white-space:pre-wrap!important;overflow-wrap:anywhere!important;overflow-x:hidden!important} .hero{padding:24px;border-radius:20px;background:#0c2139;color:#fff;margin-bottom:24px}
.hero p{color:#b7cbe0;margin-bottom:0} .hero h2{color:#fff;margin:0 0 8px;font-size:26px}
</style>''',unsafe_allow_html=True)

def secret(name):
    try:return str(st.secrets.get(name,os.environ.get(name,'')))
    except Exception:return os.environ.get(name,'')

@st.cache_resource
def manager():return Jobs()
jobs=manager()
if 'owner' not in st.session_state:st.session_state.owner=uuid.uuid4().hex
owner=st.session_state.owner
with st.sidebar:
    st.title('📈 BIST Atölyesi')
    st.caption('Tüm motorlar · WEB 1.0')
    group=st.selectbox('Tarama grubu',['Tümü','Günlük','Canlı','Temel','Test','iTick','Kayıtlar','Otomatik'])
    choices=[n for n,(title,g) in SCANS.items() if group=='Tümü' or group==g]
    scan=st.selectbox('Tarama',choices,format_func=lambda n:f'{n:02d} · {SCANS[n][0]}',index=choices.index(9) if 9 in choices else 0)
    st.divider()
    with st.expander('Yönetici kontrolleri'):
        code=st.text_input('Yönetici kodu',type='password')
        expected=secret('ADMIN_ACCESS_CODE')
        admin=bool(expected and code and hmac.compare_digest(code,expected))
        st.caption('iTick ve otomatik plan yönetimi sunucu sahibi içindir.')
        if admin:
            st.success('Yönetici erişimi açık')
            if st.button('Otomatik 20 seans planını başlat'):jobs.auto=True
            if st.button('Otomatik planı durdur'):jobs.auto=False
        elif code:st.error('Yönetici kodu geçersiz veya sunucuda tanımlanmamış.')
    st.caption('Veri: Yahoo gecikmeli OHLCV · iTick sunucu anahtarıyla')

st.markdown('<div class="hero"><h2>Hazırlığı gör. Teyidi bekle. Sonucu ölç.</h2><p>Günlük Top10, uyuyan hisseler, balina izi ve tüm tarama motorları tek yerde.</p></div>',unsafe_allow_html=True)
a,b,c=st.columns(3)
a.metric('Tarama seçenekleri','28')
b.metric('Bekleyen işler',str(sum(j['state']=='Sirada' for j in list(jobs.items.values()))))
c.metric('Otomatik plan','Açık' if jobs.auto else 'Kapalı')
st.subheader(SCANS[scan][0])
st.caption('Sonuçlar ortak sunucuda kaydedilir. Balina izi fiyat-hacim yorumudur; kurum kimliği veya otomatik işlem değildir.')
params={'scan':scan}
with st.container(border=True):
    if scan<=8:
        label=st.selectbox('Mum periyodu',list(TIMEFRAMES),index=1);params['tf']=TIMEFRAMES[label]
    if scan in (19,21):
        d1,d2=st.columns(2)
        start=d1.date_input('Başlangıç',date(2026,4,1),max_value=date.today()-timedelta(days=1))
        end=d2.date_input('Bitiş',date(2026,8,31),max_value=date.today()-timedelta(days=1))
        params.update(start=start.isoformat(),end=end.isoformat())
        st.caption('Sadece sinyal anına kadar veri kullanılır. Veri indirme uzun sürebilir.')
    if scan==24:params['symbol']=st.text_input('Hisse kodu (boş bırakırsan son kayıtlar)','').strip().upper()
    if scan==16:st.info('Bu düğme tüm motorları bir kez çalıştırır. Saatli 20 seans planı yönetici bölümünden açılır; sunucu açık kalmalıdır.')
    if scan in (17,23):st.info('iTick canlı takibi en fazla 30 dakika çalışır. Sunucuda anahtar ve yönetici erişimi gerekir.')
    allowed=scan not in (16,17,23,25) or admin
    if not allowed:st.caption('Bu işlem için yönetici erişimi gerekir.')
    if st.button('Taramayı başlat',type='primary',disabled=not allowed,use_container_width=True):
        try:
            if scan in (19,21) and start>end:raise ValueError('Başlangıç tarihi bitişten sonra olamaz.')
            env={}
            if scan in (17,23):
                key=secret('ITICK_KEY')
                if not key:raise ValueError('Sunucuda iTick anahtarı tanımlı değil.')
                env['ITICK_KEY']=key
            st.session_state.job=jobs.submit(params,owner,env)
            st.success('Tarama sıraya alındı.')
        except Exception as exc:st.error(str(exc))

@st.fragment(run_every=3)
def status():
    jid=st.session_state.get('job')
    if not jid:
        st.info('Bir tarama seçip başlat. Sonuçlar burada görünecek.');return
    job=jobs.get(jid)
    if not job:st.warning('Bu iş artık listede yok.');return
    st.subheader('Tarama durumu')
    state=job['state'];st.write({'Sirada':'⏳ Sırada','Calisiyor':'🔄 Çalışıyor','Tamamlandi':'✅ Tamamlandı','Hata':'⚠️ Hata','Durduruldu':'⏹ Durduruldu','Sure doldu':'⌛ Süre doldu'}.get(state,state))
    if state in ('Sirada','Calisiyor') and st.button('Bu taramayı durdur',key='stop'):
        jobs.cancel(jid,owner,admin);st.rerun(scope='fragment')
    text=jobs.log(jid);text=re.sub(r'\x1b\[[0-9;?]*[A-Za-z]','',text)
    if state=='Hata':st.error(job.get('error','Tarama tamamlanamadı. Veri sağlayıcı mesajını kontrol et.'))
    if state=='Calisiyor':
        st.status('Tarama devam ediyor · durum 3 saniyede bir yenilenir',state='running',expanded=True)
    elif state=='Sirada':
        st.info('Taraman sırada. Başladığında işlem adımları aşağıda görünecek.')
    # Terminal satirlarini dikey, okunabilir gunluk olarak goster.
    log_lines=[line.strip() for line in text.replace('\r','\n').splitlines() if line.strip()]
    readable='\n'.join(log_lines[-80:]) or 'Tarama adımları burada görünecek...'
    st.text_area('Tarama ilerlemesi',value=readable,height=360,disabled=True,key=f'log_{jid}')
    files=job.get('files',[])
    if files:
        selected=st.selectbox('Sonuç dosyası',files,format_func=lambda p:p.name,key=f'file_{jid}')
        try:
            df=pd.read_csv(selected,encoding='utf-8-sig')
            shown=trade_view(df) if any(c in df for c in ['HISSE','symbol','SYMBOL','Sembol','ticker']) else df
            st.dataframe(shown,use_container_width=True,hide_index=True)
            if 'Hedef Fiyatı' in shown and (shown['Hedef Fiyatı'].isna().any() or shown['Stop Loss'].isna().any()):
                st.caption('Hedef veya stop üretmeyen motorlarda ilgili alan boş kalır.')
            st.download_button('CSV indir',shown.to_csv(index=False).encode('utf-8-sig'),file_name=selected.name,mime='text/csv',key=f'csv_{jid}')
        except (pd.errors.EmptyDataError,UnicodeError):st.info('Bu dosyada satır bulunmuyor.')
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
            for p in files:
                try:
                    table=pd.read_csv(p,encoding='utf-8-sig')
                    if any(c in table for c in ['HISSE','symbol','SYMBOL','Sembol','ticker']):table=trade_view(table)
                    z.writestr(p.name,table.to_csv(index=False).encode('utf-8-sig'))
                except pd.errors.EmptyDataError:z.writestr(p.name,p.read_bytes())
        st.download_button('Tüm sonuçları ZIP indir',buf.getvalue(),file_name='bist_sonuclar.zip',mime='application/zip',key=f'zip_{jid}')
status()
with st.expander('Ortak kayıtlar · Uyuyan havuzu ve geçiş geçmişi'):
    root=Path(__file__).parent/'web_data'/'results'
    names=['UYUYAN_HISSE_KALICI_HAVUZ.csv','UYUYAN_HISSE_GECIS_GECMISI.csv','TARAMA_HAFIZASI.csv','MOTOR_PATERN_BASARI_OZETI.csv']
    name=st.selectbox('Kayıt',names)
    p=root/name
    if p.exists():
        try:
            df=pd.read_csv(p,encoding='utf-8-sig');symbol=st.text_input('Hisseye göre filtrele',key='filter')
            if symbol and 'HISSE' in df:df=df[df.HISSE.astype(str).str.contains(symbol.upper(),regex=False)]
            st.dataframe(df.tail(500),use_container_width=True,hide_index=True)
            st.download_button('Kaydı indir',df.to_csv(index=False).encode('utf-8-sig'),file_name=name)
        except pd.errors.EmptyDataError:st.info('Kayıt boş.')
    else:st.caption('İlk taramadan sonra oluşur.')
st.caption('Veri sağlayıcı sınırları taramayı engelleyebilir. Ön bellekte günlük veriler 15 dakika, gün içi veriler 1 dakika saklanır. Yazılım testleri piyasa başarı oranı değildir.')
