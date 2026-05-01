# Relatório de Melhoria Contínua e Arquitetura

---

## 1. Visão Geral do Estado Atual

O projeto adota uma arquitetura em camadas composta por **routes** (FastAPI), **services** (lógica de negócio) e **models** (SQLAlchemy). A separação de responsabilidades existe, mas apresenta problemas de coesão e acoplamento identificáveis no código lido:

- **`LLMReplyService`** (≈ 1 596 linhas) concentra responsabilidades múltiplas e heterogêneas: geração de resposta via LLM, todas as regras de decisão por palavras-chave (saudação, escalada, fechamento, localização, áudio, agendamento, profanidade, perguntas pessoais etc.), construção do prompt do sistema, seleção de CTA link e controle de qualidade de resposta. O resultado é uma classe **God Object** com altíssimo acoplamento interno.

- **`DashboardOpService`** e **`HumanQueueService`** duplicam o dicionário `_HUMAN_REASON_LABELS`. Ambas as classes definem o mesmo mapeamento de chave → label (ex.: `"pedido_humano": "Cliente pediu atendimento humano"`). Qualquer nova razão exige modificação em dois lugares distintos.

- **`dashboard.py` (rota `/dashboard/op/state`)** executa consultas SQL diretamente na camada de rota (`db.query(Conversation.id).count()`, `db.query(Conversation.id).filter(...).count()`, `db.query(Conversation.contact_id).distinct().count()`), violando a separação de camadas.

- **`ScheduleService._build_slots`** encoda regras de negócio de horário de funcionamento com valores literais (`range(8, 21)`) que não são configuráveis, e o máximo de dias (`93`) também é hardcoded.

- **`RoutingService.route_intent`** é um conjunto de `if/elif` lineares. Cada novo tipo de rota ou plataforma requer modificação direta desta função.

- Os serviços são todos instanciados diretamente com `DashboardOpService()`, `HumanQueueService()`, `ManualMessageService()` etc. nas rotas — sem injeção de dependência, impossibilitando substituição por mocks em testes.

- **Limitação de escopo**: os arquivos `base.py` (classe `BaseExternalService`), `memory_service.py`, `contact_memory_service.py` e os modelos SQLAlchemy não foram integralmente lidos. Observações sobre contratos de interface partem do código efetivamente analisado.

---

## 2. Bugs Críticos Identificados

### Bug 1 — KPI `inbound_total` e `outbound_total` retornam o mesmo valor

**Arquivo:** `app/api/routes/dashboard.py`, função `dashboard_op_state_compat`, linhas 374–375.

```python
inbound_total = db.query(Conversation.id).count()
outbound_total = db.query(Conversation.id).count()
```

Ambas as queries são idênticas: contam **todas** as conversas sem qualquer filtro de direção. O campo `outbound_total` deveria medir algo diferente de `inbound_total`, mas a lógica atual torna os dois valores sempre iguais. Isso é uma quebra funcional: o dashboard exibe uma métrica incorreta para o operador.

---

### Bug 2 — `_build_slots` pode gerar slot com `start_time` no passado sem marcação

**Arquivo:** `app/services/schedule_service.py`, função `_build_slots`, linhas 169–185.

```python
for day in range(days):
    for hour in range(8, 21):
        slot_time = start_day_local + timedelta(days=day, hours=hour)
        key = slot_time.strftime("%Y-%m-%dT%H:00")
        slots.append({"start_time": slot_time.isoformat(), "status": slot_map.get(key, "free")})
```

Slots no passado (antes de `now_local`) são retornados com status `"free"` sem qualquer distinção. O cliente do dashboard pode tentar reservar um horário já expirado sem receber indicação de que aquele slot é inválido. Não há filtragem ou campo `"past": true` para horários anteriores ao momento presente.

---

## 3. Gargalos de OCP (Open/Closed Principle)

### OCP-1 — `LLMReplyService.generate_reply`: cadeia de `if` para regras de decisão

A função `generate_reply` (linhas 384–699) é uma sequência linear de verificações (`_is_greeting`, `_should_close_conversation`, `_is_personal_question`, `_contains_profanity`, `_is_visit_experience_comment`, `_detect_escalation_reason`, `_is_value_request`, `_is_explicit_schedule_request`, `_build_identity_reply`). Adicionar uma nova regra de negócio (ex.: detectar cliente VIP, novo idioma, novo fluxo promocional) exige **modificar diretamente** `generate_reply`, violando o OCP.

### OCP-2 — `LLMReplyService._HUMAN_REASON_LABELS` / `DashboardOpService._HUMAN_REASON_LABELS` / `HumanQueueService._HUMAN_REASON_LABELS`: triplicação de dicionário de domínio

O mesmo mapeamento de razões humanas está copiado em três classes. Adicionar uma nova razão exige alterar três arquivos distintos.

### OCP-3 — `RoutingService.route_intent`: `if/elif` por tipo de mensagem

A função `route_intent` (linhas 7–54) usa uma série de condicionais para decidir qual rota retornar (`transcribe_then_reply`, `generate_reply`, `request_text_clarification`, `noop`). Suportar uma nova rota ou uma nova plataforma com comportamento distinto exige modificar diretamente esta função.

### OCP-4 — `ScheduleService._build_slots`: horário de funcionamento hardcoded

O intervalo `range(8, 21)` e o limite de 93 dias (linha 61) estão literais no código. Mudar o horário de abertura/fechamento do estúdio exige modificar o código-fonte.

### OCP-5 — `dashboard.py / dashboard_op_state_compat`: lógica de agregação de KPIs na camada de rota

As queries de `leads_total`, `open_conversations_total`, `inbound_total`, `outbound_total` (linhas 374–383) residem diretamente na função de rota. Adicionar ou alterar um KPI requer modificar o handler HTTP.

---

## 4. Plano de Ação e Refatoração (Via TDD)

### 4.1 — Refatoração de `generate_reply` para padrão Chain of Responsibility (OCP-1)

#### [RED]

Escrever testes unitários que verificam que cada regra é aplicada isoladamente, **sem dependência da função `generate_reply`** em si:

```python
# test_reply_rules.py

def test_greeting_rule_matches_oi():
    rule = GreetingRule()
    result = rule.evaluate(user_text="oi", context_messages=[], key_memories=[])
    assert result is not None
    assert "Agente FC VIP" in result.reply_text

def test_greeting_rule_does_not_match_scheduling():
    rule = GreetingRule()
    result = rule.evaluate(user_text="quero agendar", context_messages=[], key_memories=[])
    assert result is None

def test_profanity_rule_matches_caralho():
    rule = ProfanityRule()
    result = rule.evaluate(user_text="caralho", context_messages=[], key_memories=[])
    assert result is not None

def test_chain_stops_at_first_match():
    chain = ReplyRuleChain([GreetingRule(), ProfanityRule()])
    result = chain.evaluate(user_text="oi", context_messages=[], key_memories=[])
    assert result is not None
    assert "Agente FC VIP" in result.reply_text
```

Esses testes falharão porque `GreetingRule`, `ProfanityRule` e `ReplyRuleChain` ainda não existem.

#### [GREEN]

Criar a interface mínima:

```python
# app/services/reply_rules/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from app.services.base import ExternalServiceResult

class ReplyRule(ABC):
    @abstractmethod
    def evaluate(
        self,
        *,
        user_text: str,
        context_messages: list[dict[str, Any]],
        key_memories: list[dict[str, Any]],
    ) -> ExternalServiceResult | None:
        ...
```

Extrair `GreetingRule` como primeiro exemplo concreto, movendo a lógica de `_is_greeting` e `_build_greeting_reply` para dentro dela. `generate_reply` delega para `ReplyRuleChain.evaluate(...)` e só prossegue para o LLM se `None` for retornado.

#### [REFACTOR]

Cada comportamento atualmente em `generate_reply` torna-se uma classe `ReplyRule` independente: `GreetingRule`, `ClosingRule`, `PersonalQuestionRule`, `ProfanityRule`, `VisitExperienceRule`, `EscalationRule`, `ValueRequestRule`, `ScheduleRequestRule`, `IdentityRule`. A cadeia é montada por injeção de dependência (lista configurável), e `generate_reply` torna-se:

```python
def generate_reply(self, *, user_text, context_messages, key_memories, model_override=None):
    result = self._rule_chain.evaluate(user_text=user_text, ...)
    if result is not None:
        return result
    return self._call_llm(user_text=user_text, ...)
```

Novas regras são adicionadas sem modificar `generate_reply`.

---

### 4.2 — Centralizar `HUMAN_REASON_LABELS` em módulo de domínio (OCP-2)

#### [RED]

```python
# test_human_reason_labels.py
from app.domain.human_queue import HUMAN_REASON_LABELS

def test_all_known_reasons_are_present():
    assert "pedido_humano" in HUMAN_REASON_LABELS
    assert "problema_agendamento" in HUMAN_REASON_LABELS

def test_label_for_unknown_reason_is_not_present():
    assert "razao_inexistente" not in HUMAN_REASON_LABELS
```

Falharão porque `app.domain.human_queue` não existe.

#### [GREEN]

Criar `app/domain/human_queue.py` com:

```python
HUMAN_REASON_LABELS: dict[str, str] = {
    "problema_agendamento": "Duvida para concluir agendamento",
    "duvida_pagamento": "Duvida sobre pagamento",
    "duvida_valor": "Duvida sobre valores",
    "nao_entendeu_menu": "Cliente nao conseguiu continuar no menu",
    "pedido_humano": "Cliente pediu atendimento humano",
}
```

#### [REFACTOR]

`HumanQueueService._HUMAN_REASON_LABELS` e `DashboardOpService._HUMAN_REASON_LABELS` são removidos. Ambas as classes importam `HUMAN_REASON_LABELS` de `app.domain.human_queue`. Novas razões são adicionadas apenas neste arquivo.

---

### 4.3 — `RoutingService`: padrão Strategy por tipo de mensagem (OCP-3)

#### [RED]

```python
# test_routing.py

def test_audio_router_matches_ptt_with_media():
    router = AudioMessageRouter()
    result = router.can_handle({"message_type": "ptt", "has_media": True})
    assert result is True
    outcome = router.route({"message_type": "ptt", "has_media": True, "platform": "whatsapp"})
    assert outcome["route"] == "transcribe_then_reply"

def test_text_router_does_not_match_audio():
    router = TextMessageRouter()
    assert router.can_handle({"message_type": "ptt", "has_media": True}) is False
```

Falharão porque `AudioMessageRouter` e `TextMessageRouter` não existem.

#### [GREEN]

```python
# app/services/routing/base.py
from abc import ABC, abstractmethod

class MessageRouter(ABC):
    @abstractmethod
    def can_handle(self, payload: dict) -> bool: ...
    @abstractmethod
    def route(self, payload: dict) -> dict: ...
```

Implementar `AudioMessageRouter`, `TextMessageRouter`, `MediaClarificationRouter`, `NoopRouter`.

#### [REFACTOR]

`RoutingService.route_intent` itera sobre uma lista injetada de `MessageRouter`. Cada novo tipo de rota ou plataforma é adicionado como nova implementação de `MessageRouter`, sem alterar `route_intent`.

---

### 4.4 — `ScheduleService._build_slots`: tornar horário de funcionamento configurável (OCP-4)

#### [RED]

```python
# test_schedule_service.py

def test_slots_respect_custom_open_hour():
    service = ScheduleService(open_hour=9, close_hour=18)
    slots = service._build_slots(start_day_local=..., days=1, reserved=[])
    hours = [datetime.fromisoformat(s["start_time"]).hour for s in slots]
    assert 8 not in hours
    assert 9 in hours
    assert 18 not in hours

def test_slots_default_to_8_to_20_when_not_configured():
    service = ScheduleService()
    slots = service._build_slots(start_day_local=..., days=1, reserved=[])
    hours = [datetime.fromisoformat(s["start_time"]).hour for s in slots]
    assert 8 in hours
    assert 20 in hours
    assert 21 not in hours
```

Falharão porque `ScheduleService.__init__` não aceita `open_hour` / `close_hour`.

#### [GREEN]

```python
class ScheduleService:
    def __init__(self, open_hour: int = 8, close_hour: int = 21, max_days: int = 93):
        self._open_hour = open_hour
        self._close_hour = close_hour
        self._max_days = max_days
```

Substituir `range(8, 21)` por `range(self._open_hour, self._close_hour)` e `min(range_days, 93)` por `min(range_days, self._max_days)`.

#### [REFACTOR]

Os valores default passam a vir de `settings` (ex.: `settings.schedule_open_hour`, `settings.schedule_close_hour`), mantendo retrocompatibilidade. Alterar horário de funcionamento não requer mais modificação de código.

---

### 4.5 — Mover KPIs de `dashboard_op_state_compat` para `DashboardOpService` (OCP-5 + Bug 1)

#### [RED]

```python
# test_dashboard_op_service.py

def test_get_kpis_returns_distinct_lead_count(db_session):
    # cria 2 conversas com o mesmo contact_id
    service = DashboardOpService()
    result = service.get_kpis(db=db_session)
    assert result["leads_total"] == 1  # distinct

def test_get_kpis_inbound_and_outbound_differ(db_session):
    # cria 1 conversa inbound e 1 outbound
    service = DashboardOpService()
    result = service.get_kpis(db=db_session)
    assert result["inbound_total"] != result["outbound_total"]
```

O segundo teste falhará porque `inbound_total` e `outbound_total` são atualmente a mesma query (Bug 1).

#### [GREEN]

Criar `DashboardOpService.get_kpis(db)` com a lógica de contagem, e **corrigir o Bug 1** definindo o critério real de diferenciação entre inbound e outbound (ex.: campo `direction` ou `origin` no modelo `Conversation` — **Limitação:** o modelo `Conversation` não foi totalmente lido; se o campo não existir, a correção requer adicionar o campo ao modelo primeiro).

#### [REFACTOR]

`dashboard_op_state_compat` passa a chamar `DashboardOpService().get_kpis(db=db)`. Nenhuma query SQL permanece na camada de rota.

---

## 5. Considerações Finais

As mudanças propostas não alteram o comportamento externo do sistema; elas reorganizam a estrutura interna para torná-la extensível sem modificação. O impacto técnico imediato mais relevante é a eliminação da classe **God Object** `LLMReplyService` via Chain of Responsibility: cada regra de negócio passa a ser testável de forma unitária e isolada, o que reduz drasticamente o risco de regressões ao adicionar novos fluxos de conversa. A centralização de `HUMAN_REASON_LABELS` elimina uma fonte recorrente de inconsistência silenciosa. A correção do Bug 1 (`inbound_total = outbound_total`) é a mudança de maior impacto operacional imediato, pois afeta a confiabilidade das métricas exibidas ao operador no dashboard. Todas as refatorações seguem o ciclo TDD descrito, garantindo que cada passo seja verificável antes de avançar.
