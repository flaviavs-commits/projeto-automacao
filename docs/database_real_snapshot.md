# Snapshot Real do Banco (Producao)

Gerado em: `2026-05-01T13:29:22.328219+00:00`

## Resumo de volume

| Tabela | Registros |
|---|---:|
| `contacts` | 6 |
| `contact_identities` | 11 |
| `contact_memories` | 13 |
| `conversations` | 9 |
| `messages` | 49 |
| `appointments` | 0 |
| `platform_accounts` | 2 |
| `posts` | 0 |
| `jobs` | 2289 |
| `audit_logs` | 3901 |

## Estrutura das tabelas

### `contacts`

| Colunas |
|---|
| `name`, `phone`, `instagram_user_id`, `youtube_channel_id`, `tiktok_user_id`, `email`, `created_at`, `updated_at`, `id`, `customer_id`, `is_temporary` |

### `contact_identities`

| Colunas |
|---|
| `contact_id`, `platform`, `platform_user_id`, `normalized_value`, `is_primary`, `metadata_json`, `created_at`, `updated_at`, `id` |

### `contact_memories`

| Colunas |
|---|
| `contact_id`, `source_message_id`, `memory_key`, `memory_value`, `status`, `importance`, `confidence`, `created_at`, `updated_at`, `id` |

### `conversations`

| Colunas |
|---|
| `contact_id`, `platform`, `status`, `summary`, `last_message_at`, `created_at`, `updated_at`, `id`, `last_inbound_message_text`, `last_inbound_message_at`, `menu_state`, `needs_human`, `human_reason`, `human_requested_at`, `human_status`, `human_accepted_at`, `human_accepted_by`, `human_ignored_at`, `human_ignored_by`, `chatbot_enabled`, `customer_collection_data`, `customer_collection_step` |

### `messages`

| Colunas |
|---|
| `conversation_id`, `platform`, `direction`, `message_type`, `external_message_id`, `text_content`, `transcription`, `media_url`, `raw_payload`, `ai_generated`, `created_at`, `id` |

### `appointments`

| Colunas |
|---|
| `id`, `contact_id`, `conversation_id`, `customer_name`, `customer_phone`, `start_time`, `end_time`, `status`, `notes`, `created_at`, `updated_at` |

### `platform_accounts`

| Colunas |
|---|
| `platform`, `external_account_id`, `access_token_encrypted`, `refresh_token_encrypted`, `token_expires_at`, `metadata_json`, `created_at`, `updated_at`, `id` |

### `posts`

| Colunas |
|---|
| `platform`, `status`, `title`, `caption`, `media_url`, `scheduled_at`, `published_at`, `external_post_id`, `platform_payload`, `created_at`, `updated_at`, `id` |

### `jobs`

| Colunas |
|---|
| `job_type`, `status`, `payload`, `error_message`, `attempts`, `created_at`, `updated_at`, `id` |

### `audit_logs`

| Colunas |
|---|
| `entity_type`, `entity_id`, `event_type`, `details`, `created_at`, `id` |

## Amostras reais

### `contacts` (ate 8 linhas)

| id | customer_id | name | phone | email | is_temporary | created_at |
|---|---|---|---|---|---|---|
| 0d751d1a-0c34-4bfc-bcd8-4ddb79bd220c | CUST-B8C3DB681B01 | - | - | - | True | 2026-04-30 01:19:31.062375+00:00 |
| 784b5bcf-eda5-4367-abbf-fe3dd4e5fb5c | CUST-5ED98D52A985 | - | 5524988416883 | - | False | 2026-04-29 19:35:33.331606+00:00 |
| aa6e60ed-f99e-4d42-b6a4-3a248d3af0c4 | CUST-F5D6ECA9B777 | Gabriel Fernandes | 133595024851015 | - | False | 2026-04-29 11:31:07.800822+00:00 |
| 3fcb292f-7442-4540-923a-c0f90790a173 | CUST-F0D6EC390251 | - | 5524999849231 | - | False | 2026-04-29 11:26:16.349213+00:00 |
| 51258d7c-4334-45a4-a329-ddf8cb498b87 | CUST-80A1BFD4098B | - | 5524998545803 | - | False | 2026-04-28 20:12:16.087701+00:00 |
| 0691be8c-7b0a-4013-9c0b-2cd4e5043621 | CUST-498BFC7BD631 | - | - | - | False | 2026-04-24 14:02:58.003147+00:00 |

### `contact_identities` (ate 8 linhas)

| id | contact_id | platform | platform_user_id | is_primary | created_at |
|---|---|---|---|---|---|
| 8261acca-3f5a-4d54-adfb-e1be3c803578 | 0d751d1a-0c34-4bfc-bcd8-4ddb79bd220c | whatsapp | 198474867941546@lid | True | 2026-04-30 01:19:31.078092+00:00 |
| e9b97f1c-3b21-4825-9db0-4b1bb5038ee3 | 0d751d1a-0c34-4bfc-bcd8-4ddb79bd220c | whatsapp | 5524981664835-1576632163@g.us | True | 2026-04-30 01:19:31.078084+00:00 |
| e5dcec01-1102-418c-aa92-b88ceac315da | 784b5bcf-eda5-4367-abbf-fe3dd4e5fb5c | whatsapp | 242549839147214@lid | True | 2026-04-29 19:35:33.345919+00:00 |
| 6f7e4515-769f-4211-a204-09ea29bff785 | 784b5bcf-eda5-4367-abbf-fe3dd4e5fb5c | whatsapp | 5524988416883 | True | 2026-04-29 19:35:33.345912+00:00 |
| 14b84910-88fa-4ddd-afa2-91fbbf9cc384 | 51258d7c-4334-45a4-a329-ddf8cb498b87 | whatsapp | 42546197729283@lid | False | 2026-04-29 19:35:17.093788+00:00 |
| e5386b5e-abd5-492e-b0cd-983d37f85a66 | 51258d7c-4334-45a4-a329-ddf8cb498b87 | whatsapp | 5524998545803 | False | 2026-04-29 19:35:17.093780+00:00 |
| 680c54e7-1121-4b2d-be8e-51e525e000fb | 3fcb292f-7442-4540-923a-c0f90790a173 | whatsapp | 133595024851015@lid | False | 2026-04-29 12:08:30.601393+00:00 |
| 380d95d0-abb5-4ad2-a940-d5ddc0646c90 | aa6e60ed-f99e-4d42-b6a4-3a248d3af0c4 | whatsapp | 133595024851015 | True | 2026-04-29 11:31:07.804760+00:00 |

### `contact_memories` (ate 8 linhas)

| id | contact_id | memory_key | memory_value | status | updated_at |
|---|---|---|---|---|---|
| 1db375b2-52a3-4713-9625-7688caf52642 | 3fcb292f-7442-4540-923a-c0f90790a173 | human_reason | valores | active | 2026-04-30 22:24:09.030414+00:00 |
| 288446ad-b4d8-4418-a5c1-76b3de3d857e | 3fcb292f-7442-4540-923a-c0f90790a173 | pacote_interesse | 1h | active | 2026-05-01 12:57:36.253440+00:00 |
| 293e6828-193b-4bf0-8e4d-9c4b6010c749 | 51258d7c-4334-45a4-a329-ddf8cb498b87 | cliente_status | antigo | active | 2026-04-29 19:35:17.174259+00:00 |
| 44ece4e0-e064-4709-b3ec-411c9880a2a2 | 3fcb292f-7442-4540-923a-c0f90790a173 | cliente_status | antigo | active | 2026-05-01 12:58:48.062768+00:00 |
| 505c8a62-a90f-4f3d-8ae0-0beaba9561dc | 784b5bcf-eda5-4367-abbf-fe3dd4e5fb5c | interesse | preco | active | 2026-04-29 19:35:42.098065+00:00 |
| 568f7d5f-1d64-493d-9844-8d1b533ddddd | 3fcb292f-7442-4540-923a-c0f90790a173 | tipo_agendamento | cliente_antigo | active | 2026-05-01 12:57:23.886468+00:00 |
| 6598635c-5c0c-4f07-930d-a81ba1d0112a | 784b5bcf-eda5-4367-abbf-fe3dd4e5fb5c | pacote_interesse | 2h | active | 2026-04-29 19:35:42.098069+00:00 |
| 6aa3b963-d085-4b5a-b82b-1dbb15529850 | 51258d7c-4334-45a4-a329-ddf8cb498b87 | human_reason | outro | active | 2026-04-29 19:35:56.754294+00:00 |

### `conversations` (ate 8 linhas)

| id | contact_id | platform | status | human_status | menu_state | chatbot_enabled | updated_at |
|---|---|---|---|---|---|---|---|
| 10acb114-b73e-41d1-ac0f-3b8c740fe32b | 3fcb292f-7442-4540-923a-c0f90790a173 | whatsapp | open | closed | structure_menu | True | 2026-05-01 12:58:59.302529+00:00 |
| 1c039e1e-e569-4ffd-ae4e-373ff5c40ec1 | aa6e60ed-f99e-4d42-b6a4-3a248d3af0c4 | whatsapp | closed | closed | - | True | 2026-04-29 19:33:27.788919+00:00 |
| 20c36aac-010b-4901-a7e3-25e3960867b9 | 784b5bcf-eda5-4367-abbf-fe3dd4e5fb5c | whatsapp | closed | closed | pricing_menu | True | 2026-04-30 01:19:31.408390+00:00 |
| 6d9fab7e-32d5-414d-b551-f9915c5d2b71 | 0691be8c-7b0a-4013-9c0b-2cd4e5043621 | whatsapp | open | closed | - | True | 2026-04-30 15:04:20.606024+00:00 |
| 864596b7-9c36-4179-bcff-a7c166a6c19e | 0d751d1a-0c34-4bfc-bcd8-4ddb79bd220c | whatsapp | closed | closed | collect_new_customer_data | False | 2026-05-01 12:52:29.780075+00:00 |
| 8ca1d8ee-e2e2-466f-a6fe-cf4098c26129 | 51258d7c-4334-45a4-a329-ddf8cb498b87 | whatsapp | closed | closed | - | True | 2026-04-29 19:33:27.788922+00:00 |
| 9896df82-4bd8-45b2-93cd-7dd32a904ab9 | 3fcb292f-7442-4540-923a-c0f90790a173 | whatsapp | closed | closed | human_menu | True | 2026-04-30 13:28:39.948407+00:00 |
| af368df2-bb14-465b-ac6c-5e38b47c006b | 51258d7c-4334-45a4-a329-ddf8cb498b87 | whatsapp | closed | closed | human_menu | True | 2026-04-30 01:19:31.408396+00:00 |

### `messages` (ate 8 linhas)

| id | conversation_id | platform | direction | message_type | external_message_id | created_at |
|---|---|---|---|---|---|---|
| e7149b6f-210f-4fae-a938-18ca07195dab | 10acb114-b73e-41d1-ac0f-3b8c740fe32b | whatsapp | outbound | text | - | 2026-05-01 12:58:59.304233+00:00 |
| 8a7d5830-8111-4584-a604-835b413a09b4 | 10acb114-b73e-41d1-ac0f-3b8c740fe32b | whatsapp | inbound | text | 3A52F4B277BD7888A78D | 2026-05-01 12:58:59.204527+00:00 |
| b7339ffa-01c7-438e-97b5-a0b1eca92cef | 10acb114-b73e-41d1-ac0f-3b8c740fe32b | whatsapp | outbound | text | - | 2026-05-01 12:58:53.666257+00:00 |
| a325e3a7-2e51-46cd-a2b2-58c96e16b810 | 10acb114-b73e-41d1-ac0f-3b8c740fe32b | whatsapp | inbound | text | 3A06D207AB1287E51235 | 2026-05-01 12:58:53.571321+00:00 |
| 249e0707-17eb-4404-b3eb-b7c7183e1748 | 10acb114-b73e-41d1-ac0f-3b8c740fe32b | whatsapp | outbound | text | - | 2026-05-01 12:58:48.065662+00:00 |
| b0344c9e-b890-4665-99a1-0a4d04f779be | 864596b7-9c36-4179-bcff-a7c166a6c19e | whatsapp | outbound | text | - | 2026-04-30 01:19:31.385126+00:00 |
| d8665e8f-ee3d-4a7e-8f09-b66891fabe95 | 864596b7-9c36-4179-bcff-a7c166a6c19e | whatsapp | inbound | text | 3A70F6E2D7D75812860B | 2026-04-30 01:19:31.083791+00:00 |
| da328de7-8370-46e2-8787-17b9978bd980 | 9896df82-4bd8-45b2-93cd-7dd32a904ab9 | whatsapp | outbound | text | - | 2026-04-29 20:16:06.107326+00:00 |

### `appointments` (ate 8 linhas)

| id | contact_id | customer_name | customer_phone | start_time | end_time | status |
|---|---|---|---|---|---|---|
| - | - | - | - | - | - | - |

### `platform_accounts` (ate 8 linhas)

| id | platform | external_account_id | token_expires_at | updated_at |
|---|---|---|---|---|
| 36c3bbdd-bf54-4d4e-aea4-3b79ed78ada5 | meta | 122174952416895412 | 2026-06-20 18:02:13.577074+00:00 | 2026-04-22 12:05:49.597989+00:00 |
| 70b4b580-1d4c-4281-94bd-2ccc0e5b8078 | meta | 122174948474895412 | 2026-06-12 13:41:43.670277+00:00 | 2026-04-13 13:41:44.792158+00:00 |

### `posts` (ate 8 linhas)

| id | platform | status | title | scheduled_at | published_at | created_at |
|---|---|---|---|---|---|---|
| - | - | - | - | - | - | - |

### `jobs` (ate 8 linhas)

| id | job_type | status | attempts | updated_at |
|---|---|---|---|---|
| 0012dc85-4d97-4c43-95e0-5b50f11e7402 | process_incoming_message | completed | 1 | 2026-04-20 12:04:09.608433+00:00 |
| 0031709f-3b7f-4ec5-9666-536d2f0089d9 | send_follow_up | completed | 1 | 2026-04-30 14:00:49.112048+00:00 |
| 00658da7-d5cb-4534-b7d8-e9ff23db39f0 | generate_reply | completed | 1 | 2026-04-20 12:14:06.033918+00:00 |
| 0068d3b6-1e61-44e9-a094-4d4e85c5f729 | generate_reply | completed | 1 | 2026-04-20 11:48:02.236477+00:00 |
| 009ce7be-1ed0-4162-af62-40c0c6c01f56 | generate_reply | completed | 1 | 2026-04-14 19:59:01.675687+00:00 |
| 00abcbbe-b55d-4998-af7e-8cb4ef445785 | generate_reply | completed | 1 | 2026-04-20 11:45:22.930008+00:00 |
| 00aeb9c3-782a-4f6a-8c7a-fd492fa9066d | process_incoming_message | completed | 1 | 2026-04-20 13:36:13.241774+00:00 |
| 00c1f693-83ca-41ad-9603-7edde7c7f96b | generate_reply | completed | 1 | 2026-04-20 20:37:14.502377+00:00 |

### `audit_logs` (ate 8 linhas)

| id | entity_type | event_type | created_at |
|---|---|---|---|
| a4d96d85-7e24-4236-bd27-648afe762329 | message | incoming_message_processed | 2026-05-01 12:58:59.394369+00:00 |
| 7ee4a3fa-55c7-4f26-9ef3-3bad9d2c4d2c | conversation | message_retention_pruned | 2026-05-01 12:58:59.355792+00:00 |
| b0d610e3-ef28-4116-b4b8-fb184ca8887f | conversation | auto_reply_generated | 2026-05-01 12:58:59.355772+00:00 |
| 4383ea72-429a-482b-a499-75c461f67fa9 | contact_identity | identity_conflict | 2026-05-01 12:58:59.199313+00:00 |
| f1fca8f0-6ecf-493f-afcb-0c7915799bcf | contact_identity | identity_conflict | 2026-05-01 12:58:59.199308+00:00 |
| 437a2b43-6cee-4a3b-b55f-a748083b4df4 | webhook | evolution_webhook_received | 2026-05-01 12:58:59.199277+00:00 |
| c6185370-2f93-47ec-86b2-a4b4d4d4ddf8 | message | incoming_message_processed | 2026-05-01 12:58:53.739499+00:00 |
| 537c3d76-a85f-431c-a376-2854b67acef2 | conversation | message_retention_pruned | 2026-05-01 12:58:53.713198+00:00 |
