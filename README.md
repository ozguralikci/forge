# AI Software Factory

Kullanıcının doğal dille verdiği yazılım talebini araştıran, planlayan, tartışan, kodlayan, test eden, denetleyen ve teslim eden çok ajanlı yazılım şirketi işletim sistemi.

## İlk hedef

İlk pilotta sistem şu akışı kanıtlayacaktır:

1. Kullanıcı proje talebini verir.
2. Sistem proje anayasası ve kabul kriterleri oluşturur.
3. ChatGPT/OpenAI proje yönetimi ve hakemlik yapar.
4. Claude mimari eleştiri ve teknik değerlendirme yapar.
5. Kodlama ajanı projeyi uygular.
6. Bağımsız doğrulama katmanı testleri gerçekten çalıştırır.
7. Hatalar kök neden analiziyle düzeltilir.
8. Çalışan proje, test raporu ve dokümantasyonla teslim edilir.

## Önerilen roller

- OpenAI / ChatGPT: CEO, ürün yöneticisi, proje yöneticisi, final hakemi
- Claude: baş mimar, teknik eleştirmen, risk değerlendirici
- Claude Code veya Codex CLI: ana uygulayıcı
- Codex CLI veya ikinci sağlayıcı: bağımsız kod inceleyici
- Python orkestratör: durum makinesi, izinler, görev kuyruğu, maliyet ve denetim
- Docker + Git + CI: tarafsız doğrulama

## Başlangıç dosyaları

- `docs/PROJECT_CONSTITUTION.md`: değiştirilemez ve kullanıcı kontrollü kurallar
- `docs/PRODUCT_VISION.md`: ürün tanımı ve kapsam
- `docs/ARCHITECTURE.md`: sistem mimarisi
- `docs/ROADMAP.md`: fazlar ve teslim kapıları
- `docs/AUTHORIZATION_MODEL.md`: kullanıcı izin ve sorumluluk sistemi
- `docs/DEFINITION_OF_DONE.md`: tamamlanma kriterleri
- `prompts/CHATGPT_SYSTEM_PROMPT.md`: ChatGPT rol talimatı
- `prompts/CLAUDE_SYSTEM_PROMPT.md`: Claude rol talimatı
- `prompts/IMPLEMENTER_PROMPT.md`: kodlama ajanı talimatı
- `schemas/*.json`: ajanlar arası standart veri sözleşmeleri
- `config/project_defaults.yaml`: varsayılan proje politikaları
- `examples/pilot_bot/PROJECT_REQUEST.md`: ilk pilot örneği

## İlk çalışma sırası

1. `docs/PROJECT_CONSTITUTION.md` kullanıcı tarafından onaylanır.
2. API ve geliştirme ortamı hazırlanır.
3. Orkestratör iskeleti yazılır.
4. ChatGPT ve Claude sağlayıcı adaptörleri eklenir.
5. Tek görevlik kodlama/test döngüsü çalıştırılır.
6. İlk pilot bot baştan sona üretilir.
