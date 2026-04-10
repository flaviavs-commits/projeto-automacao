# bot-multiredes

Backend central em Python/FastAPI para orquestrar WhatsApp, Instagram, TikTok, YouTube, dashboard e automacoes assicronas.

## Stack

- Python 3.12
- FastAPI + Uvicorn
- Pydantic Settings
- SQLAlchemy + Alembic
- PostgreSQL
- Redis + Celery

## Estrutura

```text
app/
  main.py
  core/
    config.py
    database.py
    logging.py
    security.py
  api/routes/
    analytics.py
    contacts.py
    conversations.py
    health.py
    messages.py
    posts.py
    webhooks_meta.py
  models/
    audit_log.py
    contact.py
    conversation.py
    job.py
    message.py
    platform_account.py
    post.py
  schemas/
    contact.py
    conversation.py
    message.py
    post.py
    webhook.py
  services/
    analytics_service.py
    instagram_publish_service.py
    instagram_service.py
    media_service.py
    memory_service.py
    routing_service.py
    tiktok_service.py
    transcription_service.py
    whatsapp_service.py
    youtube_service.py
  workers/
    celery_app.py
    tasks.py
alembic/
```

## Configuracao

Copie `.env.example` para `.env` e ajuste os valores locais. As variaveis suportadas incluem:

- `APP_NAME`
- `APP_ENV`
- `APP_PORT`
- `DATABASE_URL`
- `REDIS_URL`
- `META_ENABLED`
- `META_VERIFY_TOKEN`
- `META_ACCESS_TOKEN`
- `META_GRAPH_BASE_URL`
- `META_AUTH_BASE_URL`
- `META_API_VERSION`
- `META_WHATSAPP_PHONE_NUMBER_ID`
- `INSTAGRAM_BUSINESS_ACCOUNT_ID`
- `INSTAGRAM_APP_ID`
- `INSTAGRAM_APP_SECRET`
- `META_APP_ID` (opcional, alias de app id para OAuth)
- `META_APP_SECRET` (opcional, alias de app secret para OAuth)
- `META_OAUTH_REDIRECT_URI`
- `META_OAUTH_SCOPES`
- `OAUTH_STATE_SECRET`
- `OAUTH_STATE_TTL_SECONDS`
- `TOKEN_ENCRYPTION_SECRET`
- `YOUTUBE_API_KEY`
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `TIKTOK_ENABLED`
- `TIKTOK_API_BASE_URL`
- `TIKTOK_CLIENT_KEY`
- `TIKTOK_CLIENT_SECRET`
- `LOCAL_STORAGE_PATH`
- `LOG_LEVEL`

### Modo sem Meta (fallback automatico)

- Quando `META_ENABLED=false` ou nao existir token (nem `META_ACCESS_TOKEN` nem token OAuth salvo), as integracoes Meta ficam em fallback seguro.
- `POST /webhooks/meta` aceita o payload e retorna `ignored_reason=meta_disabled` sem enfileirar jobs.
- Posts de plataformas Meta em status de fila (`draft`, `queued`, `scheduled`, etc.) passam automaticamente para `pending_meta_review`.
- Se TikTok estiver sem setup (`TIKTOK_ENABLED=false` ou sem key/secret), posts TikTok equivalentes passam para `pending_tiktok_setup`.
- `GET /health` exibe `integrations` com `meta_runtime_enabled`, `meta_cached_token_ready` e `tiktok_runtime_enabled` para observabilidade.

## Instalar dependencias

```bash
pip install -r requirements.txt
```

## Subir a API

```bash
uvicorn app.main:app --reload --port 8000
```

## Deploy no Railway

O projeto inclui `Procfile` para start da API no Railway:

```text
web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-${APP_PORT:-8000}}
```

No Railway, configure as variaveis de ambiente necessarias (principalmente `DATABASE_URL`, `REDIS_URL` e tokens). A porta usa `PORT` (Railway) com fallback para `APP_PORT`.

## Subir o worker Celery

```bash
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

## Migracoes

Criar ou revisar as migracoes:

```bash
alembic revision --autogenerate -m "descricao"
```

Aplicar as migracoes:

```bash
alembic upgrade head
```

## Endpoints iniciais

- `GET /`
- `GET /health`
- `GET /dashboard`
- `GET /contacts`
- `GET /contacts/{contact_id}`
- `POST /contacts`
- `PATCH /contacts/{contact_id}`
- `GET /conversations`
- `GET /conversations/{conversation_id}`
- `POST /conversations`
- `PATCH /conversations/{conversation_id}`
- `GET /messages`
- `GET /messages/{message_id}`
- `POST /messages`
- `PATCH /messages/{message_id}`
- `GET /posts`
- `GET /posts/{post_id}`
- `POST /posts`
- `PATCH /posts/{post_id}`
- `GET /analytics`
- `GET /oauth/meta/start`
- `GET /oauth/meta/callback`
- `GET /oauth/facebook/start`
- `GET /oauth/facebook/callback`
- `GET /webhooks/meta`
- `POST /webhooks/meta`

## OAuth Meta/Facebook

- Endpoint de inicio: `GET /oauth/meta/start` (alias: `GET /oauth/facebook/start`).
- Endpoint de callback: `GET /oauth/meta/callback` (alias: `GET /oauth/facebook/callback`).
- O callback valida `state` assinado com TTL e troca o `code` por token na Graph API.
- O token resultante e salvo em `platform_accounts.access_token_encrypted`.
- Os servicos de WhatsApp e publicacao Instagram usam esse token salvo como fallback automatico.
- A URI de callback no Meta Developers deve apontar para seu dominio publico, por exemplo:
  - `https://SEU_DOMINIO/oauth/meta/callback`
  - ou `https://SEU_DOMINIO/oauth/facebook/callback`

## Status atual

- Base da API, configuracao, logging estruturado, SQLAlchemy e Celery estao preparados.
- Modelos principais e migracao inicial foram adicionados.
- Webhook Meta esta pronto para verificacao local e recebimento seguro de payload.
- OAuth Meta/Facebook (`/oauth/meta/start` + `/oauth/meta/callback`) esta implementado com `state` assinado e persistencia de token em `platform_accounts`.
- Dashboard web inicial para operacao (leads, mensagens e posts) disponivel em `/dashboard`.
- Integracoes externas ja possuem adaptadores HTTP reais (WhatsApp/Instagram/TikTok/YouTube), operando com fallback seguro quando faltam credenciais.
