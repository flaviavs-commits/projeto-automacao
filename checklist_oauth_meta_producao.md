# Checklist Manual - OAuth Meta em Producao

## Objetivo

Validar fluxo OAuth Meta/Facebook ponta a ponta, persistencia segura de token e readiness efetivo em runtime.

## 1. Pre-flight de configuracao

1. Confirmar variaveis no servico da API no Railway:
   - `META_ENABLED=true`
   - `META_APP_ID` e `META_APP_SECRET` (ou aliases `INSTAGRAM_APP_ID`/`INSTAGRAM_APP_SECRET`)
   - `META_OAUTH_REDIRECT_URI` (URL publica da callback)
   - `OAUTH_STATE_SECRET`
   - `TOKEN_ENCRYPTION_SECRET`
2. Confirmar deploy da API em `SUCCESS`.
3. Confirmar endpoint de saude:
   - `curl.exe -sS "https://projeto-automacao-production.up.railway.app/health"`

## 2. Iniciar autorizacao OAuth

1. Gerar URL de autorizacao sem redirecionar automaticamente:
   - `curl.exe -sS "https://projeto-automacao-production.up.railway.app/oauth/meta/start?return_url=true"`
2. Validar que a resposta contem:
   - `status=ok`
   - `authorization_url`
   - `redirect_uri`
3. Abrir `authorization_url` no navegador e concluir consentimento na Meta.

## 3. Validar callback e persistencia

1. A callback deve responder JSON com:
   - `status=connected`
   - `platform_account_id`
   - `external_account_id`
   - `token_source`
2. Validar em banco (via shell da API/worker) que existe linha em `platform_accounts` para `platform='meta'`.
3. Validar auditoria em `audit_logs` com `event_type='meta_oauth_connected'`.

## 4. Validar readiness em runtime

1. Reconsultar saude:
   - `curl.exe -sS "https://projeto-automacao-production.up.railway.app/health"`
2. Conferir no bloco `integrations`:
   - `meta_cached_token_present=true`
   - `meta_cached_token_expired=false`
   - `meta_cached_token_ready=true`
   - `meta_runtime_enabled=true`
3. Se `instagram_business_account_id` foi retornado no callback, conferir:
   - `instagram_cached_account_ready=true`
   - `instagram_publish_ready=true` (quando aplicavel)

## 5. Teste funcional minimo

1. Criar post de teste para plataforma Meta/Instagram via `POST /posts`.
2. Verificar se nao caiu em `pending_meta_review` por indisponibilidade.
3. Se houver dispatch WhatsApp habilitado, validar envio outbound com credenciais ativas.

## 6. Teste de degradacao controlada

1. Simular token invalido/expirado (ambiente controlado).
2. Confirmar em `/health`:
   - `meta_cached_token_expired=true` ou `meta_cached_token_ready=false`
3. Confirmar comportamento esperado:
   - operacoes Meta bloqueadas de forma controlada;
   - sistema permanece operacional nas demais frentes.

## 7. Critério de aceite

1. Callback OAuth concluida com `status=connected`.
2. Token persistido e auditado.
3. `/health` com sinalizacao coerente de token cacheado.
4. Fluxo funcional Meta executa quando token valido.
5. Com token invalido/expirado, bloqueio e degradacao controlados sem quebra geral.
