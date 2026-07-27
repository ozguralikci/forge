# Sistem Mimarisi

## Üst seviye bileşenler

1. Müşteri ve proje portalı
2. FastAPI orkestratör
3. Durum makinesi
4. Yetkilendirme motoru
5. Görev kuyruğu
6. Ajan sağlayıcı adaptörleri
7. Araştırma katmanı
8. İzole geliştirme ortamı
9. Git ve sürüm yönetimi
10. Test ve kalite motoru
11. Teslimat üreticisi
12. Denetim ve maliyet kayıtları

## Önerilen teknoloji yığını

- Backend: Python 3.12+, FastAPI
- Veri tabanı: PostgreSQL
- Kuyruk: Redis + Dramatiq veya Celery
- Arayüz: React veya Next.js
- Orkestrasyon: açık durum makinesi + sağlayıcı adaptörleri
- AI sağlayıcıları: OpenAI API, Anthropic API
- Kodlama motorları: Claude Code ve/veya Codex CLI
- İzolasyon: Docker
- Sürüm kontrolü: Git + GitHub
- CI: GitHub Actions
- Secret yönetimi: yerel şifreli kasa; ileride Vault

## Ana akış

```text
PROJECT_RECEIVED
→ REQUIREMENTS_ANALYSIS
→ RESEARCH
→ ARCHITECTURE_DISCUSSION
→ PLAN_APPROVED
→ TASK_READY
→ IMPLEMENTING
→ TESTING
→ REVIEWING
→ FIX_REQUIRED veya TASK_COMPLETED
→ FINAL_VALIDATION
→ USER_ACCEPTANCE
→ PROJECT_COMPLETED
```

## Sağlayıcı bağımsızlığı

Orkestratör doğrudan model markalarına bağlı yazılmamalıdır.

```python
class AgentProvider:
    async def run(self, request): ...
    async def review(self, request): ...
    async def execute(self, request): ...
```

İlk adaptörler:

- OpenAIProvider
- AnthropicProvider
- ClaudeCodeProvider
- CodexCliProvider

## Korunan alanlar

- `constitution/`
- `acceptance_tests/`
- `orchestrator/security/`
- `orchestrator/budget/`

Uygulayıcı ajan bu alanlara yazamaz.
