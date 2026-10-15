# BIST Web V6 — Sade taramalar

Ana menüde altı tarama: Günlük Top10, Uyuyan Hisseler, Patlama Öncesi, Dönüş Avcısı, Balina İzi, Balina + Erken Teyit.
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

Bu pakette eski 1–8 stratejileri, yinelenen tavan/V32 varyantları, masaüstü menüsü, test dosyaları ve önbellek yoktur. Kalan .py dosyaları kullanılan motorların çalışma bağımlılıklarıdır.
