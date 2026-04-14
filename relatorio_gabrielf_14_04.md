# Relatorio Diario - Gabriel F

- Data: 14/04/2026
- Projeto: intelligent-vitality (Railway)
- Repositorio: flaviavs-commits/projeto-automacao

## Resumo Executivo

O dia deixou um ponto cristalino: o principal impeditivo atual do projeto e a conexao com a Meta.

- O LLM ja esta em producao (Railway) e esta operacional para atuar como agente inteligente no fluxo interno (webhook -> worker -> LLM -> persistencia).
- A maior dificuldade continua sendo a Meta: ainda nao foi possivel conectar 100% os produtos (WhatsApp e Instagram) de forma consistente ponta a ponta (entrada e saida) sem depender de ajustes externos, permissoes e configuracao de conta.

As frentes executadas no dia foram:
1. Estabilizacao e validacao do LLM em producao Railway (pronto para uso como agente inteligente).
2. Endurecimento de observabilidade/QA da conexao Meta (WhatsApp/Instagram) para expor o erro real (sem maquiagem).

Resultado pratico do fechamento do dia:
- pipeline interno da API/worker continua funcional;
- erro real de envio WhatsApp foi confirmado e agora aparece explicitamente no QA;
- ausencia de DM Instagram tambem passou a ser erro explicito no QA;
- o bloqueio dominante para fechar o ciclo com `FAIL=0` segue sendo a Meta (configuracao, permissoes e/ou eventos nao chegando).

## Objetivos Tecnicos do Dia

1. Validar operacao real em producao apos melhorias de qualidade do LLM.
2. Garantir que o dashboard operacional seja o ponto central de trabalho de mensagens.
3. Implementar prova de conexao Meta de ida e volta no backend.
4. Fazer o QA reportar erro real com codigo, local e explicacao simples para usuario semi leigo.

## Cronologia Tecnica das Entregas

### 1) Frente LLM em producao (Railway)

- Commit principal de melhoria de qualidade do LLM:
  - `a580574` (`feat: improve llm reply quality with fallback model retry`)
- Commit de consolidacao da validacao em producao:
  - `013ce1e` (`docs: log production validation for llm quality fallback`)
- Deploy manual confirmado no Railway:
  - API: `256a9d92-8636-4d51-a2bc-d312c78c6139`
  - worker: `30e9419e-4ff2-4561-a5c9-e4c04107e761`
- Estado final dos servicos nessa etapa: `SUCCESS`.

Validacao feita:
- `GET /health` com `status=ok`.
- webhook real aceito (`202`) e processado pelo worker.
- log de worker confirmando fluxo `process_incoming_message` completo.
- evidencia de uso de fallback de modelo em runtime real.

Status desta frente no fim do dia:
- LLM pronto para ser usado como agente inteligente em producao (sem depender de maquina local).
- Este nao e o impeditivo atual do projeto; o impeditivo atual e a Meta (WhatsApp/Instagram).

### 2) Ferramenta operacional para conversa com producao

- Entregue:
  - `road_test/chat_railway_prod.py`
  - `road_test/chat_railway_prod.cmd`
- Objetivo:
  - permitir teste real via CLI no fluxo webhook -> worker -> LLM sem depender de interface externa.
- Validacao:
  - execucao `--once` retornando `llm_status=completed` e ids de rastreio de mensagem.

### 3) Dashboard operacional de mensagens (central OP)

- Dashboard evoluido para operar conversas e envio outbound por dentro da aplicacao:
  - leitura de estado operacional por conversa;
  - listagem de mensagens por conversa;
  - envio outbound via endpoint operacional.
- Arquivo principal desta frente:
  - `app/api/routes/dashboard.py`

Ponto relevante:
- envio outbound feito pelo dashboard registra `dispatch_status` e `dispatch_result` no `raw_payload` da mensagem, o que virou fonte primaria de diagnostico no QA.

### 4) Sinal live Meta (ida e volta) no backend

- Novo servico:
  - `app/services/meta_live_service.py`
- Novos endpoints:
  - `GET /health/meta-live/outbound`
  - `GET /health/meta-live/inbound`
  - `GET /health/meta-live`
- Endpoint `/health` enriquecido com sinais de credencial resolvida e readiness efetiva.

Cobertura entregue:
- prova de saida para Graph API (`/me` + probe de numero quando disponivel);
- prova de entrada por evidencias recentes de webhook em `audit_logs`;
- status combinado (`ok`, `degraded`, `fail`).

Motivo desta frente ser critica:
- a Meta e hoje o gargalo principal: sem fechar WhatsApp/Instagram 100% conectados, o sistema nao vira "operacao diaria" real somente pelo dashboard.

### 5) Robustez de token Meta e fonte de credenciais

- `PlatformAccountService` ganhou:
  - tentativa de refresh de token long-lived em janela de renovacao;
  - resolvedor unico de credenciais (`resolve_meta_credentials`).
- `WhatsAppService` e `InstagramPublishService` passaram a usar o resolvedor unico.
- Isso reduziu inconsistencias de prioridade entre token de ambiente e token OAuth persistido.

Arquivos:
- `app/services/platform_account_service.py`
- `app/services/whatsapp_service.py`
- `app/services/instagram_publish_service.py`

### 6) Auditoria de falha de assinatura do webhook

- `webhooks_meta` passou a registrar evento de auditoria quando assinatura Meta e invalida:
  - `event_type=meta_webhook_invalid_signature`
- Arquivo:
  - `app/api/routes/webhooks_meta.py`

Impacto:
- agora existe evidencia rastreavel no banco para falha de assinatura, usada diretamente no `meta-live`.

### 7) Base de erros externos mais explicita

- `BaseExternalService` passou a extrair e carregar `error_meta` nos erros HTTP:
  - `code`, `error_subcode`, `message`, `fbtrace_id`.
- Arquivo:
  - `app/services/base.py`

Impacto:
- QA e dashboard passaram a ter diagnostico util para erro Meta sem depender de leitura manual de log bruto.

### 8) QA reforcado para erro real (sem maquiagem)

- `qa_tudo.py` recebeu ampliacoes estruturais:
  - secao "Resumo Simples";
  - secao "Tela de Erros";
  - parse de codigo HTTP/META e local da falha;
  - explicacao simplificada + causa mais provavel.
- Novos checks remotos criticos:
  - `Meta Live / Sinal ida/volta Meta`
  - `Meta Live / WhatsApp dispatch (falhas reais)`
  - `Meta Live / Instagram DM entrada`

Comportamento final:
- falha de dispatch WhatsApp real vira `FAIL` automatico;
- falta de inbound Instagram em janela valida vira `FAIL` automatico;
- erro mostra local, codigo e detalhe tecnico.

## Validacao Objetiva do Fechamento do Dia

Execucao de QA mais recente (14/04/2026, ~16:24 BRT):
- comando: `cmd /c .\\.venv\\Scripts\\python.exe qa_tudo.py --no-dashboard --no-pause`
- resultado: `PASS=11`, `WARN=2`, `FAIL=2`
- relatorio: `qa_report_latest.json`

Falhas reais registradas:
1. WhatsApp dispatch:
- evidencias:
  - `status_code=400`
  - `code=131030`
  - `message=(#131030) Recipient phone number not in allowed list`
  - `fbtrace_id=AnMIxXRjwPGnPeX6wnI1HXv`
- houve tambem erro historico recente:
  - `status_code=401`
  - `code=190`
  - `error_subcode=463`
  - token expirado no horario informado pela Meta.

2. Instagram inbound:
- `instagram_ready=True` no `/health`
- `inbound_count=0` na janela de verificacao
- resultado: sem prova de DM chegando no dashboard no periodo validado.

Interpretacao objetiva:
- O sistema esta "vivo" e funcional internamente (LLM e pipeline), mas a camada Meta ainda nao esta 100% conectada (WhatsApp/Instagram).
- Por isso o QA fecha com `FAIL=2`: nao e bug interno mascarado; e bloqueio real de integracao/conta/escopo/eventos.

Warns:
1. Railway CLI sem sessao valida local (`railway login`).
2. Meta inbound sem evento recente suficiente para prova continua em uma das janelas de checagem.

## Evidencias de Commits do Dia (main)

- `a580574` - `feat: improve llm reply quality with fallback model retry`
- `013ce1e` - `docs: log production validation for llm quality fallback`
- `b4dcb8c` - `feat: harden production flow and WhatsApp readiness`
- `08cccfe` - `feat: support signed webhook in production chat tool`

## Arquivos Principais Trabalhados no Dia

- `app/api/routes/dashboard.py`
- `app/api/routes/health.py`
- `app/api/routes/webhooks_meta.py`
- `app/services/base.py`
- `app/services/platform_account_service.py`
- `app/services/whatsapp_service.py`
- `app/services/instagram_publish_service.py`
- `app/services/meta_live_service.py` (novo)
- `qa_tudo.py`
- `.railwayignore` (novo)
- `road_test/build_qa_tudo_exe.cmd` (novo)

## Itens Nao Concluidos (Estado Atual)

1. WhatsApp outbound ainda bloqueado para numero fora da allow list de teste (`131030`).
2. Entrada de DM Instagram ainda sem evidencia de entrega no periodo validado pelo QA.
3. Sessao local do Railway CLI expirando/intermitente para alguns checks de operacao.
4. QA ainda nao fecha em `FAIL=0` por dependencia de configuracao externa da Meta.

## Riscos Tecnicos Abertos

1. Percepcao de saude falsa se houver apenas check de endpoint sem check de erro funcional de mensagem.
2. Token Meta expirado pode degradar envio de forma silenciosa se nao houver monitoramento de codigo `190/463`.
3. Webhook pode estar "configurado" mas sem entrega efetiva de DM Instagram, mantendo lacuna operacional.

## Proximos Passos Recomendados (P0/P1)

1. P0: liberar numero destino no ambiente de teste WhatsApp Cloud API para remover `131030`.
2. P0: validar assinatura e subscriptions de webhook Instagram Messaging ate `inbound_count>0` no QA.
3. P0: repetir QA completo apos ajustes externos e perseguir `FAIL=0`.
4. P1: manter monitoramento de expirar token Meta e confirmar refresh persistido em runtime.
5. P1: consolidar checklist operacional de Meta (escopos, app mode, webhook, allow list, phone id) para reduzir regressao.

## Conclusao do Dia

O dia entregou evolucao forte de governanca tecnica: o sistema agora mostra erro real de integracao em vez de aparentar saude por endpoint "200".

Estado atual, sem ambiguidade:
- O LLM ja esta em producao e pronto para atuar como agente inteligente (pipeline interno OK).
- O principal impeditivo do projeto hoje e a Meta: a conexao ainda nao esta 100% fechada e confiavel para WhatsApp e Instagram.
- As falhas centrais (dispatch WhatsApp e inbound Instagram) estao explicitamente detectadas e rastreadas no QA com codigo, local e causa provavel.
- A resolucao final depende de fechar configuracao/permissoes/eventos na Meta, nao de falta de capacidade do LLM ou do backend/QA.
