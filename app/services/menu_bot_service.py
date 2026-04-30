from __future__ import annotations

import re
import unicodedata
from typing import Any


class MenuBotService:
    MAIN_MENU_OPTIONS = (
        "1 - Agendamento\n"
        "2 - Valores\n"
        "3 - Conhecer a FC VIP\n"
        "4 - Localizacao\n"
        "5 - Estrutura do estudio\n"
        "6 - Falar com atendente\n"
        "0 - Encerrar atendimento"
    )
    _SKIP_OPTIONAL_VALUES = {"0", "pular", "nao tenho", "nao", ""}
    _EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    _INSTAGRAM_USER_RE = re.compile(r"^[a-zA-Z0-9._]{2,30}$")
    _REPEATED_DIGITS_RE = re.compile(r"^(\d)\1+$")

    def handle_message(
        self,
        *,
        message_text: str,
        conversation: Any,
        contact: Any,
        customer_exists: bool,
        identities: list[dict[str, Any]] | None = None,
        memories: list[dict[str, Any]] | None = None,
        collection_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del identities  # kept to preserve explicit service contract
        text = " ".join(str(message_text or "").split()).strip()
        normalized = self._normalize(text)
        state = str(getattr(conversation, "menu_state", "") or "").strip() or ""
        payload_data = self._initial_collection_data(
            explicit_data=collection_data,
            conversation=conversation,
        )

        if not state:
            return self._start_new_chat(contact=contact, customer_exists=customer_exists, memories=memories)

        if state in {
            "collect_name",
            "collect_phone",
            "collect_email",
            "collect_instagram",
            "collect_facebook",
        }:
            return self._handle_collection_state(
                state=state,
                text=text,
                normalized=normalized,
                payload_data=payload_data,
            )

        if normalized == "0":
            return self._end_response()
        if normalized in {"9", "menu"}:
            return self._main_menu_response(contact=contact, customer_exists=customer_exists, from_return=True, memories=memories)
        if not normalized.isdigit():
            return self._invalid_non_numeric(state=state, contact=contact, customer_exists=customer_exists, memories=memories)

        return self._handle_menu_numeric(
            state=state,
            option=normalized,
            contact=contact,
            customer_exists=customer_exists,
            memories=memories,
        )

    def _initial_collection_data(self, *, explicit_data: dict[str, Any] | None, conversation: Any) -> dict[str, Any]:
        if explicit_data:
            return dict(explicit_data)
        conversation_data = getattr(conversation, "customer_collection_data", None)
        if isinstance(conversation_data, dict):
            return dict(conversation_data)
        return {}

    def _start_new_chat(self, *, contact: Any, customer_exists: bool, memories: list[dict[str, Any]] | None) -> dict[str, Any]:
        if customer_exists:
            return self._main_menu_response(contact=contact, customer_exists=True, from_return=False, memories=memories)
        return self._response(
            text=(
                "Ola! Seja bem-vindo(a) a FC VIP.\n\n"
                "Antes de continuar, preciso fazer seu cadastro rapido.\n\n"
                "Vou pedir uma informacao por vez.\n\n"
                "Etapa 1 de 5:\n"
                "Por favor, envie seu nome completo."
            ),
            state="collect_name",
            memory_updates=[{"memory_key": "cliente_status", "memory_value": "novo"}],
            collected_customer_data={},
            customer_collection_step="collect_name",
        )

    def _handle_collection_state(
        self,
        *,
        state: str,
        text: str,
        normalized: str,
        payload_data: dict[str, Any],
    ) -> dict[str, Any]:
        if state == "collect_name":
            valid_name = self._validate_name(text)
            if not valid_name:
                return self._collect_retry_name(payload_data=payload_data)
            updated = dict(payload_data)
            updated["name"] = valid_name
            return self._response(
                text=(
                    "Etapa 2 de 5:\n"
                    "Agora envie seu telefone com DDD.\n\n"
                    "Digite apenas numeros.\n\n"
                    "Exemplo:\n"
                    "24999999999"
                ),
                state="collect_phone",
                collected_customer_data=updated,
                customer_collection_step="collect_phone",
            )

        if state == "collect_phone":
            valid_phone = self._validate_phone(text)
            if valid_phone is None:
                return self._collect_retry_phone(payload_data=payload_data)
            updated = dict(payload_data)
            updated["phone_original"] = text
            updated["phone_normalized"] = valid_phone
            return self._response(
                text=(
                    "Etapa 3 de 5:\n"
                    "Agora envie seu email.\n\n"
                    "Exemplo:\n"
                    "cliente@email.com"
                ),
                state="collect_email",
                collected_customer_data=updated,
                customer_collection_step="collect_email",
            )

        if state == "collect_email":
            valid_email = self._validate_email(text)
            if not valid_email:
                return self._collect_retry_email(payload_data=payload_data)
            updated = dict(payload_data)
            updated["email"] = valid_email
            return self._response(
                text="Etapa 4 de 5:\nAgora envie seu Instagram.",
                state="collect_instagram",
                collected_customer_data=updated,
                customer_collection_step="collect_instagram",
            )

        if state == "collect_instagram":
            normalized_instagram = self._normalize_instagram(text=text, normalized=normalized)
            if normalized_instagram == "__invalid__":
                return self._collect_retry_instagram(payload_data=payload_data)
            updated = dict(payload_data)
            updated["instagram"] = None if normalized_instagram == "" else normalized_instagram
            return self._response(
                text="Etapa 5 de 5:\nAgora envie seu Facebook.",
                state="collect_facebook",
                collected_customer_data=updated,
                customer_collection_step="collect_facebook",
            )

        normalized_facebook = self._normalize_facebook(text=text, normalized=normalized)
        if normalized_facebook == "__invalid__":
            return self._collect_retry_facebook(payload_data=payload_data)
        updated = dict(payload_data)
        updated["facebook"] = None if normalized_facebook == "" else normalized_facebook
        if not self._required_collection_done(updated):
            return self._collect_retry_name(payload_data=updated)
        return self._response(
            text=(
                "Cadastro concluido com sucesso.\n\n"
                "Agora escolha uma opcao:\n\n"
                f"{self.MAIN_MENU_OPTIONS}\n\n"
                "Digite apenas o numero da opcao desejada."
            ),
            state="main_menu",
            memory_updates=self._build_collection_memory_updates(updated),
            collected_customer_data=updated,
            customer_collection_step=None,
        )

    def _required_collection_done(self, data: dict[str, Any]) -> bool:
        return bool(data.get("name") and data.get("phone_normalized") and data.get("email"))

    def _build_collection_memory_updates(self, data: dict[str, Any]) -> list[dict[str, str]]:
        updates = [
            {"memory_key": "cliente_status", "memory_value": "novo"},
            {"memory_key": "nome_cliente", "memory_value": str(data.get("name") or "").strip()},
            {"memory_key": "telefone", "memory_value": str(data.get("phone_normalized") or "").strip()},
            {"memory_key": "email", "memory_value": str(data.get("email") or "").strip()},
        ]
        instagram = str(data.get("instagram") or "").strip()
        facebook = str(data.get("facebook") or "").strip()
        if instagram:
            updates.append({"memory_key": "instagram_cliente", "memory_value": instagram})
        if facebook:
            updates.append({"memory_key": "facebook_cliente", "memory_value": facebook})
        return [item for item in updates if str(item.get("memory_value") or "").strip()]

    def _handle_menu_numeric(
        self,
        *,
        state: str,
        option: str,
        contact: Any,
        customer_exists: bool,
        memories: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        if state == "main_menu":
            return self._handle_main_menu(option=option, contact=contact, customer_exists=customer_exists)
        if state == "pricing_menu":
            return self._handle_pricing_menu(option=option, contact=contact, customer_exists=customer_exists)
        if state == "studio_menu":
            return self._handle_studio_menu(option=option, contact=contact, customer_exists=customer_exists)
        if state == "location_menu":
            return self._handle_location_menu(option=option, contact=contact, customer_exists=customer_exists)
        if state == "structure_menu":
            return self._handle_structure_menu(option=option, contact=contact, customer_exists=customer_exists)
        if state == "human_menu":
            return self._handle_human_menu(option=option, contact=contact, customer_exists=customer_exists)
        if state in {"booking_menu", "booking_after_link"}:
            return self._invalid_numeric(state="booking_after_link", contact=contact, customer_exists=customer_exists, memories=memories)
        return self._main_menu_response(contact=contact, customer_exists=customer_exists, from_return=False, memories=memories)

    def _handle_main_menu(self, *, option: str, contact: Any, customer_exists: bool) -> dict[str, Any]:
        if option == "1":
            return self._booking_link_response(customer_exists=customer_exists)
        if option == "2":
            return self._pricing_menu_response()
        if option == "3":
            return self._studio_menu_response()
        if option == "4":
            return self._location_menu_response()
        if option == "5":
            return self._structure_menu_response()
        if option == "6":
            return self._human_menu_response()
        return self._invalid_numeric(state="main_menu", contact=contact, customer_exists=customer_exists, memories=None)

    def _handle_pricing_menu(self, *, option: str, contact: Any, customer_exists: bool) -> dict[str, Any]:
        options: dict[str, tuple[str, list[dict[str, str]]]] = {
            "1": (
                "O valor de 1 hora na FC VIP e:\n\n"
                "Valor padrao: R$130\n"
                "Valor para membro Descontos VIP: R$75\n\n"
                "A assinatura de membro e R$25.\n\n"
                "Para agendar, escolha a opcao 1 no menu principal.\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                [
                    {"memory_key": "interesse", "memory_value": "preco"},
                    {"memory_key": "pacote_interesse", "memory_value": "1h"},
                ],
            ),
            "2": (
                "O valor de 2 horas na FC VIP e:\n\n"
                "Valor padrao: R$250\n"
                "Valor para membro Descontos VIP: R$147\n\n"
                "A assinatura de membro e R$25.\n\n"
                "Para agendar, escolha a opcao 1 no menu principal.\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                [
                    {"memory_key": "interesse", "memory_value": "preco"},
                    {"memory_key": "pacote_interesse", "memory_value": "2h"},
                ],
            ),
            "3": (
                "O valor de 3 horas na FC VIP e:\n\n"
                "Valor padrao: R$380\n"
                "Valor para membro Descontos VIP: R$220\n\n"
                "A assinatura de membro e R$25.\n\n"
                "Para agendar, escolha a opcao 1 no menu principal.\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                [
                    {"memory_key": "interesse", "memory_value": "preco"},
                    {"memory_key": "pacote_interesse", "memory_value": "3h"},
                ],
            ),
            "4": (
                "Valores da FC VIP:\n\n"
                "1 hora:\nValor padrao: R$130\nMembro Descontos VIP: R$75\n\n"
                "2 horas:\nValor padrao: R$250\nMembro Descontos VIP: R$147\n\n"
                "3 horas:\nValor padrao: R$380\nMembro Descontos VIP: R$220\n\n"
                "A assinatura de membro e R$25.\n\n"
                "Para agendar, escolha a opcao 1 no menu principal.\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                [{"memory_key": "interesse", "memory_value": "preco"}],
            ),
            "5": (
                "Sendo membro Descontos VIP, voce consegue valores reduzidos na FC VIP.\n\n"
                "Valores de membro:\n\n"
                "1 hora: R$75\n"
                "2 horas: R$147\n"
                "3 horas: R$220\n\n"
                "A assinatura de membro e R$25 e tambem da acesso a beneficios em outros parceiros.\n\n"
                "Conheca mais:\n"
                "https://descontoss-vip.com\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                [{"memory_key": "interesse_membro", "memory_value": "sim"}],
            ),
        }
        if option not in options:
            return self._invalid_numeric(state="pricing_menu", contact=contact, customer_exists=customer_exists, memories=None)
        text, memory_updates = options[option]
        return self._response(text=text, state="pricing_menu", memory_updates=memory_updates)

    def _handle_studio_menu(self, *, option: str, contact: Any, customer_exists: bool) -> dict[str, Any]:
        options: dict[str, tuple[str, list[dict[str, str]]]] = {
            "1": (
                "A FC VIP e um espaco de fotografia e producao audiovisual em Volta Redonda.\n\n"
                "O estudio foi criado para facilitar producoes de foto e video com estrutura pronta, iluminacao completa e ambientes preparados para criacao.\n\n"
                "Voce tambem pode ver a landing page com o video tour:\n"
                "https://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                [{"memory_key": "interesse", "memory_value": "conhecer_estudio"}],
            ),
            "2": (
                "A FC VIP e ideal para fotografos, videomakers, criadores de conteudo, marcas, empresas, profissionais liberais e pessoas que querem produzir fotos ou videos com estrutura profissional.\n\n"
                "Voce tambem pode ver a landing page com o video tour:\n"
                "https://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                [{"memory_key": "interesse", "memory_value": "publico_estudio"}],
            ),
            "3": (
                "Voce pode conhecer mais sobre a FC VIP e ver o video tour pela landing page:\n\n"
                "https://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                [{"memory_key": "interesse", "memory_value": "site"}],
            ),
        }
        if option not in options:
            return self._invalid_numeric(state="studio_menu", contact=contact, customer_exists=customer_exists, memories=None)
        text, memory_updates = options[option]
        return self._response(text=text, state="studio_menu", memory_updates=memory_updates)

    def _handle_location_menu(self, *, option: str, contact: Any, customer_exists: bool) -> dict[str, Any]:
        if option == "1":
            booking_response = self._booking_link_response(customer_exists=customer_exists)
            booking_response["memory_updates"] = list(booking_response.get("memory_updates") or []) + [
                {"memory_key": "origem", "memory_value": "localizacao"}
            ]
            return booking_response
        if option == "2":
            return self._response(
                text=(
                    "Voce pode conhecer mais sobre a FC VIP e ver o video tour pela landing page:\n\n"
                    "https://www.fcvip.com.br\n\n"
                    "9 - Voltar ao menu principal\n"
                    "0 - Encerrar atendimento"
                ),
                state="location_menu",
                memory_updates=[{"memory_key": "interesse", "memory_value": "localizacao"}],
            )
        return self._invalid_numeric(state="location_menu", contact=contact, customer_exists=customer_exists, memories=None)

    def _handle_structure_menu(self, *, option: str, contact: Any, customer_exists: bool) -> dict[str, Any]:
        responses: dict[str, tuple[str, str]] = {
            "1": (
                "A FC VIP conta com fundos fotograficos variados:\n\n"
                "- 3 roxos instagramaveis\n"
                "- 2 brancos de 3x3m\n"
                "- 2 pretos de 3x3m\n"
                "- 2 verdes de 3x3m\n"
                "- 1 roxo padrao\n"
                "- 1 pano laranja\n\n"
                "Voce tambem pode ver a landing page com o video tour:\n"
                "https://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                "fundos_fotograficos",
            ),
            "2": (
                "A FC VIP conta com iluminacao completa para producoes de foto e video:\n\n"
                "- 4 softboxes Tomate MLG-065\n"
                "- 2 bastoes de LED GTP\n"
                "- 2 refletores de 40w\n"
                "- 2 luzes de video LED Pocket\n"
                "- 4 luzes ShowTech\n"
                "- 1 luz circular conceitual laranja\n"
                "- 1 rebatedor/difusor\n\n"
                "Voce tambem pode ver a landing page com o video tour:\n"
                "https://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                "iluminacao",
            ),
            "3": (
                "A FC VIP possui tripes e suportes para apoiar diferentes tipos de producao:\n\n"
                "- 7 tripes para iluminacao\n"
                "- 4 tripes para fundo fotografico\n"
                "- 4 suportes articulaveis para camera\n"
                "- 3 tripes padrao para camera/celular\n"
                "- 1 suporte articulavel para celular\n\n"
                "Voce tambem pode ver a landing page com o video tour:\n"
                "https://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                "tripes_suportes",
            ),
            "4": (
                "A FC VIP conta com itens de cenografia para compor diferentes estilos de producao:\n\n"
                "- 2 banquetas pretas\n"
                "- bancos baixos preto e branco\n"
                "- poltronas\n"
                "- sofa\n"
                "- mesas de centro de vidro\n"
                "- tapetes variados brancos, verdes e vermelhos\n"
                "- vasos\n"
                "- velas\n"
                "- luminaria\n"
                "- elefante decorativo\n\n"
                "Voce tambem pode ver a landing page com o video tour:\n"
                "https://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                "cenografia",
            ),
            "5": (
                "A FC VIP tambem possui infraestrutura de apoio para as producoes:\n\n"
                "- 2 ar-condicionados\n"
                "- 3 ventiladores\n"
                "- filtro de agua\n"
                "- mesa de apoio\n"
                "- cabideiro\n"
                "- 10 garras\n"
                "- fontes para softbox\n"
                "- filtros de linha\n"
                "- extensao\n"
                "- adaptador\n\n"
                "Voce tambem pode ver a landing page com o video tour:\n"
                "https://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                "infraestrutura",
            ),
            "6": (
                "Voce pode conhecer a estrutura da FC VIP e ver o video tour pela landing page:\n\n"
                "https://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento",
                "video_tour",
            ),
        }
        if option not in responses:
            return self._invalid_numeric(state="structure_menu", contact=contact, customer_exists=customer_exists, memories=None)
        text, structure_value = responses[option]
        memory_updates = [{"memory_key": "interesse", "memory_value": "estrutura"}]
        if structure_value == "video_tour":
            memory_updates = [{"memory_key": "interesse", "memory_value": "video_tour"}]
        else:
            memory_updates.append({"memory_key": "estrutura_interesse", "memory_value": structure_value})
        return self._response(text=text, state="structure_menu", memory_updates=memory_updates)

    def _handle_human_menu(self, *, option: str, contact: Any, customer_exists: bool) -> dict[str, Any]:
        mapping = {
            "1": ("agendamento", "Certo. Vou registrar que voce quer falar com um atendente sobre agendamento."),
            "2": ("valores", "Certo. Vou registrar que voce quer falar com um atendente sobre valores."),
            "3": ("problema_agendamento", "Certo. Vou registrar que voce precisa de ajuda com um agendamento."),
            "4": ("parceria", "Certo. Vou registrar seu interesse em parceria ou atuacao profissional com a FC VIP."),
            "5": ("outro", "Certo. Vou registrar que voce quer falar com um atendente sobre outro assunto."),
        }
        if option not in mapping:
            return self._invalid_numeric(state="human_menu", contact=contact, customer_exists=customer_exists, memories=None)
        reason, lead = mapping[option]
        response = self._response(
            text=f"{lead}\n\nUm atendente podera seguir com voce assim que possivel.",
            state="human_menu",
            memory_updates=[{"memory_key": "human_reason", "memory_value": reason}],
        )
        response["needs_human"] = True
        response["human_reason"] = reason
        response["dashboard_notification"] = True
        return response

    def _booking_link_response(self, *, customer_exists: bool) -> dict[str, Any]:
        if customer_exists:
            return self._response(
                text=(
                    "Para fazer seu agendamento pela FC VIP, acesse:\n\n"
                    "https://www.fcvip.com.br/agendamentos\n\n"
                    "9 - Voltar ao menu principal\n"
                    "0 - Encerrar atendimento"
                ),
                state="booking_after_link",
                memory_updates=[
                    {"memory_key": "interesse", "memory_value": "agendamento"},
                    {"memory_key": "tipo_agendamento", "memory_value": "cliente_antigo"},
                ],
            )
        return self._response(
            text=(
                "Para fazer um novo agendamento na FC VIP, preencha o formulario abaixo:\n\n"
                "https://www.fcvip.com.br/formulario\n\n"
                "Por la voce informa os dados da producao e o horario desejado.\n\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento"
            ),
            state="booking_after_link",
            memory_updates=[
                {"memory_key": "interesse", "memory_value": "agendamento"},
                {"memory_key": "tipo_agendamento", "memory_value": "novo"},
            ],
        )

    def _main_menu_response(
        self,
        *,
        contact: Any,
        customer_exists: bool,
        from_return: bool,
        memories: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        if from_return:
            greeting = "Voltamos ao menu principal."
        elif customer_exists:
            name = self._resolve_customer_name(contact=contact, memories=memories)
            if name:
                greeting = f"Ola, {name}! Seja bem-vindo(a) de volta a FC VIP."
            else:
                greeting = "Ola! Seja bem-vindo(a) de volta a FC VIP."
        else:
            greeting = "Atendimento iniciado."
        memory_updates = [{"memory_key": "cliente_status", "memory_value": "antigo" if customer_exists else "novo"}]
        return self._response(
            text=(
                f"{greeting}\n\n"
                "Escolha uma opcao:\n\n"
                f"{self.MAIN_MENU_OPTIONS}\n\n"
                "Digite apenas o numero da opcao desejada."
            ),
            state="main_menu",
            memory_updates=memory_updates,
        )

    def _pricing_menu_response(self) -> dict[str, Any]:
        return self._response(
            text=(
                "Escolha qual valor deseja consultar:\n\n"
                "1 - 1 hora de estudio\n"
                "2 - 2 horas de estudio\n"
                "3 - 3 horas de estudio\n"
                "4 - Ver todos os valores\n"
                "5 - Entender desconto de membro\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento\n\n"
                "Digite apenas o numero da opcao desejada."
            ),
            state="pricing_menu",
        )

    def _studio_menu_response(self) -> dict[str, Any]:
        return self._response(
            text=(
                "O que voce quer saber sobre a FC VIP?\n\n"
                "1 - O que e a FC VIP\n"
                "2 - Para quem e o estudio\n"
                "3 - Ver o site e video tour\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento\n\n"
                "Digite apenas o numero da opcao desejada."
            ),
            state="studio_menu",
        )

    def _location_menu_response(self) -> dict[str, Any]:
        return self._response(
            text=(
                "A FC VIP fica na:\n\n"
                "Rua Corifeu Marques, 32\n"
                "Jardim Amalia 1\n"
                "Volta Redonda - RJ\n\n"
                "Escolha uma opcao:\n\n"
                "1 - Fazer agendamento\n"
                "2 - Conhecer o site e video tour\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento\n\n"
                "Digite apenas o numero da opcao desejada."
            ),
            state="location_menu",
        )

    def _structure_menu_response(self) -> dict[str, Any]:
        return self._response(
            text=(
                "Sobre a estrutura da FC VIP, escolha uma opcao:\n\n"
                "1 - Fundos fotograficos\n"
                "2 - Iluminacao\n"
                "3 - Tripes e suportes\n"
                "4 - Cenografia\n"
                "5 - Infraestrutura\n"
                "6 - Ver landing page com video tour\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento\n\n"
                "Digite apenas o numero da opcao desejada."
            ),
            state="structure_menu",
        )

    def _human_menu_response(self) -> dict[str, Any]:
        return self._response(
            text=(
                "Voce quer falar com um atendente sobre qual assunto?\n\n"
                "1 - Agendamento\n"
                "2 - Valores\n"
                "3 - Problema com agendamento\n"
                "4 - Parceria / profissional audiovisual\n"
                "5 - Outro assunto\n"
                "9 - Voltar ao menu principal\n"
                "0 - Encerrar atendimento\n\n"
                "Digite apenas o numero da opcao desejada."
            ),
            state="human_menu",
        )

    def _render_state_menu(
        self,
        *,
        state: str,
        contact: Any,
        customer_exists: bool,
        memories: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        if state == "main_menu":
            return self._main_menu_response(contact=contact, customer_exists=customer_exists, from_return=False, memories=memories)
        if state == "pricing_menu":
            return self._pricing_menu_response()
        if state == "studio_menu":
            return self._studio_menu_response()
        if state == "location_menu":
            return self._location_menu_response()
        if state == "structure_menu":
            return self._structure_menu_response()
        if state in {"booking_menu", "booking_after_link"}:
            return self._booking_link_response(customer_exists=customer_exists)
        if state == "human_menu":
            return self._human_menu_response()
        return self._main_menu_response(contact=contact, customer_exists=customer_exists, from_return=False, memories=memories)

    def _invalid_non_numeric(
        self,
        *,
        state: str,
        contact: Any,
        customer_exists: bool,
        memories: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        menu = self._render_state_menu(state=state, contact=contact, customer_exists=customer_exists, memories=memories)
        menu["reply_text"] = "Para continuar, escolha uma opcao digitando apenas o numero.\n\n" + menu["reply_text"]
        return menu

    def _invalid_numeric(
        self,
        *,
        state: str,
        contact: Any,
        customer_exists: bool,
        memories: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        menu = self._render_state_menu(state=state, contact=contact, customer_exists=customer_exists, memories=memories)
        menu["reply_text"] = "Opcao invalida.\n\n" + menu["reply_text"]
        return menu

    def _end_response(self) -> dict[str, Any]:
        return self._response(
            text="Atendimento encerrado.\n\nSe precisar de algo depois, e so mandar uma nova mensagem.",
            state="end",
            close_conversation=True,
        )

    def _collect_retry_name(self, *, payload_data: dict[str, Any]) -> dict[str, Any]:
        return self._response(
            text="Para continuar, preciso do seu nome completo.\n\nExemplo:\nMaria Silva",
            state="collect_name",
            collected_customer_data=payload_data,
            customer_collection_step="collect_name",
        )

    def _collect_retry_phone(self, *, payload_data: dict[str, Any]) -> dict[str, Any]:
        return self._response(
            text=(
                "Esse telefone nao parece valido.\n\n"
                "Envie o telefone com DDD, usando apenas numeros.\n\n"
                "Exemplo:\n"
                "24999999999"
            ),
            state="collect_phone",
            collected_customer_data=payload_data,
            customer_collection_step="collect_phone",
        )

    def _collect_retry_email(self, *, payload_data: dict[str, Any]) -> dict[str, Any]:
        return self._response(
            text=(
                "Esse email nao parece valido.\n\n"
                "Envie um email nesse formato:\n\n"
                "cliente@email.com"
            ),
            state="collect_email",
            collected_customer_data=payload_data,
            customer_collection_step="collect_email",
        )

    def _collect_retry_instagram(self, *, payload_data: dict[str, Any]) -> dict[str, Any]:
        return self._response(
            text="Envie seu Instagram com ou sem @.\n\nExemplo:\n@fcvip",
            state="collect_instagram",
            collected_customer_data=payload_data,
            customer_collection_step="collect_instagram",
        )

    def _collect_retry_facebook(self, *, payload_data: dict[str, Any]) -> dict[str, Any]:
        return self._response(
            text="Envie seu Facebook, usuario ou link.\n\nExemplo:\nfacebook.com/seunome",
            state="collect_facebook",
            collected_customer_data=payload_data,
            customer_collection_step="collect_facebook",
        )

    def _response(
        self,
        *,
        text: str,
        state: str,
        memory_updates: list[dict[str, str]] | None = None,
        needs_human: bool = False,
        human_reason: str | None = None,
        close_conversation: bool = False,
        collected_customer_data: dict[str, Any] | None = None,
        customer_collection_step: str | None = None,
    ) -> dict[str, Any]:
        return {
            "reply_text": text,
            "next_state": state,
            "memory_updates": memory_updates or [],
            "needs_human": needs_human,
            "human_reason": human_reason,
            "close_conversation": close_conversation,
            "chatbot_should_reply": True,
            "dashboard_notification": False,
            "collected_customer_data": dict(collected_customer_data or {}),
            "customer_collection_step": customer_collection_step,
        }

    def _validate_name(self, text: str) -> str | None:
        candidate = " ".join(str(text or "").split()).strip()
        if not candidate:
            return None
        if "@" in candidate:
            return None
        if any(ch.isdigit() for ch in candidate):
            return None
        words = [word for word in candidate.split(" ") if word]
        if len(words) < 2:
            return None
        normalized_words = []
        for word in words:
            clean_word = re.sub(r"[^A-Za-zÀ-ÿ'-]", "", word).strip()
            if len(clean_word) < 2:
                return None
            normalized_words.append(clean_word)
        if not normalized_words:
            return None
        return " ".join(word[:1].upper() + word[1:] for word in normalized_words)

    def _validate_phone(self, text: str) -> str | None:
        raw = str(text or "").strip()
        if not raw:
            return None
        sanitized = raw.replace(" ", "").replace("(", "").replace(")", "").replace("-", "").replace("+", "")
        if not sanitized.isdigit():
            return None
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) < 10:
            return None
        if self._REPEATED_DIGITS_RE.match(digits):
            return None
        if digits.startswith("55"):
            if len(digits) not in {12, 13}:
                return None
            return f"+{digits}"
        if len(digits) not in {10, 11}:
            return None
        return f"+55{digits}"

    def _validate_email(self, text: str) -> str | None:
        email = str(text or "").strip().lower()
        if not email:
            return None
        if " " in email:
            return None
        if not self._EMAIL_RE.match(email):
            return None
        return email

    def _normalize_instagram(self, *, text: str, normalized: str) -> str:
        if normalized in self._SKIP_OPTIONAL_VALUES:
            return ""
        candidate = str(text or "").strip()
        if not candidate:
            return ""
        lowered = candidate.lower()
        if "instagram.com/" in lowered:
            candidate = candidate.split("instagram.com/", 1)[1]
        candidate = candidate.split("?", 1)[0].split("/", 1)[0].strip().lstrip("@")
        if not candidate:
            return "__invalid__"
        if " " in candidate:
            return "__invalid__"
        if not self._INSTAGRAM_USER_RE.match(candidate):
            return "__invalid__"
        digits_only = "".join(ch for ch in candidate if ch.isdigit())
        if digits_only and len(set(digits_only)) == 1 and len(digits_only) >= 6:
            return "__invalid__"
        return f"@{candidate.lower()}"

    def _normalize_facebook(self, *, text: str, normalized: str) -> str:
        if normalized in self._SKIP_OPTIONAL_VALUES:
            return ""
        candidate = str(text or "").strip()
        if not candidate:
            return ""
        lowered = candidate.lower()
        if "facebook.com/" in lowered:
            candidate = candidate.split("facebook.com/", 1)[1]
        candidate = candidate.split("?", 1)[0].split("/", 1)[0].strip().lstrip("@")
        if not candidate or len(candidate) < 2:
            return "__invalid__"
        if " " in candidate:
            return "__invalid__"
        if "@" in candidate or self._EMAIL_RE.match(candidate):
            return "__invalid__"
        digits = "".join(ch for ch in candidate if ch.isdigit())
        if len(digits) >= 10:
            return "__invalid__"
        return candidate.lower()

    def _normalize(self, value: str) -> str:
        lowered = str(value or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\s+", " ", normalized).strip()

    def _resolve_customer_name(self, *, contact: Any, memories: list[dict[str, Any]] | None) -> str | None:
        contact_name = " ".join(str(getattr(contact, "name", "") or "").split()).strip()
        if self._looks_like_reliable_name(contact_name):
            return contact_name
        for memory in memories or []:
            key = str(memory.get("key") or memory.get("memory_key") or "").strip().lower()
            if key != "nome_cliente":
                continue
            value = " ".join(str(memory.get("value") or memory.get("memory_value") or "").split()).strip()
            if self._looks_like_reliable_name(value):
                return value
        return None

    def _looks_like_reliable_name(self, value: str) -> bool:
        if len(value) < 4:
            return False
        normalized = self._normalize(value)
        if not normalized:
            return False
        if any(ch.isdigit() for ch in normalized):
            return False
        return len([word for word in normalized.split(" ") if word]) >= 2
