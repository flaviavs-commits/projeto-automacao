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
- `META_VERIFY_TOKEN`
- `META_ACCESS_TOKEN`
- `INSTAGRAM_APP_ID`
- `INSTAGRAM_APP_SECRET`
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `TIKTOK_CLIENT_KEY`
- `TIKTOK_CLIENT_SECRET`
- `LOCAL_STORAGE_PATH`
- `LOG_LEVEL`

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
- `GET /contacts`
- `GET /conversations`
- `GET /messages`
- `GET /posts`
- `GET /analytics`
- `GET /webhooks/meta`
- `POST /webhooks/meta`

## Status atual

- Base da API, configuracao, logging estruturado, SQLAlchemy e Celery estao preparados.
- Modelos principais e migracao inicial foram adicionados.
- Webhook Meta esta pronto para verificacao local e recebimento seguro de payload.
- Integracoes externas e rotinas de publicacao seguem como stubs seguros ate a configuracao de credenciais reais.
nem precisava disso
,,,,,,,,,,,,,,,,,    