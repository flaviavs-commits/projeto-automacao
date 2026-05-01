# Integracao com API FC VIP

## Objetivo

Documentar a integracao que consulta dados de clientes na API parceira FC VIP (ex.: identificar se um telefone ja existe como cliente antigo).

## Arquivos principais

- Servico da integracao: `app/services/fcvip_partner_api_service.py`
- Base HTTP/retries: `app/services/base.py`
- Uso no dashboard OP (snapshot de cliente): `app/services/dashboard_op_service.py`
- Testes: `tests/test_fcvip_partner_api_service.py`
- Variaveis de ambiente: `.env.example`

## Variaveis de ambiente

- `FCVIP_PARTNER_API_ENABLED` (default: `true`)
- `FCVIP_PARTNER_API_BASE_URL`
- `FCVIP_PARTNER_API_KEY`
- `FCVIP_PARTNER_API_TIMEOUT_SECONDS` (default: `12`)
- `FCVIP_PARTNER_API_PAGE_SIZE` (default: `50`)
- `FCVIP_PARTNER_API_LEADS_MAX_PAGES` (default: `3`)

| Variavel | Uso | Exemplo |
|---|---|---|
| `FCVIP_PARTNER_API_ENABLED` | Habilita/desabilita integracao | `true` |
| `FCVIP_PARTNER_API_BASE_URL` | Base da API parceira | `https://vs-production-c4dd.up.railway.app` |
| `FCVIP_PARTNER_API_KEY` | Chave de autenticacao | `partner-test-key` |
| `FCVIP_PARTNER_API_TIMEOUT_SECONDS` | Timeout HTTP | `12` |
| `FCVIP_PARTNER_API_PAGE_SIZE` | Quantidade por pagina | `50` |
| `FCVIP_PARTNER_API_LEADS_MAX_PAGES` | Max paginas por consulta | `3` |

## Endpoint externo utilizado

- Metodo: `GET`
- URL base: `${FCVIP_PARTNER_API_BASE_URL}/api/partner/leads/`
- Auth header:
  - `Authorization: Api-Key <FCVIP_PARTNER_API_KEY>`
- Query params:
  - `page`
  - `page_size`

| Item | Valor |
|---|---|
| Metodo | `GET` |
| Endpoint | `/api/partner/leads/` |
| Header auth | `Authorization: Api-Key <key>` |
| Query params | `page`, `page_size` |

## Contrato esperado da resposta

Envelope esperado (resumo):

```json
{
  "success": true,
  "data": {
    "leads": [
      { "id": 123, "whatsapp": "5511999999999" }
    ],
    "total_pages": 3
  }
}
```

Campos usados na leitura de telefone do lead:

- `whatsapp`
- `telefone`
- `phone`

## Regra de negocio aplicada

Fluxo de `lookup_customer_by_whatsapp(phone_number=...)`:

1. Normaliza telefone de entrada (somente digitos).
2. Verifica cache curto in-memory.
3. Valida se integracao esta habilitada e com credenciais.
4. Pagina em `/api/partner/leads/` ate `FCVIP_PARTNER_API_LEADS_MAX_PAGES`.
5. Se encontrar telefone:
   - `customer_exists=true`
   - `customer_status="antigo"`
6. Se nao encontrar:
   - `customer_exists=false`
   - `customer_status="novo"`

Comparacao de telefone:

- match exato de digitos, ou
- match pelos ultimos 10 digitos (fallback).

## Resiliencia

- Retry automatico em falhas de rede/timeout/5xx.
- Backoff curto por tentativa.
- Cache in-memory por 90 segundos para reduzir chamadas repetidas.

## Formato de retorno interno

O servico retorna `ExternalServiceResult` com campos como:

- `status` (`completed`, `request_failed`, `missing_credentials`, `integration_disabled`, etc.)
- `customer_exists`
- `customer_status`
- `matched_lead_id` (quando aplicavel)
- `checked_pages`

| Campo | Significado |
|---|---|
| `status` | Resultado tecnico da chamada (`completed`, `request_failed`, etc.) |
| `customer_exists` | Se o cliente foi encontrado na base FC VIP |
| `customer_status` | Classificacao de negocio (`antigo`/`novo`) |
| `matched_lead_id` | ID do lead encontrado no parceiro |
| `checked_pages` | Quantas paginas foram lidas na busca |

## Onde aparece no produto

No painel OP, detalhe de cliente (`/dashboard/op/contacts/{contact_id}`):

- bloco `fcvip_api` com snapshot da consulta.
- mensagem amigavel quando indisponivel ou sem telefone.

## Testes existentes

`tests/test_fcvip_partner_api_service.py` cobre:

- credenciais ausentes;
- cliente encontrado;
- cliente nao encontrado;
- erro do parceiro (ex.: 403);
- retry em erro 5xx;
- cache curto.

## Troubleshooting rapido

- `missing_credentials`:
  - revisar `FCVIP_PARTNER_API_BASE_URL` e `FCVIP_PARTNER_API_KEY`.
- `request_failed` com status HTTP:
  - validar API key, rota e disponibilidade do parceiro.
- retorno sem `data.leads`:
  - contrato do parceiro mudou; revisar parser (`_extract_leads_payload`).
