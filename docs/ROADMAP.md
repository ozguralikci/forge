# Yol Haritası

## FAZ 0 — Proje temeli

- Ürün vizyonu
- Proje anayasası
- Yetkilendirme modeli
- Ajan rolleri
- JSON şemaları
- İlk pilot tanımı

Çıkış kriteri: Belgeler onaylanmış olmalı.

## FAZ 1 — Orkestratör çekirdeği

- Proje ve görev modelleri
- Durum makinesi
- Audit log
- Bütçe sınırı
- Yetki talepleri
- Sağlayıcı arayüzü

Çıkış kriteri: Sahte ajanlarla tam görev akışı çalışmalı.

## FAZ 2 — OpenAI ve Claude entegrasyonu

- OpenAI planlayıcı/hakem
- Claude mimar/eleştirmen
- Standart JSON mesajları
- Hata ve tekrar yönetimi

Çıkış kriteri: İki model aynı proje planını değerlendirip kayıtlı karar üretmeli.

## FAZ 3 — Kodlama motoru

- Claude Code veya Codex CLI adaptörü
- İzole çalışma alanı
- Dosya izinleri
- Komut izin listesi
- Git branch ve checkpoint

Çıkış kriteri: Tek küçük görev otomatik kodlanıp commitlenmeli.

## FAZ 4 — Bağımsız doğrulama

- pytest / npm test
- lint ve type-check
- build
- güvenlik taraması
- korunan kabul testleri

Çıkış kriteri: Ajan raporundan bağımsız PASS/FAIL sonucu üretilmeli.

## FAZ 5 — Düzeltme döngüsü

- Hata sınıflandırması
- Kök neden analizi
- Araştırma tetikleme
- En fazla üç düzeltme turu
- Başarısız çözüm hafızası

Çıkış kriteri: Bilerek hatalı görev otomatik düzeltilmeli.

## FAZ 6 — İlk pilot proje

- Harici API'den veri alma
- Veriyi kaydetme
- Koşul oluşunca Telegram bildirimi
- Zamanlama
- Docker
- Test ve teslimat

Çıkış kriteri: Kullanıcı kabul senaryoları geçmeli.

## FAZ 7 — Web kontrol paneli

- Proje oluşturma
- Durum izleme
- Yetki onayları
- Ajan kararları
- Test sonuçları
- Teslimat indirme

## FAZ 8 — Çoklu proje ve bakım

- Birden fazla proje
- Sürüm yönetimi
- Hata ve bakım talepleri
- Güvenlik ve bağımlılık takibi
