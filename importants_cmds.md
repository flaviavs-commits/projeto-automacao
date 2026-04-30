## Comandos importantes para salvar

rodar qa test em py (terminal):  .\.venv\Scripts\python.exe qa_tudo.py --no-pause
rodar qa test em py (dashboard): >d:/Projeto/Chosen/projeto-automacao/.venv/Scripts/python.exe d:/Projeto/Chosen/projeto-automacao/qa_tudo.py

## Links importantes para salvar

API Railway (raiz): https://projeto-automacao-production.up.railway.app/
Dashboard API Railway: https://projeto-automacao-production.up.railway.app/dashboard



##
<!-- Você vai implementar um chatbot de menu fechado para atendimento WhatsApp da FC VIP.
Contexto:

- Não queremos LLM.
- Não queremos classificador de intenção.
- Não queremos interpretar texto livre.
- O bot deve funcionar por menus numéricos.
- O cliente recebe opções 1, 2, 3, 4, 5, 6...
- Depois escolhe uma opção e pode receber subopções.
- A lógica é: estado atual da conversa + número digitado = próxima resposta.
- Se o cliente digitar texto livre, o bot deve pedir para escolher uma opção numérica.
- Não reativar llm-runtime.
- Não usar OpenAI.
- Não mexer no gateway Baileys nesta task.
- Não mexer em Railway nesta task, salvo se for estritamente necessário.
- Preservar webhook, worker, dashboard, follow-up e fallback de canal já existentes.
- Seguir obrigatoriamente os padrões da pasta felixo_standards.
- Usar TDD: primeiro criar testes, depois implementar.

Regra TDD obrigatória:

1. Antes de programar a funcionalidade, criar testes cobrindo o comportamento esperado.
2. Rodar os testes e confirmar que inicialmente falham quando a funcionalidade ainda não existe.
3. Implementar a funcionalidade.
4. Rodar novamente os testes até passar.
5. Rodar QA completo ao final.
6. Nenhuma implementação deve ser considerada concluída sem testes.

Objetivo:

Criar um serviço novo:

app/services/menu_bot_service.py

Esse serviço deve receber:
- texto da mensagem;
- conversa;
- contato;
- dados/memórias do contato, quando disponíveis.

E retornar:
- reply_text;
- next_state;
- memory_updates;
- needs_human;
- human_reason;
- close_conversation;
- dashboard_notification, quando aplicável.

Estados iniciais:

- start_new_chat
- collect_new_customer_data
- main_menu
- booking_menu
- booking_after_link
- pricing_menu
- studio_menu
- location_menu
- structure_menu
- backgrounds_menu
- lighting_menu
- supports_menu
- scenography_menu
- infrastructure_menu
- human_menu
- end

Regra de início de conversa nova:

Essa regra só vale para chat novo iniciado.

Se o chat já está em andamento, continuar o atendimento normal pelo menu_state salvo.

Ao iniciar um chat novo:

1. Verificar se o cliente já existe na base de dados.

2. Se cliente for antigo/já existir na database:
   - usar o nome se estiver disponível.
   - responder:

"Olá, [nome do cliente]! Seja bem-vindo(a) de volta à FC VIP.

Escolha uma opção:

1 - Agendamento
2 - Valores
3 - Conhecer a FC VIP
4 - Localização
5 - Estrutura do estúdio
6 - Falar com atendente
0 - Encerrar atendimento

Digite apenas o número da opção desejada."

   - salvar estado main_menu.

3. Se cliente for novo:
   - iniciar coleta de dados antes do menu principal.
   - pedir dados mínimos de identificação.
   - sugestão de primeira mensagem:

"Olá! Seja bem-vindo(a) à FC VIP.

Antes de continuar, preciso de alguns dados rápidos para iniciar seu atendimento.

Por favor, envie seu nome completo."

   - depois coletar telefone se ainda não houver telefone confiável no evento.
   - depois de coletar os dados mínimos, mostrar o menu principal.

Observação:
- Se o número/telefone já veio do WhatsApp/Baileys e for confiável, não perguntar telefone novamente.
- Se não houver nome, perguntar nome.
- Não salvar cliente novo como cliente definitivo sem dados mínimos.
- Se o cliente abandonar antes de concluir dados, manter como temporário conforme regra já discutida.

Regra importante de agendamento por tipo de cliente:

- Cliente novo recebe link:
  https://www.fcvip.com.br/formulario

- Cliente antigo/já existente na database recebe link:
  https://www.fcvip.com.br/agendamentos

- Nunca enviar /formulario para cliente que já existe na database quando ele for fazer agendamento.
- Não usar mais a opção "consultar ou ajustar agendamento existente".
- A opção de agendamento deve decidir automaticamente o link correto pelo status do cliente.

Correção de endereço:

Corrigir qualquer referência antiga de endereço que diga Jardim Amália 2.

O endereço correto é:

Rua Corifeu Marques, 32
Jardim Amália 1
Volta Redonda - RJ

Atualizar também:
- README.md
- ia.md
- humano.md
- base/prompt/memória onde constar Jardim Amália 2
- qualquer template antigo com endereço incorreto

Regras globais:

1. Se a mensagem for saudação:
   - oi
   - olá
   - ola
   - bom dia
   - boa tarde
   - boa noite
   - menu

   Se for chat novo, aplicar regra de início de conversa nova.
   Se não for chat novo, mostrar ou repetir o menu atual.

2. Se não existir estado salvo da conversa:
   - tratar como chat novo.

3. Em qualquer estado:
   - 0 encerra atendimento.
   - 9 volta ao menu principal.

4. Se o cliente digitar algo que não seja número e não seja saudação/menu:
   responder:
   "Para continuar, escolha uma opção digitando apenas o número."
   E repetir o menu atual.

5. Se o cliente digitar número inválido para o estado atual:
   responder:
   "Opção inválida."
   E repetir o menu atual.

6. Não tentar interpretar texto livre como "quanto custa", "quero agendar", "onde fica", "tem luz".
   Nesses casos, repetir menu e pedir número.

Menu principal:

Texto para cliente novo depois da coleta:

"Atendimento iniciado com sucesso.

Escolha uma opção:

1 - Agendamento
2 - Valores
3 - Conhecer a FC VIP
4 - Localização
5 - Estrutura do estúdio
6 - Falar com atendente
0 - Encerrar atendimento

Digite apenas o número da opção desejada."

Texto para cliente antigo:

"Olá, [nome do cliente]! Seja bem-vindo(a) de volta à FC VIP.

Escolha uma opção:

1 - Agendamento
2 - Valores
3 - Conhecer a FC VIP
4 - Localização
5 - Estrutura do estúdio
6 - Falar com atendente
0 - Encerrar atendimento

Digite apenas o número da opção desejada."

Estado: main_menu

Opções do main_menu:

1 -> booking_menu
2 -> pricing_menu
3 -> studio_menu
4 -> location_menu
5 -> structure_menu
6 -> human_menu
0 -> end

booking_menu:

Não criar submenu com "consultar agendamento existente".

Ao escolher agendamento, responder diretamente com o link correto de acordo com o tipo de cliente.

Se cliente novo:

"Para fazer um novo agendamento na FC VIP, preencha o formulário abaixo:

https://www.fcvip.com.br/formulario

Por lá você informa os dados da produção e o horário desejado.

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Se cliente antigo/já existente na database:

"Para fazer seu agendamento pela FC VIP, acesse:

https://www.fcvip.com.br/agendamentos

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Salvar memória:
interesse=agendamento

Se cliente novo:
tipo_agendamento=novo

Se cliente antigo:
tipo_agendamento=cliente_antigo

pricing_menu:

Texto:

"Escolha qual valor deseja consultar:

1 - 1 hora de estúdio
2 - 2 horas de estúdio
3 - 3 horas de estúdio
4 - Ver todos os valores
5 - Entender desconto de membro
9 - Voltar ao menu principal
0 - Encerrar atendimento

Digite apenas o número da opção desejada."

Opções:

1:
"O valor de 1 hora na FC VIP é:

Valor padrão: R$130
Valor para membro Descontos VIP: R$75

A assinatura de membro é R$25.

Para agendar, escolha a opção 1 no menu principal.

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=preco
pacote_interesse=1h

2:
"O valor de 2 horas na FC VIP é:

Valor padrão: R$250
Valor para membro Descontos VIP: R$147

A assinatura de membro é R$25.

Para agendar, escolha a opção 1 no menu principal.

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=preco
pacote_interesse=2h

3:
"O valor de 3 horas na FC VIP é:

Valor padrão: R$380
Valor para membro Descontos VIP: R$220

A assinatura de membro é R$25.

Para agendar, escolha a opção 1 no menu principal.

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=preco
pacote_interesse=3h

4:
"Valores da FC VIP:

1 hora:
Valor padrão: R$130
Membro Descontos VIP: R$75

2 horas:
Valor padrão: R$250
Membro Descontos VIP: R$147

3 horas:
Valor padrão: R$380
Membro Descontos VIP: R$220

A assinatura de membro é R$25.

Para agendar, escolha a opção 1 no menu principal.

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=preco

5:
"Sendo membro Descontos VIP, você consegue valores reduzidos na FC VIP.

Valores de membro:

1 hora: R$75
2 horas: R$147
3 horas: R$220

A assinatura de membro é R$25 e também dá acesso a benefícios em outros parceiros.

Conheça mais:
https://descontoss-vip.com

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse_membro=sim

studio_menu:

Texto:

"O que você quer saber sobre a FC VIP?

1 - O que é a FC VIP
2 - Para quem é o estúdio
3 - Ver o site e vídeo tour
9 - Voltar ao menu principal
0 - Encerrar atendimento

Digite apenas o número da opção desejada."

Opções:

1:
"A FC VIP é um espaço de fotografia e produção audiovisual em Volta Redonda.

O estúdio foi criado para facilitar produções de foto e vídeo com estrutura pronta, iluminação completa e ambientes preparados para criação.

Você também pode ver a landing page com o vídeo tour:
https://www.fcvip.com.br

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=conhecer_estudio

2:
"A FC VIP é ideal para fotógrafos, videomakers, criadores de conteúdo, marcas, empresas, profissionais liberais e pessoas que querem produzir fotos ou vídeos com estrutura profissional.

Você também pode ver a landing page com o vídeo tour:
https://www.fcvip.com.br

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=publico_estudio

3:
"Você pode conhecer mais sobre a FC VIP e ver o vídeo tour pela landing page:

https://www.fcvip.com.br

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=site

location_menu:

Ao escolher localização, responder:

"A FC VIP fica na:

Rua Corifeu Marques, 32
Jardim Amália 1
Volta Redonda - RJ

Escolha uma opção:

1 - Fazer agendamento
2 - Conhecer o site e vídeo tour
9 - Voltar ao menu principal
0 - Encerrar atendimento

Digite apenas o número da opção desejada."

Opções:

1:
Se cliente novo:
"Para fazer um novo agendamento na FC VIP, preencha o formulário abaixo:

https://www.fcvip.com.br/formulario

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Se cliente antigo:
"Para fazer seu agendamento pela FC VIP, acesse:

https://www.fcvip.com.br/agendamentos

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=agendamento
origem=localizacao

2:
"Você pode conhecer mais sobre a FC VIP e ver o vídeo tour pela landing page:

https://www.fcvip.com.br

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=localizacao

structure_menu:

Texto:

"Sobre a estrutura da FC VIP, escolha uma opção:

1 - Fundos fotográficos
2 - Iluminação
3 - Tripés e suportes
4 - Cenografia
5 - Infraestrutura
6 - Ver landing page com vídeo tour
9 - Voltar ao menu principal
0 - Encerrar atendimento

Digite apenas o número da opção desejada."

Opções:

1 - Fundos fotográficos:

"A FC VIP conta com fundos fotográficos variados:

- 3 roxos instagramáveis
- 2 brancos de 3x3m
- 2 pretos de 3x3m
- 2 verdes de 3x3m
- 1 roxo padrão
- 1 pano laranja

Você também pode ver a landing page com o vídeo tour:
https://www.fcvip.com.br

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=estrutura
estrutura_interesse=fundos_fotograficos

2 - Iluminação:

"A FC VIP conta com iluminação completa para produções de foto e vídeo:

- 4 softboxes Tomate MLG-065
- 2 bastões de LED GTP
- 2 refletores de 40w
- 2 luzes de vídeo LED Pocket
- 4 luzes ShowTech
- 1 luz circular conceitual laranja
- 1 rebatedor/difusor

Você também pode ver a landing page com o vídeo tour:
https://www.fcvip.com.br

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=estrutura
estrutura_interesse=iluminacao

3 - Tripés e suportes:

"A FC VIP possui tripés e suportes para apoiar diferentes tipos de produção:

- 7 tripés para iluminação
- 4 tripés para fundo fotográfico
- 4 suportes articuláveis para câmera
- 3 tripés padrão para câmera/celular
- 1 suporte articulável para celular

Você também pode ver a landing page com o vídeo tour:
https://www.fcvip.com.br

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=estrutura
estrutura_interesse=tripes_suportes

4 - Cenografia:

"A FC VIP conta com itens de cenografia para compor diferentes estilos de produção:

- 2 banquetas pretas
- bancos baixos preto e branco
- poltronas
- sofá
- mesas de centro de vidro
- tapetes variados brancos, verdes e vermelhos
- vasos
- velas
- luminária
- elefante decorativo

Você também pode ver a landing page com o vídeo tour:
https://www.fcvip.com.br

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=estrutura
estrutura_interesse=cenografia

5 - Infraestrutura:

"A FC VIP também possui infraestrutura de apoio para as produções:

- 2 ar-condicionados
- 3 ventiladores
- filtro de água
- mesa de apoio
- cabideiro
- 10 garras
- fontes para softbox
- filtros de linha
- extensão
- adaptador

Você também pode ver a landing page com o vídeo tour:
https://www.fcvip.com.br

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=estrutura
estrutura_interesse=infraestrutura

6 - Landing page/vídeo tour:

"Você pode conhecer a estrutura da FC VIP e ver o vídeo tour pela landing page:

https://www.fcvip.com.br

9 - Voltar ao menu principal
0 - Encerrar atendimento"

Memória:
interesse=video_tour

human_menu:

Texto:

"Você quer falar com um atendente sobre qual assunto?

1 - Agendamento
2 - Valores
3 - Problema com agendamento
4 - Parceria / profissional audiovisual
5 - Outro assunto
9 - Voltar ao menu principal
0 - Encerrar atendimento

Digite apenas o número da opção desejada."

Opções:

1:
"Certo. Vou registrar que você quer falar com um atendente sobre agendamento.

Um atendente poderá seguir com você assim que possível."

needs_human=true
human_reason=agendamento

2:
"Certo. Vou registrar que você quer falar com um atendente sobre valores.

Um atendente poderá seguir com você assim que possível."

needs_human=true
human_reason=valores

3:
"Certo. Vou registrar que você precisa de ajuda com um agendamento.

Um atendente poderá seguir com você assim que possível."

needs_human=true
human_reason=problema_agendamento

4:
"Certo. Vou registrar seu interesse em parceria ou atuação profissional com a FC VIP.

Um atendente poderá seguir com você assim que possível."

needs_human=true
human_reason=parceria

5:
"Certo. Vou registrar que você quer falar com um atendente sobre outro assunto.

Um atendente poderá seguir com você assim que possível."

needs_human=true
human_reason=outro

Notificação para atendimento humano:

Sempre que needs_human=true:

1. Marcar a conversa como precisando de humano.
2. Registrar human_reason.
3. Criar AuditLog com evento human_requested.
4. Fazer o dashboard exibir essa conversa em uma área de alerta/pendência humana.
5. Se já existir dashboard operacional, adicionar card ou contador para:
   - atendimentos humanos pendentes;
   - motivo;
   - nome/telefone do cliente, se disponível;
   - data/hora da solicitação;
   - última mensagem do cliente.
6. Não encerrar a conversa automaticamente ao pedir humano.

Encerramento:

Se o cliente digitar 0 em qualquer estado:

"Atendimento encerrado.

Se precisar de algo depois, é só mandar uma nova mensagem."

Ações:
- conversation.status=closed
- menu_state=end
- aplicar rotina de limpeza de mensagens se já existir
- não apagar contact_memories
- manter memórias pilares

Memórias pilares:

Manter o modelo de memória pilar.

Salvar apenas informações úteis e duráveis, como:
- cliente_status=novo/antigo
- nome do cliente, se coletado
- telefone, se coletado/confiável
- interesse=agendamento
- interesse=preco
- interesse=estrutura
- interesse=localizacao
- interesse=conhecer_estudio
- pacote_interesse=1h/2h/3h
- interesse_membro=sim
- estrutura_interesse=fundos_fotograficos/iluminacao/tripes_suportes/cenografia/infraestrutura
- human_reason, se pediu humano

Não salvar mensagens genéricas como memória pilar:
- oi
- ok
- obrigado
- talvez
- não sei
- vou ver
- qualquer coisa aviso

Integração com worker:

No app/workers/tasks.py:

- Quando LLM_ENABLED=false, usar MenuBotService.
- Não usar LLMReplyService nessa condição.
- Persistir outbound normalmente.
- Enviar pelo canal atual normalmente.
- Manter follow-up automático existente.
- Manter fallback de canal existente.
- Atualizar o estado da conversa após cada resposta.
- Atualizar dashboard/pendência quando needs_human=true.

Persistência de estado:

Verificar se Conversation já possui campo adequado para estado/metadados.

Preferência:
- se já existir campo JSON/metadados, salvar menu_state nele para evitar migration desnecessária.

Se não existir forma segura, criar migration adicionando:
- menu_state
- needs_human
- human_reason
- last_inbound_message_text
- last_inbound_message_at
- human_requested_at

Cuidados:

1. Não interpretar texto livre.
2. Não criar classificador por palavra-chave.
3. Não reativar LLM.
4. Não mexer no gateway Baileys.
5. Não quebrar deduplicação por external_message_id.
6. Não quebrar dashboard.
7. Não quebrar follow-up.
8. Não quebrar fallback de canal.
9. Não apagar contact_memories.
10. Não apagar contatos reais.
11. Não enviar /formulario para cliente antigo.
12. Corrigir Jardim Amália 2 para Jardim Amália 1 em todos os lugares necessários.
13. Seguir felixo_standards.
14. Usar TDD.

Testes obrigatórios antes da implementação:

Criar testes para validar pelo menos:

1. Chat novo com cliente inexistente inicia coleta de nome antes do menu.
2. Chat novo com cliente antigo responde "Olá, [nome]! Seja bem-vindo(a) de volta" e mostra menu.
3. Cliente antigo escolhendo agendamento recebe /agendamentos.
4. Cliente novo escolhendo agendamento recebe /formulario.
5. Nenhum cliente antigo recebe /formulario no fluxo de agendamento.
6. "oi" em chat novo dispara regra de início correta.
7. main_menu + "1" chama fluxo de agendamento com link conforme tipo de cliente.
8. main_menu + "2" abre pricing_menu.
9. pricing_menu + "1" retorna valor de 1 hora.
10. pricing_menu + "4" retorna todos os valores.
11. main_menu + "4" retorna endereço com Jardim Amália 1.
12. location_menu não possui mais "ver endereço novamente".
13. location_menu possui opção de agendamento.
14. main_menu + "5" abre structure_menu.
15. structure_menu + "1" retorna fundos fotográficos.
16. structure_menu + "2" retorna iluminação completa.
17. structure_menu + "3" retorna tripés e suportes.
18. structure_menu + "4" retorna cenografia.
19. structure_menu + "5" retorna infraestrutura.
20. Todas as respostas de estrutura incluem https://www.fcvip.com.br.
21. human_menu + qualquer motivo válido marca needs_human=true.
22. Solicitação humana aparece/é contada no dashboard.
23. qualquer estado + "9" volta ao menu principal.
24. qualquer estado + "0" encerra atendimento.
25. texto livre tipo "quanto custa?" não é interpretado e pede opção numérica.
26. endereço antigo Jardim Amália 2 não aparece mais nos templates/documentação/base.

Depois dos testes falharem inicialmente, implementar a funcionalidade.

Rodar QA completo ao final:

cmd /c .\.venv\Scripts\python.exe qa_tudo.py --no-dashboard --no-pause

Se houver FAIL, corrigir e rodar novamente até estabilizar.

Atualizar:
- README.md
- ia.md
- humano.md

Relatório final obrigatório:
- arquivos alterados
- testes criados
- novo serviço criado
- como funciona a árvore de menus
- onde o estado é salvo
- como cliente novo/antigo é diferenciado
- como o link /formulario e /agendamentos é decidido
- como a estrutura do estúdio foi separada
- como o dashboard mostra pedidos de humano
- resultado do QA
- riscos restantes -->