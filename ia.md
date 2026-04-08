# Contexto IA - bot-multiredes

## Regra operacional permanente

- Sempre que o usuario solicitar o relatorio pessoal no padrao `relatorio_gabrielf_dd_mm.md`, atualizar tambem este arquivo `ia.md` na mesma sessao.
- O `ia.md` deve refletir o estado tecnico mais recente (infra, deploy, bloqueios, status de endpoints e proximos passos).

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
