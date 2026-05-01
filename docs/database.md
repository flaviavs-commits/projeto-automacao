# Banco de Dados do Projeto

## Visao geral

- Banco principal: PostgreSQL.
- ORM: SQLAlchemy (`app/core/database.py`).
- Migracoes: Alembic (`alembic/`).
- Ambiente local em `development`: se Postgres local estiver indisponivel, o runtime pode cair para SQLite automaticamente (fallback controlado em `app/core/database.py`).

## Tabela-resumo do banco

| Item | Valor |
|---|---|
| Banco principal | PostgreSQL |
| ORM | SQLAlchemy |
| Migracoes | Alembic |
| Arquivo de conexao | `app/core/database.py` |
| Config principal | `app/core/config.py` |
| Fallback local | SQLite em `development` (quando Postgres local falha) |

## Conexao e sessao

- URL principal: `DATABASE_URL` (config em `app/core/config.py`).
- Engine e `SessionLocal`: `app/core/database.py`.
- Dependency de rotas: `get_db()` em `app/core/database.py`.

## Tabelas principais

| Tabela | Finalidade | Chave/relacao principal |
|---|---|---|
| `contacts` | Cadastro base de cliente | `customer_id` unico |
| `conversations` | Conversas por canal | `contact_id -> contacts.id` |
| `messages` | Historico de mensagens | `conversation_id -> conversations.id` |
| `appointments` | Agenda operacional | `contact_id` e `conversation_id` opcionais |
| `contact_identities` | Unificacao multicanal | `UNIQUE(platform, platform_user_id)` |
| `contact_memories` | Memorias de cliente | `UNIQUE(contact_id, memory_key)` |
| `platform_accounts` | Tokens de plataformas | `platform + external_account_id` |
| `audit_logs` | Auditoria de eventos | `entity_type + event_type` |
| `jobs` | Controle de jobs async | `job_type + status` |
| `posts` | Publicacoes multi-canal | `platform + status` |

### `contacts`

- Identidade global do cliente (`customer_id`).
- Campos principais: `name`, `phone`, `email`, `instagram_user_id`, `youtube_channel_id`, `tiktok_user_id`, `is_temporary`.

### `conversations`

- Conversas por cliente/canal.
- Campos principais: `contact_id`, `platform`, `status`, `summary`, `last_message_at`.
- Campos operacionais OP/menu: `menu_state`, `needs_human`, `human_status`, `human_reason`, `human_requested_at`, `chatbot_enabled`.
- Campos de coleta no menu: `customer_collection_data`, `customer_collection_step`.

### `messages`

- Historico de mensagens por conversa.
- Campos principais: `conversation_id`, `platform`, `direction`, `message_type`, `external_message_id`, `text_content`, `raw_payload`, `ai_generated`, `created_at`.

### `appointments`

- Agenda operacional.
- Campos principais: `contact_id`, `conversation_id`, `customer_name`, `customer_phone`, `start_time`, `end_time`, `status`, `notes`.

### `contact_identities`

- Mapeia multiplas identidades de canal para um mesmo `contact`.
- Unicidade: `(platform, platform_user_id)`.

### `contact_memories`

- Memorias-chave por cliente.
- Unicidade: `(contact_id, memory_key)`.

### `platform_accounts`

- Tokens/credenciais de plataformas externas (criptografados pela camada de aplicacao).

### `audit_logs`

- Trilhas de auditoria de eventos operacionais.

### `jobs`

- Persistencia de estado/tentativas de jobs assicronos.

### `posts`

- Conteudo/publicacoes multi-canal e metadados de agendamento/publicacao.

## Relacionamentos (alto nivel)

- `contacts (1) -> (N) conversations`
- `contacts (1) -> (N) contact_identities`
- `contacts (1) -> (N) contact_memories`
- `conversations (1) -> (N) messages`
- `appointments (N) -> (1) contacts` (opcional)
- `appointments (N) -> (1) conversations` (opcional)
- `contact_memories (N) -> (1) messages` via `source_message_id` (opcional)

## Linha do tempo de migracoes

- `20260403_0001_initial_schema`
  - cria base inicial: `audit_logs`, `contacts`, `jobs`, `platform_accounts`, `posts`, `conversations`, `messages`.
- `20260413_0002_customer_identity_memory`
  - adiciona `contacts.customer_id`.
  - cria `contact_identities` e `contact_memories`.
- `20260429_0003_message_retention_identity_flags`
  - adiciona `contacts.is_temporary`.
  - adiciona `conversations.last_inbound_message_text` e `last_inbound_message_at`.
- `20260429_0004_menu_bot_state`
  - adiciona estado do menu e solicitacao humana em `conversations`.
- `20260430_0005_op_dashboard_human_queue_and_appointments`
  - adiciona controle humano/chatbot em `conversations`.
  - cria tabela `appointments`.
- `20260430_0006_menu_bot_collection_state`
  - adiciona `conversations.customer_collection_data` e `customer_collection_step`.

## Comandos uteis

- Aplicar migracoes:
  - `python -m alembic upgrade head`
- Ver historico:
  - `python -m alembic history`
- Ver cabeca atual:
  - `python -m alembic heads`

## Observacoes operacionais

- Se o codigo usa colunas novas e o banco de producao nao foi migrado, surgem erros de `UndefinedColumn`.
- Sempre alinhar deploy de codigo com `alembic upgrade head` no ambiente alvo.
