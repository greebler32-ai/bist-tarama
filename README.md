# BIST Web V8 — Sade taramalar

Günlük menü: Günlük Top10, Uyuyan Hisseler, Patlama Öncesi, Balina İzi. Canlı menü: Canlı Trade, Canlı Tavan, Tavan Radarı, Dönüş Avcısı, Balina + Erken Teyit.
Test, hafıza, başarı, iTick ve otomatik plan ayrı Test ve takip araçları bölümünde.
Her taramanın açıklaması sayfada açılır; TARAMA_KILAVUZU.md dosyasında tüm açıklamalar var.

GitHub deposunun kökündeki dosyaları bu sürümle güncelleyin. Streamlit giriş dosyası app.py. Yeni sonuçlar için yeni tarama başlatın. Eski sonuç CSV'leri geriye dönük hesaplanmaz.
Kurulum: KURULUM.bat → WEB_CALISTIR.bat. Sunucuda Python 3.12 önerilir.

Hata raporları artık aday tablosuna dönüştürülmez. Dosya listesinde sonuc.csv önce, veri hata dosyaları sonra gelir. Hata raporlarında hisse ve hata nedeni gösterilir. Hiçbir teknik seviye hata satırından üretilmez.
Uyuyan ve olumlu balina adaylarında günlük mumlardan teknik plan hesaplanır. Dağıtım izine alım hedefi verilmez. Üretilmeyen alan — olarak görünür; sıfır fiyat uydurulmaz. Puan olasılık değildir.
Top10 hem ekranda hem kayıtta en fazla 10 adaydır.

22 odaklı test geçti: sade menü/kılavuz, hata ve rapor ayrımı, plan hesapları, havuz ve geçiş geçmişi, web açılışı. Gerçek veri sağlayıcı sorunlarının ortadan kalktığı iddia edilmez.

Anahtarlar yalnız Streamlit Secrets alanına: ADMIN_ACCESS_CODE ve ITICK_KEY. Gerçek .env/secrets.toml GitHub'a yüklenmez.
Sunucu dosyalarının yeniden başlatmada kalıcı olduğu varsayılmaz; CSV'leri indirin. Zamanlı plan sunucu açıkken çalışır; yeniden açılışta yönetici başlatır.

Bu pakette eski 1–8 stratejileri, yinelenen V32 varyantları, masaüstü menüsü, test dosyaları ve önbellek yoktur. Kalan .py dosyaları kullanılan motorların çalışma bağımlılıklarıdır.

## V7 veri kontrolu
Veri indirme cagrilari is bazinda raporlanir: basarili, basarisiz, onbellek. Bunlar benzersiz hisse sayilari degildir.
Hic veri donmezse "Veri alinamadi"; basarili ve basarisiz istekler birlikte varsa "Kismi". Bu durumlar "aday bulunamadi" ile karistirilmaz. Yerel hafiza/ozet gibi veri indirmeyen islemler bu kurala tabi degildir.
Her istegin hata raporu WEB_VERI_HATALARI.csv dosyasindadir. Kaynak fiyatlar gelmediginde yeni fiyat uydurulmaz.
Teknik plan icin son 20 mumun fiyatlari pozitif, son kapanis mumun araliginda ve veriler sonlu olmalidir. Bozuk son mum yerine eski bir mumun plani yazilmaz. Ekranda stop<giris<hedef saglanmayan plan gosterilmez.
28 agdan bagimsiz birim kontrolu ve Python derleme kontrolu gecti. Yfinance veri cagrilari bu birim testlerinde taklit edilmistir. Bu ortamda paket kaynagindan Streamlit/yfinance kurulamadigi icin V7 web acilisi yeniden test edilemedi. Canli veri baglantisi veya piyasa basarisi dogrulanmadi.

V8: Canlı Trade/Tavan/Radar geri eklendi; otomatik canlı turuna da bağlandı. Yahoo taramaları gecikmeli 15dk veridir; iTick ile aynı akış değildir.
