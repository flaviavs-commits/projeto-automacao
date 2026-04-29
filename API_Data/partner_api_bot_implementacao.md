# API de Dados para Dev de IA — Plano de Implementação

> Baseado no documento "Detalhes Técnicos: FastAPI e Django"

---

## Visão Geral

Dois fluxos de integração entre o microserviço FastAPI (bot/IA) e o Django (FCVIP):

| Track | Direção | Objetivo |
|---|---|---|
| **A** | FastAPI → Django | Bot envia dados de leads/clientes para sincronizar |
| **B** | Django → IA | Dev de IA lê dados via Partner API Keys |

---

## Track A — Integração Bot → Django (PUSH)

### A1. Autenticação M2M — `IsBotService`

**Arquivo novo:** `bot/permissions.py`

- Lê o header `X-Service-Token` da requisição
- Compara com `settings.BOT_INTEGRATION_TOKEN` via `hmac.compare_digest` (proteção contra timing attack)
- Aplicado como `@permission_classes([IsBotService])` nos endpoints do bot

**Arquivo novo:** `bot/throttles.py`

- Classe `BotServiceThrottle` — limite de **100 req/min**
- Cache key baseada no IP do serviço FastAPI

**Adições em `settings.py`:**
```
BOT_INTEGRATION_TOKEN = env("BOT_INTEGRATION_TOKEN")
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["bot_service"] = "100/min"
```

---

### A2. Endpoint de Upsert Atômico

**`POST /api/bot/sync-cliente/`**

**Arquivo novo:** `bot/views.py`

**Fluxo:**
1. Valida payload com `SyncClienteSerializer`
2. Dentro de `transaction.atomic()`:
   - Match por `email` OR `whatsapp` no banco
   - **Se não existe:** cria usuário com `origem=payload["origem"]`
   - **Se existe (merge):** aplica `setattr` apenas se campo atual é `None` ou `""` — nunca sobrescreve `is_member`, `plano`, `membership_locked`, `password`
3. Retorna `api_success(data={"id": usuario.id, "action": "created" | "updated"})`

**Campos aceitos no payload:**
```json
{
  "email": "...",
  "nome": "...",
  "whatsapp": "...",
  "telefone": "...",
  "cpf": "...",
  "instagram": "...",
  "cidade": "...",
  "origem": "bot_whatsapp"
}
```

**Arquivo novo:** `bot/serializers.py` — `SyncClienteSerializer` valida e normaliza antes do upsert.

---

### A3. Audit Trail

Reutiliza `UserActivityLog` existente (`accounts/models.py`).

Após cada upsert, registra:
```python
UserActivityLog.objects.create(
    user=usuario,
    event_type="BOT_SYNC",
    status="success",
    metadata={
        "action": "created" | "updated",
        "fields_changed": [...],
        "origem": payload["origem"]
    }
)
```

**Modificação necessária:** adicionar choice `BOT_SYNC` em `UserActivityLog.event_type` + migration.

---

### A4. BotAIClient — Proxy Django → FastAPI

**Arquivo:** `assistant/integrations.py` (adicionar classe)

Django encaminha perguntas do usuário ao FastAPI ao invés de chamar OpenAI diretamente:

```python
class BotAIClient:
    """Cliente HTTP para o microserviço FastAPI de IA."""

    def ask(self, question: str, context: dict) -> str:
        try:
            resp = httpx.post(
                f"{settings.BOT_AI_BASE_URL}/responder",
                json={"pergunta": question, "contexto": context},
                timeout=settings.BOT_AI_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()["resposta"]
        except httpx.TimeoutException:
            return "Nossos servidores estão processando muita informação. Tente novamente em instantes."
        except Exception:
            raise AssistantSetupError("Falha na comunicação com o serviço de IA.")
```

**Adições em `settings.py`:**
```
BOT_AI_BASE_URL = env("BOT_AI_BASE_URL", default="")
BOT_AI_TIMEOUT  = env.int("BOT_AI_TIMEOUT", default=30)
```

O `assistant_ask_view` existente usa `BotAIClient` como alternativa ao OpenAI — sem mudança na interface pública.

---

## Track B — Partner API (IA lê dados do Django)

Autenticação via **Partner API Key** com escopo no header:
```
Authorization: Api-Key <sua_key>
```

Todos os endpoints ficam em `api_keys/views.py`, registrados em `/api/partner/`.

---

### B1. `GET /api/partner/agenda/`

**Escopo:** `analytics:read`

**Retorna:** reservas e slots de agenda

```json
{
  "reservas": [
    {
      "id": 1,
      "slot_inicio": "2026-05-01T10:00:00Z",
      "slot_fim": "2026-05-01T11:00:00Z",
      "recurso": "estudio-a",
      "status": "CONFIRMADA",
      "kit_type": "ESSENCIAL",
      "tipo_sessao": "retrato",
      "origem": "site",
      "criado_em": "2026-04-20T14:00:00Z"
    }
  ],
  "total": 42,
  "page": 1
}
```

**Query params:** `?data_inicio=` `?data_fim=` `?status=` `?recurso=` `?page=`
**Paginação:** 50 registros/página

---

### B2. `GET /api/partner/clientes/`

**Escopo:** `users:read`

**Retorna:** membros FCVIP (sem dados sensíveis)

```json
{
  "clientes": [
    {
      "id": 123,
      "email": "...",
      "nome": "...",
      "plano": "MEMBRO",
      "is_member_active": true,
      "account_tier": 2,
      "cidade": "SP",
      "instagram": "@...",
      "member_since": "2025-01-01T00:00:00Z",
      "criado_em": "2024-11-01T00:00:00Z"
    }
  ],
  "total": 300,
  "page": 1
}
```

**Campos NUNCA retornados:** `password`, `cpf`, `telefone`, `is_superuser`, `is_staff`

**Query params:** `?plano=` `?is_member=` `?cidade=` `?page=`

---

### B3. `GET /api/partner/billing/`

**Escopo:** `billing:read`

**Retorna:** eventos de billing (sem payload sensível)

```json
{
  "eventos": [
    {
      "tipo": "PAYMENT_SUCCEEDED",
      "gateway": "stripe",
      "criado_em": "2026-04-28T10:00:00Z"
    }
  ],
  "total": 150,
  "page": 1
}
```

**Campos NUNCA retornados:** `payload` completo, `gateway_event_id` raw

**Query params:** `?tipo=` `?data_inicio=` `?data_fim=` `?page=`

---

### B4. `GET /api/partner/leads/`

**Escopo:** `analytics:read`

**Retorna:** leads capturados (`accounts.Lead`)

```json
{
  "leads": [
    {
      "id": 1,
      "email": "...",
      "nome": "...",
      "whatsapp": "...",
      "origem": "bot_whatsapp",
      "criado_em": "2026-04-15T..."
    }
  ],
  "total": 80,
  "page": 1
}
```

---

## Mapa de Arquivos

| Arquivo | Ação | Descrição |
|---|---|---|
| `bot/` | Criar app | Nova app Django para integração bot |
| `bot/permissions.py` | Criar | `IsBotService` com HMAC |
| `bot/throttles.py` | Criar | `BotServiceThrottle` 100/min |
| `bot/views.py` | Criar | `sync_cliente_view` com atomic upsert |
| `bot/serializers.py` | Criar | `SyncClienteSerializer` |
| `bot/urls.py` | Criar | Rota `sync-cliente/` |
| `api_keys/views.py` | Modificar | 4 endpoints Partner API |
| `api_keys/urls.py` | Criar | Rotas `/agenda/`, `/clientes/`, `/billing/`, `/leads/` |
| `assistant/integrations.py` | Modificar | Adicionar `BotAIClient` |
| `accounts/models.py` | Modificar | Choice `BOT_SYNC` em `UserActivityLog.event_type` |
| `accounts/migrations/` | Criar | Migration para novo choice |
| `fcvip_backend/urls.py` | Modificar | Registrar `bot.urls` e `api_keys.urls` |
| `fcvip_backend/settings.py` | Modificar | `BOT_INTEGRATION_TOKEN`, `BOT_AI_*`, throttle rate |

---

## Verificação

```bash
# 1. Criar Partner API Key via admin Django
python manage.py create_partner_key --name "Dev IA" --scopes analytics:read users:read billing:read

# 2. Testar endpoints de leitura
curl -H "Authorization: Api-Key <key>" /api/partner/agenda/
curl -H "Authorization: Api-Key <key>" /api/partner/clientes/
curl -H "Authorization: Api-Key <key>" /api/partner/billing/
curl -H "Authorization: Api-Key <key>" /api/partner/leads/

# 3. Testar upsert do bot
curl -X POST /api/bot/sync-cliente/ \
  -H "X-Service-Token: <BOT_INTEGRATION_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@test.com", "nome": "Teste", "origem": "bot_whatsapp"}'

# 4. Verificar audit log no admin Django
# Admin > Accounts > UserActivityLog > filtrar por event_type=BOT_SYNC

# 5. Testar proteções
curl /api/bot/sync-cliente/            # → 403 (sem token)
curl /api/partner/clientes/            # → 403 (sem key)
curl -H "Authorization: Api-Key <key_com_analytics>" /api/partner/clientes/  # → 403 (escopo errado)
```
