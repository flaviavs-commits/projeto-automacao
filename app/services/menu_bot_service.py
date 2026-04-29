from __future__ import annotations

import re
import unicodedata
from typing import Any


class MenuBotService:
    GREETINGS = {"oi", "ola", "bom dia", "boa tarde", "boa noite", "menu"}
    MAIN_MENU_OPTIONS = (
        "1 - Agendamento\n"
        "2 - Valores\n"
        "3 - Conhecer a FC VIP\n"
        "4 - Localizacao\n"
        "5 - Estrutura do estudio\n"
        "6 - Falar com atendente\n"
        "0 - Encerrar atendimento"
    )

    def handle_message(
        self,
        *,
        message_text: str,
        conversation: Any,
        contact: Any,
        customer_exists: bool,
        memories: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        text = " ".join(str(message_text or "").split()).strip()
        normalized = self._normalize(text)
        current_state = str(getattr(conversation, "menu_state", "") or "").strip() or None
        is_new_chat = bool(getattr(conversation, "is_new_chat", False)) or current_state is None

        if normalized == "0":
            return self._end_response()

        if normalized == "9":
            return self._main_menu_response(
                contact=contact,
                customer_exists=customer_exists,
                from_return=True,
                memories=memories,
            )

        if is_new_chat and not current_state:
            return self._new_chat_start(
                contact=contact,
                customer_exists=customer_exists,
                memories=memories,
            )

        state = current_state or "main_menu"
        if normalized in self.GREETINGS:
            return self._render_state_menu(
                state=state,
                contact=contact,
                customer_exists=customer_exists,
                memories=memories,
            )

        if state == "collect_new_customer_data":
            return self._handle_collect_data(
                text=text,
                contact=contact,
                customer_exists=customer_exists,
                memories=memories,
            )

        if not normalized.isdigit():
            return self._invalid_non_numeric(state=state, contact=contact, customer_exists=customer_exists)

        return self._handle_numeric_state(
            option=normalized,
            state=state,
            contact=contact,
            customer_exists=customer_exists,
        )

    def _new_chat_start(
        self,
        *,
        contact: Any,
        customer_exists: bool,
        memories: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if customer_exists:
            if self._resolve_customer_name(contact=contact, memories=memories) is None:
                return {
                    "reply_text": (
                        "Antes de continuar, preciso confirmar seus dados para manter o atendimento correto.\n\n"
                        "Por favor, envie seu nome completo."
                    ),
                    "next_state": "collect_new_customer_data",
                    "memory_updates": [{"memory_key": "cliente_status", "memory_value": "antigo"}],
                    "needs_human": False,
                    "human_reason": None,
                    "close_conversation": False,
                    "dashboard_notification": False,
                }
            return self._main_menu_response(
                contact=contact,
                customer_exists=True,
                from_return=False,
                memories=memories,
            )
        return {
            "reply_text": (
                "Ola! Seja bem-vindo(a) a FC VIP.\n\n"
                "Antes de continuar, preciso de alguns dados rapidos para iniciar seu atendimento.\n\n"
                "Por favor, envie seu nome completo."
            ),
            "next_state": "collect_new_customer_data",
            "memory_updates": [{"memory_key": "cliente_status", "memory_value": "novo"}],
            "needs_human": False,
            "human_reason": None,
            "close_conversation": False,
            "dashboard_notification": False,
        }

    def _handle_collect_data(
        self,
        *,
        text: str,
        contact: Any,
        customer_exists: bool,
        memories: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        trusted_name = self._resolve_customer_name(contact=contact, memories=memories)
        phone = str(getattr(contact, "phone", "") or "").strip()
        updates: list[dict[str, str]] = []

        if not trusted_name:
            if text.isdigit() and len(text) >= 8:
                return {
                    "reply_text": "Antes de seguir, preciso do seu nome completo.",
                    "next_state": "collect_new_customer_data",
                    "memory_updates": updates,
                    "needs_human": False,
                    "human_reason": None,
                    "close_conversation": False,
                    "dashboard_notification": False,
                }
            updates.append({"memory_key": "nome_cliente", "memory_value": text})
            if phone:
                main = self._main_menu_response(
                    contact=contact,
                    customer_exists=customer_exists,
                    from_return=False,
                    memories=memories,
                )
                main["memory_updates"] = updates + list(main.get("memory_updates") or [])
                return main
            return {
                "reply_text": "Agora me informe seu telefone com DDD (apenas numeros).",
                "next_state": "collect_new_customer_data",
                "memory_updates": updates,
                "needs_human": False,
                "human_reason": None,
                "close_conversation": False,
                "dashboard_notification": False,
            }

        if not phone:
            digits = "".join(ch for ch in text if ch.isdigit())
            if len(digits) < 10:
                return {
                    "reply_text": "Para continuar, envie seu telefone com DDD, digitando apenas numeros.",
                    "next_state": "collect_new_customer_data",
                    "memory_updates": [],
                    "needs_human": False,
                    "human_reason": None,
                    "close_conversation": False,
                    "dashboard_notification": False,
                }
            updates.append({"memory_key": "telefone", "memory_value": digits})
            main = self._main_menu_response(
                contact=contact,
                customer_exists=customer_exists,
                from_return=False,
                memories=memories,
            )
            main["memory_updates"] = updates + list(main.get("memory_updates") or [])
            return main

        return self._main_menu_response(
            contact=contact,
            customer_exists=customer_exists,
            from_return=False,
            memories=memories,
        )

    def _handle_numeric_state(self, *, option: str, state: str, contact: Any, customer_exists: bool) -> dict[str, Any]:
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
        if state in {
            "booking_menu",
            "booking_after_link",
            "backgrounds_menu",
            "lighting_menu",
            "supports_menu",
            "scenography_menu",
            "infrastructure_menu",
        }:
            return self._invalid_numeric(state=state, contact=contact, customer_exists=customer_exists)
        return self._invalid_numeric(state=state, contact=contact, customer_exists=customer_exists)

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
        return self._invalid_numeric(state="main_menu", contact=contact, customer_exists=customer_exists)

    def _handle_pricing_menu(self, *, option: str, contact: Any, customer_exists: bool) -> dict[str, Any]:
        map_texts = {
            "1": (
                "O valor de 1 hora na FC VIP e:\n\n"
                "Valor padrao: R$130\n"
                "Valor para membro Descontos VIP: R$75\n\n"
                "A assinatura de membro e R$25.\n\n"
                "Para agendar, escolha a opcao 1 no menu principal.\n\n"
                "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
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
                "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
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
                "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
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
                "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
                [{"memory_key": "interesse", "memory_value": "preco"}],
            ),
            "5": (
                "Sendo membro Descontos VIP, voce consegue valores reduzidos na FC VIP.\n\n"
                "Valores de membro:\n\n"
                "1 hora: R$75\n2 horas: R$147\n3 horas: R$220\n\n"
                "A assinatura de membro e R$25 e tambem da acesso a beneficios em outros parceiros.\n\n"
                "Conheca mais:\nhttps://descontoss-vip.com\n\n"
                "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
                [{"memory_key": "interesse_membro", "memory_value": "sim"}],
            ),
        }
        if option not in map_texts:
            return self._invalid_numeric(state="pricing_menu", contact=contact, customer_exists=customer_exists)
        text, memory = map_texts[option]
        return self._response(text, "pricing_menu", memory_updates=memory)

    def _handle_studio_menu(self, *, option: str, contact: Any, customer_exists: bool) -> dict[str, Any]:
        options = {
            "1": (
                "A FC VIP e um espaco de fotografia e producao audiovisual em Volta Redonda.\n\n"
                "O estudio foi criado para facilitar producoes de foto e video com estrutura pronta, iluminacao completa e ambientes preparados para criacao.\n\n"
                "Voce tambem pode ver a landing page com o video tour:\nhttps://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
                [{"memory_key": "interesse", "memory_value": "conhecer_estudio"}],
            ),
            "2": (
                "A FC VIP e ideal para fotografos, videomakers, criadores de conteudo, marcas, empresas, profissionais liberais e pessoas que querem produzir fotos ou videos com estrutura profissional.\n\n"
                "Voce tambem pode ver a landing page com o video tour:\nhttps://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
                [{"memory_key": "interesse", "memory_value": "publico_estudio"}],
            ),
            "3": (
                "Voce pode conhecer mais sobre a FC VIP e ver o video tour pela landing page:\n\n"
                "https://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
                [{"memory_key": "interesse", "memory_value": "site"}],
            ),
        }
        if option not in options:
            return self._invalid_numeric(state="studio_menu", contact=contact, customer_exists=customer_exists)
        text, memory = options[option]
        return self._response(text, "studio_menu", memory_updates=memory)

    def _handle_location_menu(self, *, option: str, contact: Any, customer_exists: bool) -> dict[str, Any]:
        if option == "1":
            response = self._booking_link_response(customer_exists=customer_exists)
            response["memory_updates"] = response["memory_updates"] + [
                {"memory_key": "origem", "memory_value": "localizacao"}
            ]
            return response
        if option == "2":
            return self._response(
                "Voce pode conhecer mais sobre a FC VIP e ver o video tour pela landing page:\n\n"
                "https://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
                "location_menu",
                memory_updates=[{"memory_key": "interesse", "memory_value": "localizacao"}],
            )
        return self._invalid_numeric(state="location_menu", contact=contact, customer_exists=customer_exists)

    def _handle_structure_menu(self, *, option: str, contact: Any, customer_exists: bool) -> dict[str, Any]:
        if option == "1":
            return self._backgrounds_menu_response()
        if option == "2":
            return self._lighting_menu_response()
        if option == "3":
            return self._supports_menu_response()
        if option == "4":
            return self._scenography_menu_response()
        if option == "5":
            return self._infrastructure_menu_response()
        if option == "6":
            return self._response(
                "Voce pode conhecer a estrutura da FC VIP e ver o video tour pela landing page:\n\n"
                "https://www.fcvip.com.br\n\n"
                "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
                "structure_menu",
                memory_updates=[{"memory_key": "interesse", "memory_value": "video_tour"}],
            )
        return self._invalid_numeric(state="structure_menu", contact=contact, customer_exists=customer_exists)

    def _handle_human_menu(self, *, option: str, contact: Any, customer_exists: bool) -> dict[str, Any]:
        mapping = {
            "1": ("agendamento", "Certo. Vou registrar que voce quer falar com um atendente sobre agendamento."),
            "2": ("valores", "Certo. Vou registrar que voce quer falar com um atendente sobre valores."),
            "3": ("problema_agendamento", "Certo. Vou registrar que voce precisa de ajuda com um agendamento."),
            "4": ("parceria", "Certo. Vou registrar seu interesse em parceria ou atuacao profissional com a FC VIP."),
            "5": ("outro", "Certo. Vou registrar que voce quer falar com um atendente sobre outro assunto."),
        }
        if option not in mapping:
            return self._invalid_numeric(state="human_menu", contact=contact, customer_exists=customer_exists)
        reason, lead = mapping[option]
        return {
            "reply_text": f"{lead}\n\nUm atendente podera seguir com voce assim que possivel.",
            "next_state": "human_menu",
            "memory_updates": [{"memory_key": "human_reason", "memory_value": reason}],
            "needs_human": True,
            "human_reason": reason,
            "close_conversation": False,
            "dashboard_notification": True,
        }

    def _booking_link_response(self, *, customer_exists: bool) -> dict[str, Any]:
        if customer_exists:
            return self._response(
                "Para fazer seu agendamento pela FC VIP, acesse:\n\n"
                "https://www.fcvip.com.br/agendamentos\n\n"
                "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
                "booking_after_link",
                memory_updates=[
                    {"memory_key": "interesse", "memory_value": "agendamento"},
                    {"memory_key": "tipo_agendamento", "memory_value": "cliente_antigo"},
                ],
            )
        return self._response(
            "Para fazer um novo agendamento na FC VIP, preencha o formulario abaixo:\n\n"
            "https://www.fcvip.com.br/formulario\n\n"
            "Por la voce informa os dados da producao e o horario desejado.\n\n"
            "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
            "booking_after_link",
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
        memories: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if customer_exists:
            name = self._resolve_customer_name(contact=contact, memories=memories)
            if name:
                greeting = f"Ola, {name}! Seja bem-vindo(a) de volta a FC VIP."
            else:
                greeting = "Ola! Seja bem-vindo(a) de volta a FC VIP."
            memory = [{"memory_key": "cliente_status", "memory_value": "antigo"}]
        else:
            greeting = "Atendimento iniciado com sucesso."
            memory = [{"memory_key": "cliente_status", "memory_value": "novo"}]
        if from_return:
            greeting = "Voltamos ao menu principal."
        return self._response(
            f"{greeting}\n\nEscolha uma opcao:\n\n{self.MAIN_MENU_OPTIONS}\n\nDigite apenas o numero da opcao desejada.",
            "main_menu",
            memory_updates=memory,
        )

    def _pricing_menu_response(self) -> dict[str, Any]:
        return self._response(
            "Escolha qual valor deseja consultar:\n\n"
            "1 - 1 hora de estudio\n"
            "2 - 2 horas de estudio\n"
            "3 - 3 horas de estudio\n"
            "4 - Ver todos os valores\n"
            "5 - Entender desconto de membro\n"
            "9 - Voltar ao menu principal\n"
            "0 - Encerrar atendimento\n\n"
            "Digite apenas o numero da opcao desejada.",
            "pricing_menu",
        )

    def _studio_menu_response(self) -> dict[str, Any]:
        return self._response(
            "O que voce quer saber sobre a FC VIP?\n\n"
            "1 - O que e a FC VIP\n"
            "2 - Para quem e o estudio\n"
            "3 - Ver o site e video tour\n"
            "9 - Voltar ao menu principal\n"
            "0 - Encerrar atendimento\n\n"
            "Digite apenas o numero da opcao desejada.",
            "studio_menu",
        )

    def _location_menu_response(self) -> dict[str, Any]:
        return self._response(
            "A FC VIP fica na:\n\n"
            "Rua Corifeu Marques, 32\n"
            "Jardim Amalia 1\n"
            "Volta Redonda - RJ\n\n"
            "Escolha uma opcao:\n\n"
            "1 - Fazer agendamento\n"
            "2 - Conhecer o site e video tour\n"
            "9 - Voltar ao menu principal\n"
            "0 - Encerrar atendimento\n\n"
            "Digite apenas o numero da opcao desejada.",
            "location_menu",
        )

    def _structure_menu_response(self) -> dict[str, Any]:
        return self._response(
            "Sobre a estrutura da FC VIP, escolha uma opcao:\n\n"
            "1 - Fundos fotograficos\n"
            "2 - Iluminacao\n"
            "3 - Tripes e suportes\n"
            "4 - Cenografia\n"
            "5 - Infraestrutura\n"
            "6 - Ver landing page com video tour\n"
            "9 - Voltar ao menu principal\n"
            "0 - Encerrar atendimento\n\n"
            "Digite apenas o numero da opcao desejada.",
            "structure_menu",
        )

    def _backgrounds_menu_response(self) -> dict[str, Any]:
        return self._response(
            "A FC VIP conta com fundos fotograficos variados:\n\n"
            "- 3 roxos instagramaveis\n"
            "- 2 brancos de 3x3m\n"
            "- 2 pretos de 3x3m\n"
            "- 2 verdes de 3x3m\n"
            "- 1 roxo padrao\n"
            "- 1 pano laranja\n\n"
            "Voce tambem pode ver a landing page com o video tour:\n"
            "https://www.fcvip.com.br\n\n"
            "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
            "backgrounds_menu",
            memory_updates=[
                {"memory_key": "interesse", "memory_value": "estrutura"},
                {"memory_key": "estrutura_interesse", "memory_value": "fundos_fotograficos"},
            ],
        )

    def _lighting_menu_response(self) -> dict[str, Any]:
        return self._response(
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
            "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
            "lighting_menu",
            memory_updates=[
                {"memory_key": "interesse", "memory_value": "estrutura"},
                {"memory_key": "estrutura_interesse", "memory_value": "iluminacao"},
            ],
        )

    def _supports_menu_response(self) -> dict[str, Any]:
        return self._response(
            "A FC VIP possui tripes e suportes para apoiar diferentes tipos de producao:\n\n"
            "- 7 tripes para iluminacao\n"
            "- 4 tripes para fundo fotografico\n"
            "- 4 suportes articulaveis para camera\n"
            "- 3 tripes padrao para camera/celular\n"
            "- 1 suporte articulavel para celular\n\n"
            "Voce tambem pode ver a landing page com o video tour:\n"
            "https://www.fcvip.com.br\n\n"
            "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
            "supports_menu",
            memory_updates=[
                {"memory_key": "interesse", "memory_value": "estrutura"},
                {"memory_key": "estrutura_interesse", "memory_value": "tripes_suportes"},
            ],
        )

    def _scenography_menu_response(self) -> dict[str, Any]:
        return self._response(
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
            "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
            "scenography_menu",
            memory_updates=[
                {"memory_key": "interesse", "memory_value": "estrutura"},
                {"memory_key": "estrutura_interesse", "memory_value": "cenografia"},
            ],
        )

    def _infrastructure_menu_response(self) -> dict[str, Any]:
        return self._response(
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
            "9 - Voltar ao menu principal\n0 - Encerrar atendimento",
            "infrastructure_menu",
            memory_updates=[
                {"memory_key": "interesse", "memory_value": "estrutura"},
                {"memory_key": "estrutura_interesse", "memory_value": "infraestrutura"},
            ],
        )

    def _human_menu_response(self) -> dict[str, Any]:
        return self._response(
            "Voce quer falar com um atendente sobre qual assunto?\n\n"
            "1 - Agendamento\n"
            "2 - Valores\n"
            "3 - Problema com agendamento\n"
            "4 - Parceria / profissional audiovisual\n"
            "5 - Outro assunto\n"
            "9 - Voltar ao menu principal\n"
            "0 - Encerrar atendimento\n\n"
            "Digite apenas o numero da opcao desejada.",
            "human_menu",
        )

    def _render_state_menu(
        self,
        *,
        state: str,
        contact: Any,
        customer_exists: bool,
        memories: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if state == "main_menu":
            return self._main_menu_response(
                contact=contact,
                customer_exists=customer_exists,
                from_return=False,
                memories=memories,
            )
        if state == "pricing_menu":
            return self._pricing_menu_response()
        if state == "studio_menu":
            return self._studio_menu_response()
        if state == "location_menu":
            return self._location_menu_response()
        if state == "structure_menu":
            return self._structure_menu_response()
        if state == "backgrounds_menu":
            return self._backgrounds_menu_response()
        if state == "lighting_menu":
            return self._lighting_menu_response()
        if state == "supports_menu":
            return self._supports_menu_response()
        if state == "scenography_menu":
            return self._scenography_menu_response()
        if state == "infrastructure_menu":
            return self._infrastructure_menu_response()
        if state in {"booking_menu", "booking_after_link"}:
            return self._booking_link_response(customer_exists=customer_exists)
        if state == "human_menu":
            return self._human_menu_response()
        if state == "collect_new_customer_data":
            return {
                "reply_text": "Para continuar, envie seu nome completo.",
                "next_state": "collect_new_customer_data",
                "memory_updates": [],
                "needs_human": False,
                "human_reason": None,
                "close_conversation": False,
                "dashboard_notification": False,
            }
        return self._main_menu_response(
            contact=contact,
            customer_exists=customer_exists,
            from_return=False,
            memories=memories,
        )

    def _invalid_non_numeric(
        self,
        *,
        state: str,
        contact: Any,
        customer_exists: bool,
        memories: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        menu = self._render_state_menu(
            state=state,
            contact=contact,
            customer_exists=customer_exists,
            memories=memories,
        )
        menu["reply_text"] = "Para continuar, escolha uma opcao digitando apenas o numero.\n\n" + menu["reply_text"]
        return menu

    def _invalid_numeric(
        self,
        *,
        state: str,
        contact: Any,
        customer_exists: bool,
        memories: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        menu = self._render_state_menu(
            state=state,
            contact=contact,
            customer_exists=customer_exists,
            memories=memories,
        )
        menu["reply_text"] = "Opcao invalida.\n\n" + menu["reply_text"]
        return menu

    def _end_response(self) -> dict[str, Any]:
        return {
            "reply_text": "Atendimento encerrado.\n\nSe precisar de algo depois, e so mandar uma nova mensagem.",
            "next_state": "end",
            "memory_updates": [],
            "needs_human": False,
            "human_reason": None,
            "close_conversation": True,
            "dashboard_notification": False,
        }

    def _response(self, text: str, state: str, *, memory_updates: list[dict[str, str]] | None = None) -> dict[str, Any]:
        return {
            "reply_text": text,
            "next_state": state,
            "memory_updates": memory_updates or [],
            "needs_human": False,
            "human_reason": None,
            "close_conversation": False,
            "dashboard_notification": False,
        }

    def _normalize(self, value: str) -> str:
        lowered = str(value or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _resolve_customer_name(self, *, contact: Any, memories: list[dict[str, Any]] | None = None) -> str | None:
        memory_name = self._extract_memory_value(memories=memories, key="nome_cliente")
        if self._is_reliable_name(memory_name):
            return memory_name
        contact_name = str(getattr(contact, "name", "") or "").strip()
        if self._is_reliable_name(contact_name):
            return contact_name
        return None

    def _extract_memory_value(self, *, memories: list[dict[str, Any]] | None, key: str) -> str:
        for item in list(memories or []):
            item_key = str(item.get("key") or item.get("memory_key") or "").strip().lower()
            if item_key != str(key or "").strip().lower():
                continue
            value = str(item.get("value") or item.get("memory_value") or "").strip()
            if value:
                return value
        return ""

    def _is_reliable_name(self, value: str | None) -> bool:
        cleaned = " ".join(str(value or "").split()).strip()
        if len(cleaned) < 4:
            return False
        normalized = self._normalize(cleaned)
        if not normalized:
            return False
        blocked_markers = {
            "teste",
            "test",
            "codex",
            "railway",
            "cli",
            "spam",
            "probe",
            "user",
        }
        if any(marker in normalized for marker in blocked_markers):
            return False
        return True
