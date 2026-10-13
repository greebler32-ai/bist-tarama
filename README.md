# BIST Web — V5

Streamlit giris dosyasi: `app.py`.

Tablo: Sira, Hisse, Puan, Giris Fiyati, Hedef Fiyati, Stop Loss, Kazanc %.
V33 Top10 puana gore azalan sirada ilk 10 adayi gosterir. Motor puanlari ve teknik detaylar ekranda gizlidir.

V33 hedef/stop: Giris son tamamlanmis kapanistir; hedef eski 20/40/60 mum direnci, uygun direnc yoksa 2 ATR uzatmasi. Stop son 5 mum dip yapisi altinda 0.25 ATR payidir; en az 0.5 ATR fiyat mesafesi uygulanir. Bunlar teknik referanslardir, emir veya tavan garantisi degildir.
Kullanilan kapanis tarihi sonuc tablosunun ustunde gorunur. Bayat veride uyari verilir; tatil takvimiyle teyit yapilmaz.

Yerel: KURULUM.bat, sonra WEB_CALISTIR.bat.
Yayin: dosyalari GitHub deposunun kokune yukle; Streamlit giris dosyasi app.py. .streamlit/config.toml dahil olmalidir.
Gercek anahtarlari GitHub'a yukleme. ADMIN_ACCESS_CODE ve ITICK_KEY degerlerini Streamlit Secrets alaninda tanimla. secrets.example.toml yalniz ornektir.

Ortak kayitlar sunucudadir; dosyalar yeniden baslatmada kaybolabilir. Gerektiginde CSV indir. Otomatik plan sunucu acikken calisir; yeniden baslatmada yonetici tekrar acar. iTick ve ortak kayit guncelleme yonetici gerektirir.

Bu paketten test dosyalari, terminal menusu, Docker dosyalari, eski notlar, kullanici verileri ve onbellekler cikarildi. web_engines.py ve diger motor .py dosyalari calisma bagimliliklaridir.
