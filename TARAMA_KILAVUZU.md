# BIST Tarama Kılavuzu

Önerilen akış: Günlük Top10 veya Uyuyan Hisseler → Balina + Erken Teyit → Sonuç Güncelle → Başarı Özeti.

## Günlük Top10

**Ne arar?** Ertesi işlem seansı için en güçlü en fazla 10 adayı sıralar.

**Veri:** Seans içinde son mevcut tamamlanmış günlük mum; 18.10 sonrası bugünkü kapanış mevcutsa o kullanılır.

**Nasıl okunur?** Puan seçimin sırasını gösterir; başarı olasılığı değildir. Giriş son kapanıştır. Hedef eski direnç, uygun direnç yoksa 2 ATR; stop son beş mum dip yapısının altıdır.

**Ne zaman kullanılır?** Günün Top10 adaylarını görmek istediğinde kullan. Tavan garantisi veya otomatik alım değildir.

## Uyuyan Hisseler

**Ne arar?** Henüz sert hareket yapmamış, sıkışan veya dinlenmesi bitmeye yaklaşan hisseleri arar.

**Veri:** Tamamlanmış günlük mumlar. Sonuçta kullanılan kapanış tarihine bak.

**Nasıl okunur?** HAZIRLIK/UYKU-SONU erken aşamadır; UYANIŞ hacim ve zamanlama güçlenmesidir. Kalıcı havuz geçmişi ve balina iziyle birlikte okunur.

**Ne zaman kullanılır?** Hareketten önce hazırlık listesi oluşturmak için kullan. İlk üç seans fiyat hareketi ayrıca ölçülür.

## Patlama Öncesi

**Ne arar?** Uzun dinlenme, düşüşün durması, daralma ve hacim uyanışı birlikteliğini arar.

**Veri:** Tamamlanmış günlük mumlar.

**Nasıl okunur?** ERKEN, HAZIRLANIYOR ve ATEŞLEME hazırlık dereceleridir. Sade tabloda ilk hedef H1; ayrıntılı hafızada H2/H3 ve yapı bozulması da tutulur.

**Ne zaman kullanılır?** Daha geniş patlama hazırlık havuzunu ve teknik hedef bölgelerini görmek için kullan. ERKEN-3G ile aynı filtre değildir.

## Dönüş Avcısı

**Ne arar?** Sert düşüşün ardından fiyatın gerçekten tepki verdiği hisseleri arar.

**Veri:** Yahoo gecikmeli 15 dakikalık mumlar.

**Nasıl okunur?** Dönüş puanı ve fiyat/hacim teyitlerini birlikte değerlendirir. Son bar henüz kapanmamış olabilir; aday listesi tek başına kesin giriş değildir.

**Ne zaman kullanılır?** Gün içinde dipten tepki adaylarını izlemek için kullan.

## Balina İzi

**Ne arar?** Fiyat-hacimde birikim, güçlü alım ve dağıtım izlerini ayırır.

**Veri:** Bugün hariç tamamlanmış günlük mumlar; hacim oranı, CMF ve OBV yönü.

**Nasıl okunur?** BİRİKİM ADAYI ve GÜÇLÜ ALIM İZİ olumlu iz; DAĞITIM İZİ olumlu alım teyidi değildir.

**Ne zaman kullanılır?** Büyük para hareketi olabilecek izleri taramak için kullan. Kurum, kişi veya gerçek takas kimliği belirlenmez.

## Balina + Erken Teyit

**Ne arar?** Uyuyan havuzuyla birikim/güçlü alım izi ortak olan hisselerde canlı dönüş teyidi arar.

**Veri:** Günlük hazırlık için bugün hariç aynı tarihli mumlar; canlı teyit için gecikmeli 15 dakika.

**Nasıl okunur?** CANLI TEYİT BEKLİYOR hazırlık; GİRİŞ TETİKLENDİ tamamlanmış bar ve hacim/yön koşullarının birlikte sağlanmasıdır. SEANS DIŞI veya VERİ TEYİDİ BEKLİYOR giriş değildir.

**Ne zaman kullanılır?** Hazırlık havuzunu gün içi teyitle daraltmak için kullan. Günlük referans ve canlı tetik fiyatı ayrı saklanır.

## Top10 Başarı Testi

**Ne arar?** Geçmişteki günlük Top10 listelerinin ertesi seans sonucunu ölçer.

**Veri:** Seçilen tarihlerde sadece bir önceki tamamlanmış kapanışa kadar veri.

**Nasıl okunur?** %9,5 ve üstü kapanış yaklaşık tavan ölçütüdür; gün içinde tavan fiyatına dokunma ölçümü değildir.

**Ne zaman kullanılır?** Nisan–Ağustos gibi dönemleri Eylül’den ayrı test etmek için kullan. Sonuç hesaplanmadan başarı iddia edilmez.

## Uyuyan Havuzu Başarı Testi

**Ne arar?** Uyuyan havuzu adaylarının sonraki üç seansta ne yaptığını ölçer.

**Veri:** Seçilen tarihlerde sinyal anına kadar veri; ileri üç seans yalnız sonuç ölçümünde kullanılır.

**Nasıl okunur?** +%5/+%7/+%9,5 görülme oranları ve ters hareket izlenir; eksik üç seans başarı hesabına girmez.

**Ne zaman kullanılır?** Erken yakalama başarısını patern bazında karşılaştırmak için kullan.

## Tarama Hafızası

**Ne arar?** Bir hissenin hangi taramada ne zaman çıktığını gösterir.

**Veri:** Sunucuda daha önce kaydedilmiş taramalar.

**Nasıl okunur?** Hisse koduyla filtrele; kayıt yoksa geçmiş veri henüz birikmemiş olabilir.

**Ne zaman kullanılır?** Önceki adayları aramak için kullan. Uyuyan havuzu ve geçişleri sayfanın Ortak kayıtlar bölümünde de açılır.

## Sonuç ve Hedef Güncelle

**Ne arar?** Kaydedilmiş adayların sonraki seanslarını ve sabit hedeflerini günceller.

**Veri:** Yahoo tamamlanmış günlük verisi ve XU100 seansları.

**Nasıl okunur?** D3 başarı fiyat hareketidir, gerçekleşmiş işlem kârı değildir. Aynı mumda stop/hedef varsa ihtiyatlı ölçüm uygulanır.

**Ne zaman kullanılır?** Başarı özetinden önce çalıştır. Ortak kayıtları değiştirdiği için yönetici gerekir.

## Başarı Özeti

**Ne arar?** Tamamlanan adayları motor ve patern bazında özetler.

**Veri:** Tarama hafızasının güncellenmiş sonuçları.

**Nasıl okunur?** Aynı motor/hisse/gün için ilk kayıt kullanılır. Bekleyen ve eksik kayıtlar başarı oranına katılmaz.

**Ne zaman kullanılır?** 25 ile sonuçları güncelledikten sonra aç.

## iTick · Canlı Top3 Takibi

**Ne arar?** Dönüş Avcısı adaylarının en güçlü üçünü iTick üzerinden fiyat takibine alır.

**Veri:** Gecikmeli aday seçimi + hesabın izin verdiği iTick fiyat akışı.

**Nasıl okunur?** iTick yeni aday bulmaz; seçilmiş adayları izler. Sunucu anahtarı ve yönetici erişimi gerekir.

**Ne zaman kullanılır?** Canlı fiyat takibi için kullan. En fazla 30 dakika; gerçek hesap bağlantısı ayrıca doğrulanmalıdır.

## Otomatik Ana Motorlar

**Ne arar?** Ana günlük motorları ve Dönüş Avcısını topluca çalıştırır.

**Veri:** Her motorun kendi günlük/15 dakika verisi.

**Nasıl okunur?** Düğme bir kez çalıştırır. Yönetici bölümündeki 20 seans planı saatli tekrarları açar.

**Ne zaman kullanılır?** Toplu çalışma için kullan. Sunucu açık kalmalı; yeniden başlatmada plan tekrar açılır.

Veri eskiliği ve sağlayıcı hataları kontrol edilmelidir. Kılavuz tarama mantığını açıklar; yatırım önerisi değildir.
