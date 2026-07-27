# Kullanıcı Yetkilendirme Modeli

## Yetki tipleri

- Kalıcı izin
- Süreli izin
- Bir defalık izin
- Görev bazlı izin
- Bütçe limitli izin
- Alan adı veya servis bazlı izin

## Yetki talebi örneği

```yaml
authorization_request:
  id: AUTH-001
  project_id: PILOT-001
  action: external_api_usage
  provider: example_service
  purpose: user_authorized_data_processing
  requested_secret: EXAMPLE_API_KEY
  allowed_domains:
    - api.example.com
  spending_limit_try: 1000
  expires_at: null
  reusable: false
  risk_level: medium
  system_recommendation: approve_once
```

## CAPTCHA ve doğrulama politikası

Öncelik sırası:

1. Resmî API
2. Kullanıcının manuel doğrulamasıyla yetkili oturum
3. Kullanıcı tarafından sağlanan üçüncü taraf servis; yalnızca yetkili ve uygun kullanımda

Yasak:

- Yetkisiz hesaplara erişmek
- Güvenlik kontrolünü kötüye kullanım amacıyla aşmak
- Kullanıcı izni olmadan üçüncü tarafa hassas veri göndermek

## Secret yönetimi

- Secret kaynak koda yazılmaz.
- Loglarda maskelenir.
- Ajan yalnız görev için gerekli secret'a erişir.
- Yetki süresi bitince erişim kaldırılır.
- Kullanıcı isterse secret anında iptal edilir.
