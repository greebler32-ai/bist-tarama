from pathlib import Path
from datetime import date,timedelta
import os,uuid,hmac,re,io,zipfile
import pandas as pd
import streamlit as st
from web_catalog import SCANS,TOOLS,ALL_SCANS,GUIDES,guide_markdown
from web_jobs import Jobs
from result_view import trade_view
from file_views import show_frame,result_kind,sort_files

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
    st.caption('Günlük ve canlı taramalar · WEB 8')
    area=st.radio('Bölüm',['Günlük taramalar','Canlı taramalar','Test ve takip araçları'])
    catalog={n:v for n,v in SCANS.items() if v[1]==('Günlük' if area=='Günlük taramalar' else 'Canlı')} if area!='Test ve takip araçları' else TOOLS
    choices=list(catalog)
    scan=st.selectbox('Tarama',choices,format_func=lambda n:catalog[n][0])
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
a.metric('Ana taramalar',str(len(SCANS)))
b.metric('Bekleyen işler',str(sum(j['state']=='Sirada' for j in list(jobs.items.values()))))
c.metric('Otomatik plan','Açık' if jobs.auto else 'Kapalı')
st.subheader(ALL_SCANS[scan][0])
with st.expander('Bu tarama ne yapar?',expanded=True):
    purpose,data,reading,when=GUIDES[scan]
    st.write('**Ne arar?** '+purpose)
    st.write('**Kullandığı veri:** '+data)
    st.write('**Sonucu nasıl okuyacağım?** '+reading)
    st.write('**Ne zaman kullanılır?** '+when)
with st.expander('Tüm taramaların kılavuzu'):
    for key,(title,_) in ALL_SCANS.items():
        st.markdown('**'+title+'** — '+GUIDES[key][0])
    st.download_button('Kılavuzu indir',guide_markdown().encode('utf-8'),file_name='BIST_TARAMA_KILAVUZU.md',mime='text/markdown')
st.caption('Sonuçlar ortak sunucuda kaydedilir. Balina izi fiyat-hacim yorumudur; kurum kimliği veya otomatik işlem değildir.')
params={'scan':scan}
with st.container(border=True):
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
    state=job['state'];st.write({'Sirada':'⏳ Sırada','Calisiyor':'🔄 Çalışıyor','Tamamlandi':'✅ Tamamlandı','Kismi':'⚠️ Kısmi sonuç · bazı veriler alınamadı','Veri alinamadi':'⛔ Veri alınamadı · tarama doğrulanamadı','Hata':'⚠️ Hata','Durduruldu':'⏹ Durduruldu','Sure doldu':'⌛ Süre doldu'}.get(state,state))
    if state in ('Sirada','Calisiyor') and st.button('Bu taramayı durdur',key='stop'):
        jobs.cancel(jid,owner,admin);st.rerun(scope='fragment')
    text=jobs.log(jid);text=re.sub(r'\x1b\[[0-9;?]*[A-Za-z]','',text)
    report=job.get('report',{})
    if state=='Calisiyor':
        try:report=__import__('json').loads((job['folder']/'veri_durumu.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):pass
    if report.get('istek'):
        st.caption(f"Veri isteği: {report['istek']} · Veri alınan: {report['basarili']} · Alınamayan: {report['basarisiz']} · Önbellek: {report['onbellek']}")
    if state=='Veri alinamadi':st.error('Hiç kullanılabilir kapanış verisi alınamadı. Bu sonuç aday yok demek değildir. Veri hata raporunu kontrol et.')
    elif state=='Kismi':st.warning('Liste eksik veriyle üretildi; tüm hisse evreninin tarandığı kabul edilemez.')
    if state=='Hata':st.error(job.get('error','Tarama tamamlanamadı. Veri sağlayıcı mesajını kontrol et.'))
    if state=='Calisiyor':
        st.status('Tarama devam ediyor · durum 3 saniyede bir yenilenir',state='running',expanded=True)
    elif state=='Sirada':
        st.info('Taraman sırada. Başladığında işlem adımları aşağıda görünecek.')
    # Terminal satirlarini dikey, okunabilir gunluk olarak goster.
    log_lines=[line.strip() for line in text.replace('\r','\n').splitlines() if line.strip()]
    readable='\n'.join(log_lines[-80:]) or 'Tarama adımları burada görünecek...'
    st.text_area('Tarama ilerlemesi',value=readable,height=360,disabled=True,key=f'log_{jid}')
    files=sort_files(job.get('files',[]))
    if files:
        error_rows=0
        for error_file in files:
            if result_kind(pd.DataFrame(),error_file)=='error':
                try:error_rows+=len(pd.read_csv(error_file))
                except pd.errors.EmptyDataError:pass
        if error_rows:st.warning(f'{error_rows} veri sorunu kaydı var. Hata raporlarını sonuç dosyası kutusundan açabilirsin; veri alınamayan hisseler başarı sayılmaz.')
        selected=st.selectbox('Sonuç dosyası',files,format_func=lambda p:p.name,key=f'file_{jid}')
        try:
            df=pd.read_csv(selected,encoding='utf-8-sig')
            shown=show_frame(df,selected)
            kind=result_kind(df,selected)
            if kind=='error':st.warning('Bu dosya veri hata raporudur; aday listesi değildir.')
            elif df.empty and kind!='error':
                if state=='Veri alinamadi':st.info('Veri olmadığı için aday seçimi yapılamadı.')
                elif state=='Kismi':st.info('Alınabilen verilerde aday yok; eksik veriler nedeniyle sonuç kısmi.')
                else:st.info('Bu sonuç dosyasında aday veya kayıt yok.')
            if 'VERI_TARIHI' in df:
                dates=sorted(df['VERI_TARIHI'].dropna().astype(str).unique())
                st.caption('Kullanılan kapanış tarihi: '+', '.join(dates))
                from datetime import datetime
                from zoneinfo import ZoneInfo
                now=datetime.now(ZoneInfo('Europe/Istanbul'))
                expected=pd.Timestamp(now.date()) if (now.hour,now.minute)>=(18,10) else pd.Timestamp(now.date())-pd.offsets.BDay(1)
                if dates and pd.to_datetime(dates[-1])<expected:
                    st.warning('Son veri beklenen hafta içi kapanışından eski. Tatil veya sağlayıcı gecikmesi olabilir; listeyi bugünün güncel adayı olarak değerlendirme.')
            if 'GIRIS_TURU' in df and (df.GIRIS_TURU=='SON_TAMAMLANMIS_KAPANIS').any():
                st.caption('Giriş son kapanış referansıdır. Hedef: eski direnç veya 2 ATR; stop: son 5 mum dip yapısı altında ATR payı. Gerçekleşmiş işlem veya tavan garantisi değildir.')
            st.dataframe(shown,use_container_width=True,hide_index=True)
            if 'Hedef Fiyatı' in shown and ((shown['Hedef Fiyatı']=='—').any() or (shown['Stop Loss']=='—').any()):
                st.caption('—: Bu satır için teknik plan üretilmemiş. Dağıtım izinde alım hedefi verilmez; eski dosyalar için yeni tarama gerekir.')
            st.download_button('CSV indir',shown.to_csv(index=False).encode('utf-8-sig'),file_name=selected.name,mime='text/csv',key=f'csv_{jid}')
        except (pd.errors.EmptyDataError,UnicodeError):st.info('Bu dosyada satır bulunmuyor.')
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
            for p in files:
                try:
                    table=pd.read_csv(p,encoding='utf-8-sig')
                    table=show_frame(table,p)
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
