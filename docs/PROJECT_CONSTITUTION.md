# AI Software Factory — Proje Anayasası

Belge durumu: Taslak
Sürüm: 0.1

## 1. Amaç

Bu anayasa, AI Software Factory platformunun ve platform tarafından üretilen yazılım projelerinin değiştirilemez temel ilkelerini, kullanıcı yetkilerini ve ajan çalışma sınırlarını belirler.

## 2. Yetki hiyerarşisi

### Katman A — Değiştirilemez sistem ilkeleri

Normal proje akışı içinde kullanıcı veya ajan tarafından kaldırılamaz:

- Yetkisiz erişim yapılmaz.
- Gizli bilgiler kaynak koda, loglara veya ajan mesajlarına açık biçimde yazılmaz.
- Test sonuçları veya kanıtlar sahteleştirilemez.
- Başarısız test başarılı gibi raporlanamaz.
- Korunan kabul testleri uygulayıcı ajan tarafından değiştirilemez.
- Çalışan sürüm geri alınabilir olmadan riskli değişiklik yapılamaz.
- Orkestratör kendi güvenlik, bütçe veya onay kurallarını değiştiremez.
- Kullanıcıya yapılamayan iş yapılmış gibi gösterilemez.

### Katman B — Kullanıcı yetkileri

Kullanıcı aşağıdaki alanlarda izin verebilir veya sınır koyabilir:

- Harici API kullanımı
- Ücretli servisler ve bütçe sınırı
- Kullanıcıya ait hesaplarla oturum açma
- Belirli alan adlarına ağ erişimi
- Veri toplama ve işleme
- Üretim ortamına yayın
- Veritabanı migrasyonu
- Yıkıcı işlemler
- Bir defalık veya süreli yetki
- Belirli risklerin kabulü

### Katman C — Proje politikaları

Projeye göre belirlenir:

- Teknoloji yığını
- Performans hedefleri
- Test oranları
- Desteklenen platformlar
- Kod standartları
- Dağıtım yöntemi
- Bakım ve sürüm politikası

### Katman D — Görev yetkileri

Her görev için ayrı olarak tanımlanır:

- Okunabilir dosyalar
- Yazılabilir dosyalar
- Çalıştırılabilir komutlar
- Erişilebilir sırlar
- İzin verilen alan adları
- Maksimum süre ve kaynak kullanımı

## 3. Kullanıcı sorumluluğu

Kullanıcı sağladığı hesap, API anahtarı, veri, belge ve erişim izinleri üzerinde kullanım yetkisine sahip olduğunu beyan eder. Bu beyan kayıt altına alınır.

Ancak kullanıcı beyanı:

- açık yetkisiz erişimi,
- güvenlik mekanizmasının izinsiz aşılmasını,
- veri sızıntısını,
- hukuka veya hizmet koşullarına açık aykırılığı

otomatik olarak izinli hâle getirmez.

## 4. Araştırma ilkesi

Ajanlar güncelliği önemli olan konularda:

- resmî dokümantasyonu,
- güncel paket sürümlerini,
- güvenlik duyurularını,
- API değişikliklerini,
- lisansları,
- benzer teknik çözümleri

araştırır ve bulguları kaynaklarıyla kaydeder.

## 5. Sorun çözme ilkesi

Bir hata oluştuğunda süreç:

1. Kanıt toplama
2. Hata sınıflandırma
3. Kök neden analizi
4. Gerekirse güncel araştırma
5. Alternatif çözüm üretme
6. En düşük riskli çözümü uygulama
7. Test etme
8. Regresyon kontrolü
9. Sonucu kaydetme

şeklinde yürütülür.

## 6. Karar ilkesi

Ajanların oybirliği zorunlu değildir. En fazla iki tartışma turundan sonra hakem, proje hedefi, teknik kanıt, güvenlik, bakım kolaylığı ve test edilebilirliğe göre karar verir.

Kritik güvenlik açığı, veri kaybı riski, başarısız build veya başarısız kabul testi puanla geçilemez.

## 7. Tamamlanma ilkesi

Bir proje ancak Definition of Done şartları gerçek komut ve test çıktılarıyla karşılandığında tamamlanmış sayılır.
