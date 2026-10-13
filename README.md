# BIST Sinyal Atölyesi — Web 1.0

28 masaüstü seçeneği Streamlit arayüzüne bağlanmıştır. Gerçek Python motorları kullanılır; örnek sonuçlar gösterilmez.

## Yerelde açılış

Python 3.12 önerilir. `python -m pip install -r requirements.txt` ardından `python -m streamlit run app.py`.
Windows: KURULUM.bat, sonra WEB_CALISTIR.bat.

## Herkese açık yayın

ZIP içindeki dosyaları GitHub deponuzun köküne yükleyin. `.streamlit/config.toml` klasörünü de ekleyin. Gerçek `.env`, secrets.toml veya web_data yüklemeyin.
Streamlit Community Cloud: https://share.streamlit.io → Create app → depo/branch seçin → Main file path: `app.py` → Deploy.
Uygulama erişimini App settings içinde Public yapın. Kaynak deponun herkese açık olması şart değildir; uygulama erişimi ayrı ayardır.
Advanced settings/Secrets alanına `secrets.example.toml` örneğindeki alanları kendi değerlerinizle ekleyin. Anahtarlar kodda tutulmaz.
Bu paket hazırlanmıştır; kendiliğinden internette yayınlanmış bir URL değildir.
Resmi kılavuz: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

## Kullanım

Tarama grubunu ve motoru seç → gerekiyorsa periyot/tarih gir → Taramayı başlat.
İşler sunucuda sırayla çalışır, sayfa 3 saniyede bir durumunu yeniler. Sonuçlar CSV/tablo ve ZIP olarak indirilebilir.
Kayıtlar ortak sunucu kaydıdır; arkadaşlarınız aynı havuz/hafızayı görür. Kullanıcı hesabı veya kişisel portföy yoktur.
Aynı anda aynı tarama istenirse mevcut işe katılınır. Katıldığınız ortak işi durdurmanız diğer izleyenlerin taramasını durdurmaz.
25 (ortak sonuçları güncelleme), 16 (tüm motorlar) ve iTick başlatma yönetici kodu gerektirir. Diğer taramalar herkese açıktır.
Otomatik 20 seans yönetici bölümünden açılır; manuel 16 tüm motorları bir kez çalıştırır. Saatler İstanbul saatidir.
Otomatik plan sunucu işlemi açıkken çalışır. Plan/sıra bellekte tutulur; yeniden başlatmada tekrar açılmalıdır. Resmi tatil takvimi yoktur.
iTick takibi en fazla 30 dakika çalışır. Gerçek hesap/paket uyumluluğu test edilmedi.
Yahoo önbelleği günlük veride 15 dakika, gün içi veride 1 dakika; veri sınırları önbellekle tamamen kalkmaz.
Tarama başına en fazla 3 saat süre vardır. Uzun testlerde dosyalar iş tamamlandığında gösterilir.
Eski Telegram gönderimleri web ziyaretçileri için kapatılır. Yeni bildirim aboneliği yoktur.

## Kalıcı sunucu seçeneği

Community Cloud dosyalarının ve çalışan işlemlerin yeniden başlatmada korunacağı varsayılmaz. Hafızayı düzenli indirin.
Kalıcı diskli kendi Python sunucunuzda Docker kullanabilirsiniz: `docker build -t bist-web .` ardından `docker run -p 8501:8501 -v bist-data:/app/web_data bist-web`.
Anahtarlar env veya sunucu secrets ayarıyla verilir. Tek sunucu/tek Streamlit işleminde ortak sıra ve dosya kilidi kullanılır; çoklu replica desteklenmez.

## Doğrulama sınırı

Motor birim testleri, web açılışı ve iş/sıra kontrolleri yapılır. Gerçek Yahoo denemeleri HTTP429 nedeniyle başarısız olmuştu.
Web dönüşümü tavan yakalama oranının yükseldiği anlamına gelmez. Kurum kimliği belirlenmez; fiyat-hacim izi gösterilir.
