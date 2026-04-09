# Contexto IA - bot-multiredes

## Regra operacional permanente

- Sempre que o usuario solicitar o relatorio pessoal no padrao `relatorio_gabrielf_dd_mm.md`, atualizar tambem este arquivo `ia.md` na mesma sessao.
- O `ia.md` deve refletir o estado tecnico mais recente (infra, deploy, bloqueios, status de endpoints e proximos passos).
- Toda task executada deve ser registrada tambem em `ia.md` e `humano.md` antes de encerrar a entrega.

## Escopo do projeto

Backend centralizado para automacao multi-redes com:
- WhatsApp (webhook e resposta automatica futura)
- Instagram (mensageria e publicacao futura)
- TikTok (publicacao futura)
- YouTube (publicacao e comentarios futuros)
- memoria de conversas
- dashboard central
- fila assincrona
- deploy no Railway

## Arquitetura atual

- API: FastAPI (`app.main:app`)
- Fila: Redis + Celery (`app/workers`)
- Persistencia: PostgreSQL + SQLAlchemy
- Migracoes: Alembic
- Config: Pydantic Settings por `.env`

## Estado validado nesta rodada

- Import de `app.main`, `app.workers.celery_app` e `app.workers.tasks` funciona.
- `APP_PORT`/`PORT`, `DATABASE_URL` e `REDIS_URL` carregam por settings.
- `Procfile` presente e compatível com Railway.
- `health` responde com degradado quando DB local indisponivel (comportamento esperado).
- `alembic history` e `alembic heads` funcionam; `alembic current` depende de DB ativo.
- DB local (`localhost:5432`) e Redis local (`localhost:6379`) estavam indisponiveis no momento do teste.

## Entregas implementadas nesta rodada

- Dashboard web inicial em `GET /dashboard`:
  - KPIs: leads, conversas abertas, mensagens inbound, posts publicados.
  - Top mensagens textuais (top 10).
  - Leads recentes.
  - Posts recentes.
  - Refresh manual e automatico (30s).
- Inclusao do router de dashboard no `app/main.py`.
- Limpeza de ruido textual no `README.md` e atualizacao dos endpoints documentados.

## Limites e pendencias

- Integracoes reais com APIs externas (Meta/Instagram/TikTok/YouTube) seguem em modo stub seguro.
- Provisionamento Railway (servicos e variaveis) exige acao manual no painel da conta.
- Configuracao oficial de webhook WhatsApp/Instagram exige credenciais reais e validacao no Meta Developer.
- Para migracoes em ambiente remoto, DB precisa estar ativo e com `DATABASE_URL` correta.

## Proximos passos recomendados

1. Provisionar no Railway: API + PostgreSQL + Redis + Worker Celery.
2. Definir variaveis de ambiente da API e do Worker.
3. Executar `alembic upgrade head` no ambiente Railway.
4. Validar URL publica (`/`, `/health`, `/dashboard`, `/docs`).
5. Ligar webhook Meta para endpoint publico.
6. Implementar pipeline de resposta automatica (mensagem e audio) via Celery.

## Registro de task - 2026-04-09

Task executada: auditoria de lacunas do projeto ("o que esta faltando").

Lacunas tecnicas identificadas:
- Integracoes externas ainda em stub (`not_configured`) para WhatsApp, Instagram, TikTok e YouTube.
- Tasks Celery ainda retornam `queued_stub`, sem processamento real.
- Webhook Meta recebe e aceita payload, mas ainda nao persiste nem dispara pipeline.
- API de dados expoe somente listagens; faltam endpoints de escrita/operacao para fluxo completo.
- Testes automatizados do projeto nao estao implementados/configurados (inclusive `pytest` ausente no ambiente local da venv).
- Provisionamento Railway ainda incompleto para producao plena (Postgres, Redis e Worker bloqueados por permissao no historico da sessao).

## Registro de task - 2026-04-09 (plano de execucao)

Task executada: definicao do plano de execucao priorizado e justificativa arquitetural FastAPI vs n8n.

Plano proposto:
1. P0 Infra/Release: concluir provisionamento Railway (Postgres, Redis, Worker), ajustar variaveis, rodar `alembic upgrade head` e validar `/health` sem degradacao.
2. P0 Ingestao: completar webhook Meta com persistencia de evento/mensagem e disparo de task Celery.
3. P1 Orquestracao: implementar pipeline real das tasks (transcricao, roteamento, resposta, publicacao) com estados de job.
4. P1 API operacional: adicionar endpoints de escrita/acao (criar contato/conversa/mensagem/post e atualizar status).
5. P1 Integracoes externas: trocar stubs de WhatsApp/Instagram/TikTok/YouTube por adaptadores reais com tratamento de erro e retry.
6. P2 Qualidade: criar testes automatizados (unitarios + integracao minima), adicionar `pytest` ao ambiente e checks de CI.
7. P2 Observabilidade/Seguranca: metricas, correlation id, politicas de segredo e rotacao de tokens.

Justificativa tecnica:
- FastAPI foi mantido como nucleo por oferecer tipagem forte, controle de dominio, versionamento de API e melhor governanca para fluxos de negocio complexos.
- n8n e util como camada de automacao/orquestracao visual, mas sozinho tende a ser mais fraco para modelagem de dominio, testes de codigo e manutencao de regra de negocio extensa.
- Decisao recomendada: FastAPI como backend principal e n8n opcional para fluxos perifericos (notificacoes, tarefas administrativas e integracoes simples).

## Registro de task - 2026-04-09 (execucao P0)

Task executada: execucao pratica do P0.

P0 concluido no codigo:
- `POST /webhooks/meta` agora persiste evento recebido em `audit_logs`.
- Mensagens WhatsApp do payload sao extraidas e persistidas em `contacts`, `conversations` e `messages`.
- Idempotencia aplicada por `external_message_id` (mensagens duplicadas sao ignoradas).
- Apos commit, mensagens novas sao enfileiradas via `process_incoming_message.delay(...)`.
- Resposta do webhook passou a retornar contadores de detectadas/criadas/duplicadas/enfileiradas.

Problema sem solucao nesta sessao:
- P0 de infraestrutura Railway nao pode ser concluido por bloqueio de autenticacao.
- Evidencias: `railway whoami` retornando `Unauthorized` e falha de refresh OAuth (`invalid_grant`).
- Tentativas com tokens existentes e token salvo em `~/.railway/config.json` tambem retornaram `Unauthorized`.
- `railway login --browserless` nao foi possivel no modo nao interativo do ambiente.

## Registro de task - 2026-04-09 (execucao P0 com tokens)

Task executada: retomada do P0 com tokens fornecidos pelo usuario.

Status de execucao:
- Token de projeto funcionou para operacoes no projeto `d1de1982-b64d-40c2-90ef-7be95b24707e`.
- Confirmado que `Postgres-w1Lp` e `Redis` ja existiam e estavam com deploy `SUCCESS`.
- `DATABASE_URL` e `REDIS_URL` foram configurados no servico da API (`projeto-automacao`), com `DATABASE_URL` ajustada para `postgresql+psycopg://...`.
- Migracao remota executada com sucesso (`alembic upgrade head`) usando URL publica do Postgres.
- Novo deploy da API realizado e finalizado com `SUCCESS`.
- Validacoes de producao:
  - `GET /` -> `200` (running)
  - `GET /health` -> `status=ok`, `database=ok`
  - `GET /dashboard` -> `200`
  - `POST /webhooks/meta` de teste -> `messages_created=1`, `messages_queued=1`
  - `GET /contacts|/conversations|/messages` refletindo dados persistidos.

Problema sem solucao nesta sessao:
- Criacao do servico `worker` via `railway add -s worker -r flaviavs-commits/projeto-automacao --json` retornou `Unauthorized`.
- Com o token atual, foi possivel gerenciar servicos existentes, mas nao criar novo servico.

## Registro de task - 2026-04-09 (permissao Railway)

Task executada: orientacao de como liberar permissao para concluir criacao do servico `worker`.

Orientacao consolidada:
- Garantir role adequada no projeto (Owner ou Editor no projeto; Owner tem administracao total).
- Preferir token de conta/workspace para operacoes administrativas via CLI (`RAILWAY_API_TOKEN`).
- Usar token de projeto (`RAILWAY_TOKEN`) para acoes de ambiente/deploy.
- Validar permissao com `railway status` e tentar `railway add -s worker ...`.
