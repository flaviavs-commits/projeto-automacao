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
    contact_identity.py
    contact_memory.py
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
    contact_memory_service.py
    customer_identity_service.py
    instagram_publish_service.py
    instagram_service.py
    llm_reply_service.py
    media_service.py
    memory_service.py
    routing_service.py
    tiktok_service.py
    transcription_service.py
    whatsapp_service.py
    youtube_service.py
  prompts/
    studio_agendamento.md
  workers/
    celery_app.py
    tasks.py
alembic/
road_test/
  chat_test_app.py
  build_chat_test_exe.cmd
  iniciar_leve_local.cmd
  parar_tudo_local.cmd
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
- `EVOLUTION_API_BASE_URL`
- `EVOLUTION_API_KEY`
- `EVOLUTION_INSTANCE_NAME`
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
- `LLM_ENABLED`
- `LLM_PROVIDER`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `LLM_TEMPERATURE`
- `LLM_MAX_OUTPUT_TOKENS`
- `LLM_CONTEXT_MESSAGES`
- `LLM_OFFTOPIC_TOLERANCE_TURNS`
- `LLM_DOMAIN_LOCK`
- `LLM_DOMAIN_DESCRIPTION`
- `LLM_KNOWLEDGE_PATH`
- `LLM_TEST_MODELS`
- `LLM_QUALITY_RETRY_ENABLED`
- `LLM_QUALITY_FALLBACK_MODEL`
- `LLM_QUALITY_MIN_CHARS`
- `LOCAL_STORAGE_PATH`
- `LOG_LEVEL`

### Modo sem Meta (fallback automatico)

- Quando `META_ENABLED=false` ou nao existir token (nem `META_ACCESS_TOKEN` nem token OAuth salvo), as integracoes Meta ficam em fallback seguro.
- `POST /webhooks/meta` aceita o payload e retorna `ignored_reason=meta_disabled` sem enfileirar jobs.
- Posts de plataformas Meta em status de fila (`draft`, `queued`, `scheduled`, etc.) passam automaticamente para `pending_meta_review`.
- Se TikTok estiver sem setup (`TIKTOK_ENABLED=false` ou sem key/secret), posts TikTok equivalentes passam para `pending_tiktok_setup`.
- `GET /health` exibe `integrations` com `meta_runtime_enabled`, `meta_cached_token_ready` e `tiktok_runtime_enabled` para observabilidade.
- `GET /health` tambem exibe `whatsapp_dispatch_ready` e `whatsapp_cached_phone_number_ready`.

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

## Assistente LLM local (open source)

- O projeto foi direcionado para respostas via LLM local/open source (sem dependencia de token externo).
- Integracao atual espera endpoint compativel com Ollama em `LLM_BASE_URL` (padrao: `http://127.0.0.1:11434`).
- Modelo padrao de configuracao: `qwen2.5:0.5b-instruct` (ajustavel por `LLM_MODEL`).
- O lock de dominio e aplicado por `LLM_DOMAIN_LOCK=true`, restringindo o atendimento para estudio e agendamento.
- O contexto efetivo para conversa e retomada e de `3-5` mensagens recentes (controlado por `LLM_CONTEXT_MESSAGES`, default `5`).
- A tolerancia a desvios leves pode ser calibrada por `LLM_OFFTOPIC_TOLERANCE_TURNS` (default `2`), mantendo redirecionamento ao tema do estudio.
- A base de conhecimento usada no prompt deve ser mantida em `LLM_KNOWLEDGE_PATH` (padrao: `app/prompts/studio_agendamento.md`).
- O arquivo `app/prompts/studio_agendamento.md` foi estruturado para o atendimento comercial FC VIP, com prompt final, regras, exemplos, anti-desvio, conversao e fallback humano.
- Para road test multi-modelo, configure `LLM_TEST_MODELS` com a lista CSV dos modelos disponiveis no runtime local.
- Para qualidade comercial com latencia controlada, mantenha `LLM_MODEL` em modelo leve e habilite:
- `LLM_QUALITY_RETRY_ENABLED=true`
- `LLM_QUALITY_FALLBACK_MODEL` para um modelo mais forte (ex.: `qwen2.5:1.5b-instruct`)
- `LLM_QUALITY_MIN_CHARS` para acionar retry quando a resposta vier curta/generica.
- Para reduzir custo/tokens por chamada, ajuste:
  - `LLM_KNOWLEDGE_MAX_CHARS` (recomendado `3000-5000`)
  - `LLM_KNOWLEDGE_MAX_SECTIONS` (recomendado `2-4`)
  - `LLM_PROMPT_MAX_CONTEXT_CHARS` (recomendado `500-800`)
  - `LLM_MAX_KEY_MEMORIES` (recomendado `8-12`)

## LLM no Railway (servico separado)

Para producao, rode o LLM em um servico dedicado no mesmo projeto Railway (nao no mesmo processo da API):

- `projeto-automacao` (API)
- `worker` (Celery)
- `llm-runtime` (Ollama)
- `Postgres` e `Redis`

Arquivos de deploy do runtime:

- `infra/llm-runtime/Dockerfile`
- `infra/llm-runtime/start.sh`

Configuracao recomendada no `llm-runtime`:

- volume em `/root/.ollama` (persistencia de modelos)
- `LLM_MODEL=qwen2.5:0.5b-instruct`
- `LLM_MODELS_TO_PULL=qwen2.5:0.5b-instruct,qwen2.5:1.5b-instruct`
- `LLM_PULL_POLICY=if_missing` (`never` para subir sem pull em boot, quando o volume ja tem modelos)
- `OLLAMA_HOST=0.0.0.0:11434`
- `OLLAMA_NUM_PARALLEL=1`
- `OLLAMA_MAX_LOADED_MODELS=1`
- `OLLAMA_KEEP_ALIVE=8m`

Configuracao da API e worker para usar o runtime interno:

- `LLM_BASE_URL=http://llm-runtime.railway.internal:11434`
- `LLM_ENABLED=true`
- `LLM_PROVIDER=ollama`
- `LLM_MODEL=qwen2.5:0.5b-instruct`

Observacao:

- Se a API estiver em versao com novas tabelas (ex.: `contact_identities`), execute migracoes antes de validar webhook:
  - `alembic upgrade head`

## Road Test Isolado (chat EXE)

- Objetivo: testar conversa com o modelo "cara da empresa" sem interferir no fluxo real da API/worker.
- O chat de teste reutiliza as mesmas regras de dominio, memoria-chave e bloqueio de ambiguidade do backend.
- Antes de rodar, configure no `.env` o endpoint/modelos de teste (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_TEST_MODELS`).
- O build do EXE inclui `app/prompts/studio_agendamento.md`, mantendo o mesmo padrao de informacao do fluxo real.
- Build do executavel (CMD):

```cmd
road_test\build_chat_test_exe.cmd
```

- Executar:

```cmd
dist\chat_estudio_road_test.exe
```

- Atalho para iniciar modo leve local (sobe Ollama se precisar, garante modelo leve e abre chat):

```cmd
road_test\iniciar_leve_local.cmd
```

- Atalho para parar tudo (fecha chat, descarrega modelo e encerra Ollama):

```cmd
road_test\parar_tudo_local.cmd
```

## Chat em producao (Railway)

- Chat interativo direto no pipeline real (API + worker + llm-runtime):

```cmd
road_test\chat_railway_prod.cmd
```

- Rodada unica (retorna JSON com ids/status/modelo):

```cmd
road_test\chat_railway_prod.cmd --once "quero agendar ensaio e saber valor de 2 horas"
```

- Se quiser melhorar chance de dispatch outbound, informe o `phone_number_id`:

```cmd
road_test\chat_railway_prod.cmd --phone-number-id 1234567890 --once "teste com dispatch"
```

- Se o webhook estiver exigindo assinatura (`Invalid Meta signature`), informe tambem o app secret:

```cmd
road_test\chat_railway_prod.cmd --app-secret SEU_META_APP_SECRET --once "teste assinado"
```

- Bateria online de 100 testes guiada pelos erros mais frequentes do ultimo stress:

```cmd
.venv\Scripts\python.exe -u road_test\stress_locacao_error_guided_online.py --app-secret SEU_META_APP_SECRET
```

- Observacao de rede:
  - o script ignora proxy de ambiente por padrao (evita falha quando `HTTP_PROXY`/`HTTPS_PROXY` apontam para localhost invalido);
  - use `--trust-env` somente se voce realmente precisar forcar proxy corporativo.

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
- `POST /webhooks/evolution`

## OAuth Meta/Facebook

- Endpoint de inicio: `GET /oauth/meta/start` (alias: `GET /oauth/facebook/start`).
- Endpoint de callback: `GET /oauth/meta/callback` (alias: `GET /oauth/facebook/callback`).
- O callback valida `state` assinado com TTL e troca o `code` por token na Graph API.
- O token resultante e salvo em `platform_accounts.access_token_encrypted`.
- Os servicos de publicacao Instagram usam esse token salvo como fallback automatico.
- O canal WhatsApp usa a Evolution API para webhook inbound e dispatch outbound.
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
- `generate_reply` passou a usar LLM local/open source com contexto de conversa e lock de dominio para estudio/agendamento.
- Clientes agora possuem `customer_id` global e podem ser unificados por identidade de canal em `contact_identities` (WhatsApp/Instagram/Facebook).
- Memorias-chave por cliente sao persistidas em `contact_memories`, com bloqueio de persistencia para mensagens ambiguas.
