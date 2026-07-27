# İlk Pilot Proje Talebi

## Talep

Belirlenen bir harici API'den düzenli olarak veri alan, veriyi yerel veritabanına kaydeden ve belirlenen koşul oluştuğunda Telegram üzerinden bildirim gönderen bir bot geliştir.

## Amaç

AI Software Factory'nin aşağıdaki yeteneklerini baştan sona kanıtlamak:

- Gereksinim çıkarma
- Güncel API araştırması
- Mimari tartışma
- Secret ve kullanıcı yetkisi yönetimi
- Kodlama
- Zamanlanmış çalışma
- Veritabanı
- Telegram entegrasyonu
- Hata çözme
- Docker
- Test ve teslimat

## Zorunlu özellikler

- API adresi ve kontrol aralığı yapılandırılabilir olmalı.
- Gelen veri SQLite veya PostgreSQL'e kaydedilmeli.
- Koşul sağlandığında Telegram mesajı gönderilmeli.
- Aynı olay için tekrar tekrar bildirim göndermemeli.
- API erişilemezse sistem çökmemeli.
- Hatalar loglanmalı.
- Docker ile çalıştırılabilmeli.
- `.env.example` bulunmalı.
- Birim ve entegrasyon testleri bulunmalı.

## Kabul senaryoları

1. Geçerli API cevabı alınır ve veri kaydedilir.
2. Koşul oluşmadığında bildirim gönderilmez.
3. Koşul oluştuğunda bir kez bildirim gönderilir.
4. Aynı olay tekrar geldiğinde ikinci bildirim gönderilmez.
5. API hata verdiğinde bot çalışmaya devam eder ve hata kaydı oluşturur.
6. Uygulama sıfırdan Docker ile kurulabilir.
