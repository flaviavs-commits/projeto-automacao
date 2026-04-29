# Mapa de Rotas da API — Backend Real (main)

> Atualizado em 2026-04-28 a partir dos `urls.py` e `views.py` da branch `main`.
> Base URL de produção: `https://vs-production-c4dd.up.railway.app/api`

---

## Accounts (`/api/`)

### POST /api/cadastro/
- **View**: `cadastro_view` (accounts/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny
- **Payload esperado**:
  ```json
  {
    "email": "string",
    "password": "string",
    "password_confirm": "string",
    "first_name": "string",
    "last_name": "string",
    "telefone": "string",
    "cpf": "string",
    "sexo": "string",
    "plano": "string",
    "site_cadastro": "fcvip | descontos_vip",
    "aff_ref": "string"
  }
  ```
- **Resposta de sucesso**:
  ```json
  {
    "success": true,
    "message": "Cadastro realizado com sucesso.",
    "data": {
      "user": {},
      "tokens": {
        "access": "string",
        "refresh": "string"
      },
      "pending_email_verification": false
    }
  }
  ```
- **Observações**:
  - `site_cadastro` é opcional e assume `fcvip` por padrão.
  - No fluxo simples de conta (sem `kit_type`), o backend dispara um email transacional de boas-vindas após o `commit` da transação.
  - O remetente do email de boas-vindas varia conforme `site_cadastro` e depende das variáveis `FCVIP_WELCOME_*` ou `DESCONTOS_VIP_WELCOME_*` no ambiente.
  - Quando o email pertence ao domínio `@vitissouls.com`, o backend também marca `pending_email_verification=true` e envia email de verificação.
  - Se o payload incluir `kit_type`, a rota redireciona para o fluxo unificado de cadastro + checkout.

### GET /api/verificar-email/
- **View**: `verificar_email_view` (accounts/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny
- **Observações**: Consome token UUID enviado por email; marca `email_verificado=True` e retorna JWT com `plano=ADMIN` para emails `@vitissouls.com`

### POST /api/login/
- **View**: `login_view` (accounts/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny
- **Payload esperado**:
  ```json
  { "email": "string", "password": "string" }
  ```
- **Resposta de sucesso**:
  ```json
  { "access": "string", "refresh": "string", "user": {} }
  ```

### POST /api/auth/firebase/google/
- **View**: `firebase_google_login_view` (accounts/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny

### POST /api/logout/
- **View**: `logout_view` (accounts/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### GET /api/perfil/
- **View**: `perfil_view` (accounts/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### DELETE /api/conta/
- **View**: `conta_delete_view` (accounts/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### POST /api/token/refresh/
- **View**: `token_refresh_view` (accounts/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny
- **Payload esperado**:
  ```json
  { "refresh": "string" }
  ```

### POST /api/senha/resetar/
- **View**: `password_reset_request_view` (accounts/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny

### POST /api/senha/confirmar/
- **View**: `password_reset_confirm_view` (accounts/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny

### POST /api/lead/
- **View**: `lead_create_view` (accounts/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny

### POST /api/tracking/visita/
- **View**: `track_site_visit_view` (accounts/views.py)
- **Autenticação**: Opcional
- **Permissões**: AllowAny
- **Throttle**: `SiteVisitThrottle` (`120/min` por IP)
- **Payload esperado**:
  ```json
  {
    "session_id": "string",
    "path": "/agendamentos",
    "referer": "https://origem.example/"
  }
  ```
- **Resposta de sucesso**:
  ```json
  {
    "success": true,
    "message": "Visita registrada.",
    "data": {
      "recorded": true,
      "deduplicated": false
    }
  }
  ```
- **Observações**:
  - Usado pelo frontend FCVIP para registrar pageviews anônimos ou autenticados.
  - O backend captura `ip` por `X-Forwarded-For` ou `REMOTE_ADDR` e `user_agent` do request.
  - Chamadas repetidas para o mesmo `session_id + path` em até 5 minutos são deduplicadas.
  - Se uma visita anônima recente for repetida com usuário autenticado, o registro existente é vinculado ao usuário em vez de criar nova linha.

### POST /api/afiliados/inscricao/
- **View**: `affiliate_application_create_view` (accounts/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny

### GET /api/afiliados/public/checkout-context/
- **View**: `public_affiliate_checkout_context_view` (affiliates/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny
- **Query params**:
  ```json
  { "aff_ref": "codigo-publico:123" }
  ```
- **Observações**: Endpoint público usado pela landing do Descontoss-Vip para transformar `aff_ref` em contexto de checkout do afiliado. Retorna `codigo`, `clique_id` e `betalabs_shareable_key` quando o clique existir e o afiliado estiver ativo com chave BetaLabs configurada. Retorna `404` para referência inválida, expirada ou sem contexto utilizável.

### GET /api/afiliados/me/resumo/
- **View**: `me_affiliate_summary_view` (affiliates/me_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Observações**: Escopado ao `AffiliateProfile` ativo do usuário logado; retorna métricas agregadas de `cliques`, `cadastros`, `assinaturas_ativas`, saldos (`pendente`, `aprovado`, `pago`) e resumo por status das comissões. Retorna `404` se o usuário autenticado não possuir perfil de afiliado ativo.

### GET /api/afiliados/me/comissoes/
- **View**: `me_affiliate_commissions_view` (affiliates/me_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Query params**:
  ```json
  { "status": "pendente|aprovada|paga|cancelada", "tipo": "primeira_venda|renovacao|estorno" }
  ```
- **Observações**: Lista paginada das comissões do afiliado logado. Retorna `404` se o usuário autenticado não possuir perfil de afiliado ativo.

### GET /api/afiliados/me/cliques/
- **View**: `me_affiliate_clicks_view` (affiliates/me_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Observações**: Lista paginada dos cliques do afiliado logado. Retorna `404` se o usuário autenticado não possuir perfil de afiliado ativo.

### GET, POST /api/afiliados/me/links/
- **View**: `me_affiliate_links_view` (affiliates/me_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Payload esperado no POST**:
  ```json
  {
    "slug": "stories-abril",
    "campanha": "Stories Abril",
    "destino": "https://checkout.example.com/stories-abril",
    "ativo": true
  }
  ```
- **Observações**: Lista paginada dos links/campanhas do afiliado logado com `path_publico`, `url_publica`, total de cliques e último clique. No `POST`, o `slug` é normalizado antes da persistência. Retorna `404` se o usuário autenticado não possuir perfil de afiliado ativo.

### PATCH /api/afiliados/me/links/<id>/
- **View**: `me_affiliate_link_detail_view` (affiliates/me_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Payload esperado**:
  ```json
  {
    "campanha": "Instagram Reels",
    "destino": "https://checkout.example.com/reels",
    "ativo": false
  }
  ```
- **Observações**: Atualiza apenas links do `AffiliateProfile` do usuário autenticado. Retorna `404` para link inexistente ou pertencente a outro afiliado.

### GET /api/afiliados/me/relatorio/
- **View**: `me_affiliate_report_view` (affiliates/me_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Query params**:
  ```json
  { "formato": "csv|xlsx|json|pdf", "mes": "YYYY-MM" }
  ```
- **Observações**: Baixa o relatório do afiliado autenticado em múltiplos formatos. Sem `mes`, exporta todo o histórico. A visão é sempre a do próprio afiliado, sem lista detalhada de usuários atribuídos. Retorna `404` se o perfil do afiliado não estiver ativo.

### POST /api/inscricao/
- **View**: `inscricao_create_view` (accounts/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny
- **Observações**: Inscrição FCVIP consolidada em `accounts.Inscricao`. É a fonte principal exibida em `/painel/inscricoes/`.

### POST /api/frontend/errors/
- **View**: `frontend_error_report_view` (accounts/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny
- **Observações**: Recebe erros de JS do frontend para logging

### GET /api/user/profile/
- **View**: `user_profile_view` (accounts/user_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### GET /api/user/tier/
- **View**: `user_tier_view` (accounts/user_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### GET /api/user/membership-status/
- **View**: `membership_status_view` (accounts/user_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### GET /api/user/member-benefits/
- **View**: `member_benefits_view` (accounts/user_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### GET /api/user/checkout-context/
- **View**: `checkout_context_view` (accounts/user_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Observações**: Retorna contexto de checkout pendente do usuário (kit pendente, tipo de checkout)

### POST /api/auth/verify-membership/
- **View**: `auth_verify_membership_view` (accounts/user_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

---

## Admin de Usuários (`/api/admin/`)

> Rotas montadas via `accounts/admin_urls.py` em `path("api/admin/", ...)`.

### GET /api/admin/usuarios/
- **View**: `admin_usuarios_list` (accounts/views.py)
- **Permissões**: IsAdminUser

### GET, PUT /api/admin/usuarios/<id>/
- **View**: `admin_usuario_detail` (accounts/views.py)
- **Permissões**: IsAdminUser

### POST /api/admin/usuarios/<id>/plano/
- **View**: `admin_usuario_plano` (accounts/views.py)
- **Permissões**: IsAdminUser

### POST /api/admin/usuarios/<id>/admin/
- **View**: `admin_usuario_toggle_admin` (accounts/views.py)
- **Permissões**: IsAdminUser

### GET /api/admin/logs/registros/
- **View**: `admin_logs_registros_view` (accounts/views.py)
- **Permissões**: IsAdminUser

### GET /api/admin/monitor/feed/
- **View**: `admin_monitor_feed_view` (accounts/views.py)
- **Permissões**: IsAdminUser

### GET /api/admin/agendamentos/recentes/
- **View**: `admin_recent_bookings_view` (accounts/views.py)
- **Permissões**: IsAdminUser

### GET /api/admin/activity/recent/
- **View**: `admin_activity_recent_view` (accounts/activity_views.py)
- **Permissões**: IsAdminUser

### GET /api/admin/activity/summary/
- **View**: `admin_activity_summary_view` (accounts/activity_views.py)
- **Permissões**: IsAdminUser

### GET /api/admin/activity/user/<id>/
- **View**: `admin_activity_user_view` (accounts/activity_views.py)
- **Permissões**: IsAdminUser

---

## Programa de Afiliados (`/api/admin/afiliados/`)

### GET /api/admin/afiliados/
- **View**: `admin_affiliate_profiles_list_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin
- **Observações**: Lista perfis de afiliado com métricas agregadas (`total_cliques`, `total_atribuicoes`, `total_comissoes`). Aceita `q` e `status`.

### GET /api/admin/afiliados/relatorio/
- **View**: `admin_affiliate_general_report_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin
- **Query params**:
  ```json
  { "formato": "csv|xlsx|json|pdf", "mes": "YYYY-MM", "todos": "0|1" }
  ```
- **Observações**: Exporta o relatório consolidado dos afiliados. Por padrão considera apenas perfis ativos; use `todos=1` para incluir perfis não ativos.

### POST /api/admin/afiliados/relatorios/cron/
- **View**: `admin_affiliate_reports_cron_view` (affiliates/api_views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny
- **Headers esperados**:
  ```json
  { "X-CRON-SECRET": "string" }
  ```
  ou
  ```json
  { "Authorization": "Bearer string" }
  ```
- **Observações**: Endpoint técnico do agendamento mensal. Exige `CRON_SECRET` e executa `run_affiliate_report_automation()` usando a configuração persistida em `AffiliateReportAutomationSettings`.

### GET /api/admin/afiliados/<profile_id>/relatorio/
- **View**: `admin_affiliate_report_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin
- **Query params**:
  ```json
  { "formato": "csv|xlsx|json|pdf", "mes": "YYYY-MM", "visao": "admin|afiliado" }
  ```
- **Observações**: Exporta o relatório detalhado de um afiliado específico. `visao=admin` inclui usuários atribuídos e colunas sensíveis; `visao=afiliado` reduz o payload ao recorte que o próprio afiliado pode consumir.

### GET /api/admin/afiliados/resumo/
- **View**: `admin_affiliate_summary_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin
- **Observações**: Resumo operacional por competência com totais por status e ranking de afiliados. Aceita `competencia` e `top`.

### GET /api/admin/afiliados/atribuicoes/
- **View**: `admin_affiliate_attributions_list_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin
- **Observações**: Lista paginada das atribuições com filtros `q` e `affiliate_code`.

### GET /api/admin/afiliados/auditoria/
- **View**: `admin_affiliate_audit_logs_list_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin
- **Query params**:
  ```json
  {
    "q": "string",
    "affiliate_code": "string",
    "evento": "comissao_aprovada|comissao_cancelada|comissao_estornada|payout_fechado|payout_aprovado|payout_pago",
    "origem": "admin_api|admin_panel"
  }
  ```
- **Observações**: Lista paginada do `AffiliateAuditLog` com afiliado, executor, alvo (`comissao_id` / `payout_id`), `metadata` e timestamp.

### GET /api/admin/afiliados/comissoes/
- **View**: `admin_affiliate_commissions_list_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin
- **Observações**: Lista paginada de comissões com filtros `q`, `affiliate_code`, `status` e `tipo`.

### GET /api/admin/afiliados/comissoes/exportar/
- **View**: `admin_affiliate_commissions_export_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin
- **Observações**: Export CSV usando os mesmos filtros da listagem de comissões.

### PATCH /api/admin/afiliados/comissoes/<id>/aprovar/
- **View**: `admin_affiliate_commission_approve_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin

### PATCH /api/admin/afiliados/comissoes/<id>/cancelar/
- **View**: `admin_affiliate_commission_cancel_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin

### PATCH /api/admin/afiliados/comissoes/<id>/estornar/
- **View**: `admin_affiliate_commission_refund_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin

### GET /api/admin/afiliados/payouts/
- **View**: `admin_affiliate_payouts_list_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin
- **Observações**: Lista paginada de payouts com filtros `q`, `affiliate_code` e `status`.

### GET /api/admin/afiliados/payouts/exportar/
- **View**: `admin_affiliate_payouts_export_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin
- **Observações**: Export CSV usando os mesmos filtros da listagem de payouts.

### POST /api/admin/afiliados/payouts/fechar/
- **View**: `admin_affiliate_payout_close_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin

### PATCH /api/admin/afiliados/payouts/<id>/aprovar/
- **View**: `admin_affiliate_payout_approve_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin

### PATCH /api/admin/afiliados/payouts/<id>/pagar/
- **View**: `admin_affiliate_payout_pay_view` (affiliates/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated + admin

---

## CRM (`/api/admin/crm/`)

### POST /api/admin/crm/cron/
- **View**: `admin_crm_automation_cron_view` (crm/api_views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny
- **Headers esperados**:
  ```json
  { "X-CRON-SECRET": "string" }
  ```
  ou
  ```json
  { "Authorization": "Bearer string" }
  ```
- **Observações**: Endpoint tecnico do agendamento diario do CRM por email. Exige `CRON_SECRET` e executa `run_crm_automation()` usando a configuracao persistida em `CrmAutomationSettings`.

---

## Kits e Checkout (`/api/` e `/api/billing/`)

### GET /api/kits/
- **View**: `kits_list_view` (billing/api_views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny

### GET /api/kits/<id>/
- **View**: `kit_detail_view` (billing/api_views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny

### POST /api/checkout/create-session/
- **View**: `create_checkout_session_view` (billing/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Payload esperado**:
  ```json
  {
    "kit_id": 1,
    "booking": {
      "slot_ids": [123, 124],
      "slot_id": 123,
      "whatsapp": "11999999999",
      "tipo_sessao": "Foto",
      "duracao": "2h",
      "kit_type": "recomendado",
      "metodo_pagamento": "stripe",
      "observacoes": "string"
    }
  }
  ```
- **Observações**: `kit_id` é o ID numérico do banco. `booking` é opcional; quando enviado, cria intenções de checkout por slot para o webhook Stripe converter em reservas após pagamento. Resposta: `{ success, data: { checkout_url, session_id } }`

### POST /api/checkout/webhook/
- **View**: `stripe_webhook_view` (billing/api_views.py)
- **Observações**: Webhook Stripe (rota legada na raiz) — chamado pelo Stripe, não pelo frontend

### GET /api/billing/kits/
- **View**: `kits_list_view` (billing/api_views.py)
- **Permissões**: AllowAny

### GET /api/billing/kits/<id>/
- **View**: `kit_detail_view` (billing/api_views.py)
- **Permissões**: AllowAny

### GET /api/billing/verify-membership/
- **View**: `verify_membership_view` (billing/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### GET /api/billing/checkout/
- **View**: `checkout_criar_view` (billing/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### POST /api/billing/checkout/create-session/
- **View**: `create_checkout_session_view` (billing/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Observações**: Contrato equivalente a `POST /api/checkout/create-session/`, incluindo o payload opcional `booking` com `slot_ids` para checkout de agendamentos.

### GET /api/billing/checkout-status/
- **View**: `checkout_status_view` (billing/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### POST /api/billing/webhooks/stripe/
- **View**: `stripe_webhook_view` (billing/api_views.py)
- **Observações**: Webhook Stripe (rota canônica em `/api/billing/`) — usar este URL no Stripe Dashboard

### POST /api/billing/webhooks/betalabs/
- **View**: `betalabs_webhook_view` (billing/api_views.py)
- **Observações**: Webhook BetaLabs — chamado pelo BetaLabs, não pelo frontend

### POST /api/billing/cron/check-memberships/
- **View**: `check_memberships_cron_view` (billing/api_views.py)
- **Observações**: Cron job para verificação periódica de memberships

### GET /api/billing/admin/betalabs-members/
- **View**: `betalabs_active_members_view` (billing/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAdminUser
- **Observações**: Consulta em tempo real a contagem agregada de assinaturas BetaLabs por status.

### GET /api/billing/admin/betalabs-clients/
- **View**: `betalabs_clients_view` (billing/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAdminUser
- **Query params**:
  ```json
  {
    "q": "string",
    "status": "active|overdue|canceled|none",
    "local_match": "true|false"
  }
  ```
- **Observações**: Lista paginada de clientes BetaLabs com assinaturas aninhadas, resumo por status e cruzamento com usuários locais/BillingCustomer sem criar contas automaticamente.

### GET /api/health/
- **View**: `healthcheck_view` (fcvip_backend/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny

---

## Scheduling (`/api/` e `/api/admin/agenda/`)

### POST /api/admin/agenda/cron/
- **View**: `agenda_cron_view` (scheduling/cron_views.py)
- **Autenticação**: Não (segredo compartilhado)
- **Permissões**: AllowAny
- **Headers esperados**:
  ```json
  { "X-CRON-SECRET": "string" }
  ```
  ou
  ```json
  { "Authorization": "Bearer string" }
  ```
- **Payload opcional**:
  ```json
  {
    "recurso": "estudio-principal",
    "dias": 30
  }
  ```
- **Observações**: Endpoint técnico para geração idempotente de slots da agenda. Exige `CRON_SECRET`, usa o recurso ativo informado ou `estudio-principal` por padrão, atende de segunda a domingo e gera a grade padrão de `08:00` a `20:45` (11 sessões de 60 minutos por dia).

### GET /api/agenda/disponibilidade/
- **View**: `disponibilidade_view` (scheduling/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny

### GET /api/agendamentos/recursos/
- **View**: `recursos_agenda_view` (scheduling/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### GET /api/agendamentos/slots/
- **View**: `slots_agenda_view` (scheduling/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny

### GET /api/agendamentos/slots/disponibilidade/
- **View**: `slots_disponibilidade_dia_view` (scheduling/views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny

### POST /api/agendamentos/slots/gerar/
- **View**: `gerar_slots_agenda_view` (scheduling/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAdminUser

### GET, POST /api/agendamentos/reservas/
- **View**: `reservas_agenda_view` (scheduling/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### POST /api/agendamentos/reservas/<id>/cancelar/
- **View**: `cancelar_reserva_agenda_view` (scheduling/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### POST /api/membro/inscricao/
- **View**: `inscricao_membro_view` (scheduling/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Observações**: Endpoint legado/autenticado. Mantém compatibilidade, mas grava na mesma fonte consolidada de `/api/inscricao/` (`accounts.Inscricao`, `origem=membro_endpoint`).

### GET /api/agendamentos/tickets/
- **View**: `tickets_usuario_view` (scheduling/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### POST /api/agendamentos/tickets/admin/grant/
- **View**: `tickets_admin_grant_view` (scheduling/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated (admin na lógica)

### POST /api/agendamentos/tickets/admin/grant-membership/
- **View**: `tickets_admin_grant_membership_view` (scheduling/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### GET /api/agendamentos/falhas/
- **View**: `tentativas_falha_view` (scheduling/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAdminUser

### GET /api/tickets/
- **View**: `tickets_list_view` (scheduling/ticket_api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

### GET /api/tickets/<uuid>/
- **View**: `ticket_detail_view` (scheduling/ticket_api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated

---

## Dashboard (`/api/dashboard/`)

> Rotas admin requerem `IsAuthenticated + IsAdminUser`. Rotas do cliente requerem apenas `IsAuthenticated`.

### GET /api/dashboard/overview/
- **View**: `dashboard_overview_view` (dashboard/views.py)
- **Permissões**: IsAuthenticated + IsAdminUser

### GET /api/dashboard/usuarios/
- **View**: `dashboard_usuarios_view` (dashboard/views.py)
- **Permissões**: IsAuthenticated + IsAdminUser

### GET /api/dashboard/compras/
- **View**: `dashboard_compras_view` (dashboard/views.py)
- **Permissões**: IsAuthenticated + IsAdminUser

### GET /api/dashboard/tickets/
- **View**: `dashboard_tickets_view` (dashboard/views.py)
- **Permissões**: IsAuthenticated + IsAdminUser

### GET /api/dashboard/memberships/
- **View**: `dashboard_memberships_view` (dashboard/views.py)
- **Permissões**: IsAuthenticated + IsAdminUser

### GET /api/dashboard/health/
- **View**: `dashboard_health_view` (dashboard/views.py)
- **Permissões**: IsAuthenticated + IsAdminUser

### GET /api/dashboard/meu-resumo/
- **View**: `dashboard_meu_resumo_view` (dashboard/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated (qualquer usuário logado)
- **Observações**: Cache por usuário TTL 60s (v2). Inclui `data_assinatura`, `status_assinatura`, `proximo_vencimento`, `gateway_assinatura`, `data_cadastro`, `site_cadastro`, `proximas_reservas`.

### GET /api/dashboard/gamificacao/
- **View**: `dashboard_gamificacao_view` (dashboard/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Observações**: Gamificação por sessões do FCVIP — tier (Iniciante→Elite), progresso, badges. Cache por usuário TTL 60s.

### GET /api/dashboard/descontos-vip/
- **View**: `dashboard_descontos_vip_view` (dashboard/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Observações**: Dados de economia DV — cupons, economia acumulada, tier DV, promoções ativas, link de afiliado. Cache por usuário TTL 60s.

### GET /api/dashboard/ganhos-descontos-vip/
- **View**: `dashboard_ganhos_descontos_vip_view` (dashboard/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Observações**: Contexto de ganhos — perfil afiliado, comissões, CTA para membership DV. Cache por usuário TTL 60s.

### GET /api/dashboard/agenda/
- **View**: `dashboard_agenda_view` (dashboard/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Query params**:
  ```json
  { "page": 1, "per_page": 10 }
  ```
- **Observações**: Agenda completa do cliente — totais agregados, próximas sessões confirmadas e histórico paginado. Cache por usuário TTL 60s.

### GET /api/dashboard/minha-assinatura/
- **View**: `dashboard_minha_assinatura_view` (dashboard/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Observações**: Status da BillingSubscription do usuário logado — `tem_assinatura`, `status`, `gateway`, `proximo_vencimento`, `iniciada_em`, `cancelada_em`, `cancel_at_period_end`. Cache por usuário TTL 60s.

### GET /api/dashboard/afiliado/
- **View**: `dashboard_afiliado_view` (dashboard/views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Observações**: Dashboard unificado do afiliado logado — `tem_perfil`, perfil (codigo/status/percentual/url_publica), saldo (pendente/aprovado/pago), últimas 5 comissões, totais (cliques/atribuicoes). Cache por usuário TTL 60s.

---

## CRM — Descadastro e Tracking (`/api/crm/`)

### GET /api/crm/descadastrar/
- **View**: `optout_view` (crm/api_views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny
- **Query params**: `uid`, `categoria`, `token` (HMAC-SHA256)
- **Observações**: Endpoint de opt-out por link de email. Token gerado por `make_optout_token` em `crm/services.py`.

### GET /api/crm/track/open/
- **View**: `tracking_open_view` (crm/api_views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny
- **Query params**: `lid` (CrmMessageLog.id)
- **Observações**: Retorna pixel GIF 1×1 e registra `aberto_em` na primeira chamada (idempotente).

### GET /api/crm/track/click/
- **View**: `tracking_click_view` (crm/api_views.py)
- **Autenticação**: Não
- **Permissões**: AllowAny
- **Query params**: `lid` (CrmMessageLog.id), `url` (destino), `sig` (assinatura HMAC)
- **Observações**: Incrementa `total_cliques` e redireciona para URL real. Redirect externo sem assinatura HMAC válida cai em `/`.

---

## Portfólio (`/api/portfolio/`)

### GET /api/portfolio/
- **View**: `portfolio_list_view` (portfolio/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Observações**: Lista os itens de portfólio do usuário logado, ordenados por `-criado_em`.

### POST /api/portfolio/add/
- **View**: `portfolio_create_view` (portfolio/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Payload esperado**:
  ```json
  {
    "titulo": "string",
    "url_midia": "string (URL, max 2000)",
    "tipo": "foto|video|link",
    "descricao": "string (opcional)",
    "visibilidade": "privado|publico",
    "reserva_id": "int (opcional)"
  }
  ```

### DELETE /api/portfolio/<id>/
- **View**: `portfolio_delete_view` (portfolio/api_views.py)
- **Autenticação**: JWT
- **Permissões**: IsAuthenticated
- **Observações**: Remove o item de portfólio; retorna 403 se o item não pertencer ao usuário logado.

---

## Control Center (`/api/v1/`)

> Painel interno de operações avançadas. Todas as rotas requerem autenticação de admin.

### GET /api/v1/users/
### GET /api/v1/users/stats/
### GET /api/v1/users/export/notion/
### GET, PUT /api/v1/users/<id>/
### POST /api/v1/users/<id>/plan/
### POST /api/v1/users/<id>/admin/
### DELETE /api/v1/users/<id>/delete/
### GET /api/v1/notion/inspect/
### POST /api/v1/notion/sync/leads/
### POST /api/v1/notion/databases/
### GET /api/v1/monitor/feed/
### GET /api/v1/monitor/logs/
### GET /api/v1/scheduling/failures/
### GET /api/v1/scheduling/bookings/
### GET /api/v1/billing/events/
### GET /api/v1/leads/
### GET /api/v1/security/attempts/
### GET /api/v1/inscricoes/
### PATCH /api/v1/inscricoes/<id>/status/
### GET /api/v1/system/status/
### GET /api/v1/system/health/
### GET /api/v1/schema/
### GET /api/v1/docs/

---

## Assistant (`/api/ai/`)

### GET /api/ai/status/
- **View**: `assistant_status_view` (assistant/views.py)

### POST /api/ai/perguntar/
- **View**: `assistant_ask_view` (assistant/views.py)
- **Observações**: Toda comunicação com o provider de IA passa por aqui — chave nunca vai ao frontend
