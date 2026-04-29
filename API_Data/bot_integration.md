# Integração FastAPI ↔ Django (Bot/IA)

## Visão Geral

Contrato server-to-server entre o microserviço FastAPI (bot WhatsApp / IA) e o backend Django (FCVIP). Cobre dois fluxos:

| Fluxo | Endpoint | Descrição |
|---|---|---|
| **Bot → Django** | `POST /api/bot/sync-cliente/` | Bot envia leads/clientes para o Django sincronizar |
| **Django → Bot** | `BotAIClient` (Python) | Django consulta o microserviço FastAPI para gerar respostas de IA |

Para os endpoints de leitura (`GET /api/partner/*`) usados pelo dev de IA, ver [`partner_api_keys.md`](./partner_api_keys.md).

---

## Configuração (variáveis de ambiente)

| Variável | Default | Descrição |
|---|---|---|
| `BOT_INTEGRATION_TOKEN` | `""` | Token compartilhado entre FastAPI e Django (header `X-Service-Token`) |
| `BOT_AI_BASE_URL` | `""` | URL base do microserviço FastAPI (ex: `https://bot.example.com`) |
| `BOT_AI_TIMEOUT` | `30` | Timeout em segundos para chamadas Django→FastAPI |

---

## `POST /api/bot/sync-cliente/`

Recebe payload do bot e executa **upsert atômico** de Lead + merge conservador no Usuario quando já existir.

### Headers

```
Content-Type: application/json
X-Service-Token: <BOT_INTEGRATION_TOKEN>
```

### Body

```json
{
  "email": "cliente@x.com",
  "nome": "Nome Completo",
  "whatsapp": "11999999999",
  "telefone": "11999999999",
  "cpf": "00000000000",
  "instagram": "usuario",
  "cidade": "Sao Paulo",
  "origem": "bot_whatsapp"
}
```

| Campo | Obrigatório | Notas |
|---|---|---|
| `email` | ✅ | Chave primária de match |
| `nome` | ❌ | |
| `whatsapp` / `telefone` | ❌ | Aceita ambos; mapeados para `Usuario.telefone` |
| `cpf` | ❌ | Validado e normalizado |
| `instagram` | ❌ | |
| `cidade` | ❌ | |
| `origem` | ❌ | Default `bot` |

### Resposta de sucesso (HTTP 200)

```json
{
  "success": true,
  "message": "Cliente sincronizado.",
  "data": {
    "lead_id": 1,
    "lead_action": "created",
    "usuario_id": 42,
    "usuario_action": "merged",
    "fields_changed": ["telefone", "cidade"]
  }
}
```

| Campo | Valores possíveis |
|---|---|
| `lead_action` | `created` \| `updated` |
| `usuario_action` | `merged` \| `no_changes` \| `no_match` |
| `usuario_id` | id do Usuario quando há match, senão `null` |
| `fields_changed` | Lista dos campos atualizados via merge conservador |

### Erros

| Status | Cenário |
|---|---|
| `400` | Payload inválido (sem `email`, CPF/telefone com formato errado) |
| `403` | `X-Service-Token` ausente ou inválido |
| `429` | Throttle excedido (limite 100 req/min por IP) |

### Garantias

- **Atômico**: tudo dentro de `transaction.atomic()` — falha intermediária faz rollback.
- **Idempotente por email**: chamadas repetidas com o mesmo payload não duplicam Lead.
- **Merge conservador no Usuario**: só preenche campos vazios. Nunca toca em `password`, `is_member`, `plano`, `membership_locked`, `email_verificado`, `is_staff`, `is_superuser`, `site_cadastro`.
- **Auditoria**: cada chamada cria entrada em `UserActivityLog` com `event_type=BOT_SYNC` contendo `lead_action`, `usuario_action`, `fields_changed`, `origem`.

### Exemplo

```bash
curl -X POST https://vs-production-c4dd.up.railway.app/api/bot/sync-cliente/ \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: $BOT_INTEGRATION_TOKEN" \
  -d '{
    "email": "cliente@x.com",
    "nome": "Cliente Teste",
    "whatsapp": "11999998888",
    "origem": "bot_whatsapp"
  }'
```

---

## `BotAIClient` (Django → FastAPI)

Cliente HTTP em `assistant/integrations.py` que encaminha perguntas do site ao microserviço FastAPI, isolando o custo de LLM da infraestrutura web.

### Uso

```python
from assistant.integrations import BotAIClient

client = BotAIClient()
if client.is_configured:
    resposta = client.ask("Qual o horário de funcionamento?", contexto={"user_id": 42})
```

### Comportamento defensivo

- **Timeout padrão de 30s** (configurável via `BOT_AI_TIMEOUT`).
- Em **timeout** ou **HTTP 5xx** retorna mensagem amigável sem levantar exceção: `"Nossos servidores estão processando muita informação..."`.
- Em **HTTP 4xx**, falha de rede ou resposta inválida levanta `AssistantSetupError` para a view tratar com envelope padrão.

### Contrato esperado do FastAPI

```http
POST {BOT_AI_BASE_URL}/responder
Content-Type: application/json
X-Service-Token: {BOT_INTEGRATION_TOKEN}

{ "pergunta": "...", "contexto": {...} }
```

Resposta:
```json
{ "resposta": "..." }
```

---

## Arquivos relevantes

| Arquivo | Descrição |
|---|---|
| `bot/permissions.py` | `IsBotService` (HMAC do header `X-Service-Token`) |
| `bot/throttles.py` | `BotServiceThrottle` 100/min |
| `bot/serializers.py` | `SyncClienteSerializer` |
| `bot/services.py` | `sincronizar_cliente_do_bot` (upsert atômico) |
| `bot/views.py` | `sync_cliente_view` |
| `bot/urls.py` | Rotas em `/api/bot/` |
| `assistant/integrations.py` | `BotAIClient` (proxy Django→FastAPI) |
| `accounts/models.py` | `UserActivityLog.EventTypeChoices.BOT_SYNC` |
| `tests/test_bot_permissions.py` | 4 testes do `IsBotService` |
| `tests/test_bot_sync_cliente.py` | 8 testes do upsert atômico |
| `tests/test_bot_ai_client.py` | 9 testes do `BotAIClient` |
