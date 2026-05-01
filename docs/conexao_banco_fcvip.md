# Conexao entre Banco do Projeto e API FC VIP

## Objetivo

Este documento consolida como os dados da API FC VIP entram no sistema, como sao cruzados com o banco local e onde aparecem no produto.

## Visao de ponta a ponta

| Etapa | Origem | Regra | Destino |
|---|---|---|---|
| 1. Entrada | Banco local (`contacts.phone`) | Telefone do cliente ativo | `lookup_customer_by_whatsapp()` |
| 2. Chamada externa | API FC VIP `/api/partner/leads/` | Auth por `Api-Key`, paginacao | Payload de leads |
| 3. Matching | Comparacao de telefone | Match exato ou ultimos 10 digitos | `customer_exists`/`customer_status` |
| 4. Exibicao | `dashboard_op_service` | Snapshot sem persistencia da resposta bruta | Bloco `fcvip_api` no detalhe do cliente |

## Arquivos envolvidos

| Camada | Arquivo | Papel |
|---|---|---|
| Config | `app/core/config.py` | Carrega variaveis `FCVIP_PARTNER_API_*` |
| HTTP base | `app/services/base.py` | Cliente HTTP, normalizacao de retorno e falhas |
| Integracao FC VIP | `app/services/fcvip_partner_api_service.py` | Consulta paginada e classificacao `novo/antigo` |
| Banco local | `app/models/contact.py` | Fonte do telefone local |
| Dashboard OP | `app/services/dashboard_op_service.py` | Consome a integracao e monta `fcvip_api` |
| Testes | `tests/test_fcvip_partner_api_service.py` | Garante comportamento da integracao |

## Variaveis e impacto

| Variavel | Obrigatoria | Impacto quando ausente/errada |
|---|---|---|
| `FCVIP_PARTNER_API_ENABLED` | Nao | Se `false`, integracao retorna `integration_disabled` |
| `FCVIP_PARTNER_API_BASE_URL` | Sim | Retorna `missing_credentials` |
| `FCVIP_PARTNER_API_KEY` | Sim | `missing_credentials` ou `request_failed` (403) |
| `FCVIP_PARTNER_API_TIMEOUT_SECONDS` | Nao | Timeout mais agressivo/lento |
| `FCVIP_PARTNER_API_PAGE_SIZE` | Nao | Menos/mais itens por pagina |
| `FCVIP_PARTNER_API_LEADS_MAX_PAGES` | Nao | Limita profundidade da busca |

## Mapeamento de campos (API -> regra -> saida)

| Campo API parceiro | Transformacao | Campo final interno |
|---|---|---|
| `lead.whatsapp` / `lead.telefone` / `lead.phone` | Normaliza para digitos | Base para matching |
| `lead.id` | Sem transformacao | `matched_lead_id` |
| `data.total_pages` | Inteiro > 0 | Controle de paginacao |
| Match encontrado | `customer_exists=true` | `customer_status="antigo"` |
| Match nao encontrado | `customer_exists=false` | `customer_status="novo"` |

## Tabelas locais tocadas nessa conexao

| Tabela local | Leitura/Escrita | Observacao |
|---|---|---|
| `contacts` | Leitura | Usa `phone` para consultar API FC VIP |
| `conversations` | Leitura indireta | Contexto da tela de detalhe no dashboard |
| `appointments` | Sem dependencia direta | Agenda usa dados locais; FC VIP complementa perfil |
| `audit_logs` | Opcional em outros fluxos | Nao grava resposta FC VIP por padrao nesse fluxo |

## Contrato de retorno usado no app

| Campo | Exemplo | Uso na interface |
|---|---|---|
| `status` | `completed` | Define se snapshot e valido |
| `customer_exists` | `true` | Mostra "Cliente FC VIP: Sim" |
| `customer_status` | `antigo` | Mostra status FC VIP |
| `matched_lead_id` | `123` | Rastreabilidade tecnica |
| `checked_pages` | `2` | Diagnostico de busca |

## Resiliencia e limites

| Mecanismo | Implementacao | Beneficio |
|---|---|---|
| Retry | Tentativas extras em timeout/5xx | Reduz falso negativo por instabilidade |
| Cache curto | 90 segundos em memoria | Reduz volume de chamadas repetidas |
| Normalizacao de telefone | Digitos e fallback por ultimos 10 | Melhora taxa de match |
| Validacao de envelope | Exige `data.leads` | Evita quebrar com payload invalido |

## Erros comuns e acao

| Sintoma | Causa provavel | Acao recomendada |
|---|---|---|
| `missing_credentials` | Base URL/API key ausente | Preencher `FCVIP_PARTNER_API_BASE_URL` e `FCVIP_PARTNER_API_KEY` |
| `request_failed` 401/403 | Chave invalida | Regenerar/validar API key |
| `request_failed` timeout/connection | Rede ou parceiro instavel | Revisar timeout e conectividade |
| `invalid_partner_envelope` | Contrato da API mudou | Ajustar parser `_extract_leads_payload` |

## Referencias cruzadas

- Documento de banco: `docs/database.md`
- Documento da API FC VIP: `apifcvip.md`
