# Partner API Keys — Acesso Externo ao FCVIP

## Visão Geral

O sistema de Partner API Keys permite conceder acesso controlado à API do FCVIP para parceiros externos — analistas, ferramentas de BI e pipelines de treinamento de IA.

Autenticação via header HTTP:
```
Authorization: Api-Key <sua_key>
```

---

## Escopos disponíveis

| Escopo           | Acesso concedido                              |
|------------------|-----------------------------------------------|
| `analytics:read` | Dados agregados para análise e treinamento IA |
| `users:read`     | Leitura de dados de usuários                  |
| `billing:read`   | Leitura de dados de billing                   |

---

## Como gerar uma key

### Via painel administrativo
1. Acesse `/painel/api-keys/`
2. Preencha o nome, selecione os escopos e, se necessário, informe uma data de expiração.
3. Clique em **Criar**.
4. Copie a key completa exibida no alerta. Ela aparece somente uma vez.

Pelo mesmo painel também é possível editar nome/escopos/expiração, revogar uma key ativa ou excluir uma key definitivamente.

### Via admin Django
1. Acesse `/admin/api_keys/partnerapikey/`
2. Clique em **Add Partner API Key**
3. Preencha o nome do parceiro e os escopos desejados no campo `scopes` (ex: `["analytics:read"]`)
4. Salve — a key completa será exibida **uma única vez** na tela. Copie imediatamente.

### Via management command
```bash
python manage.py create_partner_key --name "Parceiro X" --scopes analytics:read users:read
```

Em producao Railway, rode pelo ambiente da Railway para gravar no banco correto:
```bash
railway run --service Vs --environment production \
  python manage.py create_partner_key --name "Parceiro X" --scopes analytics:read users:read
```

O `settings.py` ignora `.env.local` quando detecta variaveis Railway (`RAILWAY_ENVIRONMENT`, `RAILWAY_ENVIRONMENT_ID` ou `RAILWAY_SERVICE_ID`). Isso evita que comandos `railway run` sejam desviados para o banco local de desenvolvimento.

---

## Endpoints Partner API disponíveis

Base: `/api/partner/` — autenticação via `Authorization: Api-Key <key>`.

### `GET /api/partner/agenda/` — escopo `analytics:read`

Lista reservas de agenda. Filtros por query param:

| Param | Formato | Descrição |
|---|---|---|
| `data_inicio` | `AAAA-MM-DD` | Reservas com slot a partir desta data |
| `data_fim` | `AAAA-MM-DD` | Reservas com slot até esta data |
| `status` | `confirmada` \| `cancelada` | Status da reserva |
| `recurso` | slug | Filtra por recurso (ex: `estudio-principal`) |
| `page`, `page_size` | int | Paginação (max 200/página, default 50) |

Exemplo:
```bash
curl -H "Authorization: Api-Key <key>" \
  "https://vs-production-c4dd.up.railway.app/api/partner/agenda/?data_inicio=2026-04-01&status=confirmada"
```

### `GET /api/partner/clientes/` — escopo `users:read`

Lista clientes/usuários FCVIP. **Nunca retorna** `cpf`, `telefone`, `password`, `is_superuser`, `is_staff`.

Filtros:

| Param | Formato | Descrição |
|---|---|---|
| `plano` | `nao_membro` \| `membro` \| `admin` | Tipo de conta |
| `is_member` | `true` \| `false` | Se possui assinatura ativa |
| `cidade` | string | Filtra por cidade exata |
| `page`, `page_size` | int | Paginação |

### `GET /api/partner/billing/` — escopo `billing:read`

Lista eventos de billing. **Nunca retorna** `payload` bruto do gateway nem `gateway_event_id`.

Filtros: `tipo`, `data_inicio`, `data_fim`, `page`, `page_size`.

### `GET /api/partner/leads/` — escopo `analytics:read`

Lista leads capturados (incluindo os recebidos via `POST /api/bot/sync-cliente/`).

Filtros: `origem`, `data_inicio`, `data_fim`, `page`, `page_size`.

### Envelope de resposta

Todos os endpoints retornam o envelope padrão:

```json
{
  "success": true,
  "message": "Reservas listadas.",
  "data": {
    "reservas": [ ... ],
    "total": 42,
    "page": 1,
    "page_size": 50,
    "total_pages": 1
  }
}
```

---

## Como proteger um endpoint com API Key

```python
from api_keys.permissions import HasPartnerAPIKey, require_scope

# Aceita qualquer key válida
@api_view(["GET"])
@permission_classes([HasPartnerAPIKey])
def meu_endpoint(request):
    ...

# Exige escopo específico
@api_view(["GET"])
@permission_classes([require_scope("analytics:read")])
def endpoint_analytics(request):
    ...
```

---

## Segurança

- As keys são armazenadas como **hash** no banco — o valor original nunca é recuperável.
- Keys podem ser **revogadas** a qualquer momento pelo admin.
- Keys suportam **data de expiração** (`expiry_date`).
- O prefixo da key (ex: `fcvip.AbCdEf`) identifica o parceiro nos logs sem expor o segredo.

---

## Doctor check

O **DOCTOR** mostra `fcvip_api_token` como:
- ✅ `ok` — existe ao menos uma PartnerAPIKey ativa (não revogada)
- ⚠️ `warning` — nenhuma key ativa cadastrada

---

## Arquivos relevantes

| Arquivo | Descrição |
|---|---|
| `api_keys/models.py` | Model `PartnerAPIKey` com campo `scopes` |
| `api_keys/permissions.py` | `HasPartnerAPIKey` e `require_scope()` |
| `api_keys/serializers.py` | Serializers de saída sem campos sensíveis |
| `api_keys/services.py` | Querysets filtrados (lógica fora das views) |
| `api_keys/pagination.py` | Helper de paginação reutilizável |
| `api_keys/views.py` | 4 views finas dos endpoints Partner |
| `api_keys/urls.py` | Rotas registradas em `/api/partner/` |
| `api_keys/admin.py` | Interface admin para gerenciar keys |
| `tests/test_partner_api.py` | 12 testes de contrato e segurança |
