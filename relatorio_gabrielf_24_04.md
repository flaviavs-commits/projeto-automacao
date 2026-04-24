# Relatorio Diario - Gabriel F

- Data: 24/04/2026
- Projeto principal: bot-multiredes / intelligent-vitality
- Repositorio: `flaviavs-commits/projeto-automacao`
- Ambientes trabalhados no dia: codigo local, Railway, Meta Developers, Evolution API e validacao em producao

## Resumo Executivo

O dia foi dividido em duas sessoes tecnicas distintas dentro do Codex, alem de uma frente paralela de pesquisa e refinamento para criacao de avatar hiper-realista da chefe usando imagem + video por IA.

As duas sessoes do `bot-multiredes` tiveram naturezas diferentes:

1. Sessao 1:
   reorganizacao estrutural do backend, com foco em reduzir duplicacao, remover componentes sem uso real, centralizar a ingestao de mensagens de webhook e limpar artefatos que nao agregavam valor ao runtime.

2. Sessao 2:
   trabalho de integracao real em producao envolvendo WhatsApp via Evolution API, Railway, Instagram/Meta OAuth, validacao de inbound/outbound, investigacao profunda de assinatura de webhook, envio de DMs Instagram e mapeamento preciso dos bloqueios restantes da Meta.

Em paralelo, houve trabalho relevante fora do backend principal, ligado ao avatar IA da chefe. Essa frente consolidou uma descoberta tecnica importante: em geracao de video a partir de imagens base, a imagem de origem define quase todo o teto de realismo do resultado. O principal gargalo nao esta no prompt do video, e sim na qualidade visual e no grau de naturalidade da imagem usada como base.

Resultado pratico do fechamento do dia:

- o backend ficou mais modular e menos duplicado;
- o fluxo de ingestao inbound foi consolidado;
- a coexistencia Meta + Evolution foi preservada;
- a Evolution API foi provisionada no Railway e conectada ao Redis do projeto;
- a autenticacao e o deploy no Railway foram estabilizados;
- o inbound Instagram foi efetivamente rastreado e corrigido em producao;
- o envio outbound para Instagram foi implementado no codigo e validado ate o ponto de chamada real da Graph API;
- o bloqueio restante do Instagram deixou de ser "falha generica" e passou a ser um erro objetivo de capacidade/permissao da app Meta;
- a frente de avatar IA ficou tecnicamente mais madura, com pipeline mais realista, expectativa corrigida e estrategia de producao mais eficiente.

## Objetivos do Dia

1. Melhorar a estrutura interna do backend, reduzindo duplicacao entre webhooks.
2. Limpar modulos e artefatos sem valor operacional real.
3. Migrar o canal WhatsApp para Evolution API sem remover a infraestrutura Meta necessaria para Instagram/Facebook.
4. Provisionar a Evolution API no Railway usando o Redis ja existente.
5. Validar o comportamento real dos canais em producao, com foco em Instagram DM.
6. Investigar e corrigir as falhas de assinatura do webhook Meta.
7. Implementar o envio outbound de mensagens Instagram no runtime do projeto.
8. Consolidar o aprendizado tecnico sobre criacao de avatar IA da chefe, incluindo limites, gargalos e pipeline recomendado.

## Sessao 1 - Refatoracao Estrutural do Backend

### Escopo

A primeira sessao foi dedicada a auditoria e limpeza da estrutura de dados e ingestao de mensagens, com prioridade para:

- reduzir duplicacao entre `webhooks_meta.py` e `webhooks_evolution.py`;
- centralizar persistencia inbound em um servico unico;
- remover componentes sem consumo real no runtime;
- higienizar o repositorio, removendo lixo operacional e outputs temporarios.

### Diagnostico Encontrado

Antes da refatoracao, os caminhos de entrada dos webhooks Meta e Evolution continham blocos extensos e quase paralelos para:

- extracao de mensagens;
- deduplicacao por `external_message_id`;
- resolucao de identidade do cliente por plataforma;
- abertura ou reuso de conversa;
- persistencia de mensagem inbound;
- montagem do payload para Celery.

Esse desenho trazia tres problemas diretos:

1. custo de manutencao elevado;
2. risco de divergencia entre dois fluxos que deveriam obedecer a mesma semantica;
3. aumento de superficie para regressao em ajustes simples.

Tambem foram encontrados modulos que nao participavam do runtime principal ou nao tinham relevancia operacional suficiente:

- `app/services/media_service.py`;
- `app/services/instagram_service.py` no estado anterior;
- massa de evidencias temporarias em `.qa_tmp/`;
- logs e reports antigos rastreados no repositorio.

### Entregas da Sessao 1

#### 1. Servico compartilhado de ingestao inbound

Foi criado:

- `app/services/webhook_ingestion_service.py`

Responsabilidades centralizadas:

- receber mensagens ja extraidas por plataforma;
- gravar auditoria do evento de webhook;
- deduplicar por `external_message_id`;
- resolver ou criar contato;
- abrir ou reutilizar conversa ativa;
- persistir mensagem inbound;
- devolver payloads padronizados para `process_incoming_message`.

Essa centralizacao reduziu duplicacao e deixou a regra de escrita inbound em um unico ponto de manutencao.

#### 2. Refatoracao dos webhooks

Arquivos trabalhados:

- `app/api/routes/webhooks_meta.py`
- `app/api/routes/webhooks_evolution.py`

Resultado:

- preservacao do contrato de resposta dos endpoints;
- preservacao de idempotencia;
- preservacao do enfileiramento async;
- reducao relevante de logica repetida.

#### 3. Limpeza de servicos e exports

Arquivos e pontos ajustados:

- `app/services/__init__.py`
- `README.md`
- `qa_tudo.py`

Foi removido o que nao agregava ao estado real do runtime e alinhada a documentacao ao que o projeto de fato usa.

#### 4. Higienizacao do repositorio

Foram retirados do controle de versao diversos artefatos temporarios:

- resultados de stress e QA em `.qa_tmp/`;
- `stress_dashboard_report.json`;
- `stress_dashboard_remote_report.json`;
- `uvicorn.err.log`;
- `uvicorn.out.log`.

Blindagem aplicada:

- ajuste em `.gitignore` para impedir reincidencia desse tipo de ruido operacional.

### Validacao da Sessao 1

Validacoes executadas:

- `python -m unittest discover -s tests -p "test_*.py" -v`
- `python -m compileall app qa_tudo.py`

Resultado:

- suite automatizada verde;
- compilacao dos modulos alterados verde;
- estrutura consolidada sem quebra funcional observada.

### Impacto da Sessao 1

Ao final da primeira sessao, o projeto ficou:

- mais modular;
- mais previsivel para evolucao futura;
- mais limpo do ponto de vista de repositorio;
- com menor risco de drift entre canais de entrada.

## Sessao 2 - Integracao Real em Producao, Evolution, Railway e Meta/Instagram

### Escopo

A segunda sessao foi essencialmente operacional e de integracao externa. O trabalho saiu da camada puramente estrutural e entrou na camada de prova real em producao.

As frentes abordadas foram:

- comportamento do bot em conversa real;
- migracao do WhatsApp para Evolution API;
- provisionamento da Evolution no Railway;
- tentativas de conexao via QR/pairing;
- configuracao e validacao de Instagram via Meta OAuth;
- investigacao de webhook Instagram real;
- correcoes no backend para assinatura, classificacao de eventos e dispatch outbound.

### Etapa 1 - Diagnostico inicial do comportamento do bot

O dia comecou com um teste real em producao onde uma mensagem simples de saudacao gerou uma resposta inadequada de encerramento ("Por nada...") em vez de um cumprimento inicial coerente.

Esse ponto evidenciou que:

- havia reutilizacao de contexto ou estado de conversa ja fechada;
- o comportamento do agente dependia do historico salvo;
- a identificacao de "novo cliente" e o reaproveitamento de conversa precisavam ser observados com mais rigor.

Essa investigacao foi importante para contextualizar as demais decisoes do dia: nao bastava o webhook funcionar; era necessario garantir que o ciclo inteiro de atendimento estivesse semanticamente correto.

### Etapa 2 - Migracao arquitetural do WhatsApp para Evolution API

Foi seguida a diretriz de negocio de manter coexistencia obrigatoria com Meta:

- WhatsApp migrado para Evolution;
- Instagram e Facebook mantidos na infraestrutura Meta;
- sem destruir rotas, servicos ou configuracoes ainda necessarias para o ecossistema oficial.

Decisao arquitetural respeitada:

- `webhooks_meta.py` mantido para Instagram/Facebook;
- novo canal WhatsApp conectado via Evolution API;
- fluxo core (`workers`, Celery, LLM) preservado.

### Etapa 3 - Provisionamento da Evolution API no Railway

Atividades realizadas:

- validacao da autenticacao Railway;
- criacao da estrutura local de infra para o servico;
- provisionamento do servico `evolution-api` no Railway;
- configuracao de uso do Redis interno ja existente;
- injecao das variaveis `EVOLUTION_API_BASE_URL`, `EVOLUTION_API_KEY` e `EVOLUTION_INSTANCE_NAME` nos servicos corretos;
- deploy e verificacao de status do backend, worker e Evolution.

Pontos importantes:

- a Evolution foi mantida apenas na rede interna `.railway.internal`;
- nao foi aberto dominio publico desnecessario;
- a configuracao ficou alinhada ao desenho solicitado de infra interna + Redis.

### Etapa 4 - Tentativa de conexao do WhatsApp na Evolution

Foram feitos testes com:

- QR code;
- tentativa de pareamento por numero;
- consulta de estado da instancia.

Bloqueio encontrado:

- o WhatsApp retornou mensagem equivalente a "nao e possivel conectar novos dispositivos no momento".

Leitura tecnica:

- o problema nao estava no backend Python;
- o bloqueio estava no lado do WhatsApp/dispositivo/limite de conexao naquele momento;
- nao havia evidencias de erro estrutural no provisionamento da Evolution em si.

Conclusao desta frente:

- a camada de infra Evolution ficou operante;
- o impedimento ficou concentrado no pareamento do dispositivo, nao na API.

### Etapa 5 - Configuracao e selecao do Instagram correto

Na integracao Meta, houve primeiro conexao com a conta errada e depois revisao dos ativos disponiveis.

Foi feita selecao consciente do Instagram correto:

- conta escolhida: `fc_vip_`
- `instagram_business_account_id`: `17841440950793819`

Essa etapa foi importante porque o retorno do OAuth mostrou mais de uma conta Instagram disponivel, e o backend precisou ser validado contra o ativo certo, nao apenas contra o primeiro ativo retornado.

### Etapa 6 - Meta app live, testers e requisitos de producao

Durante a validacao do Instagram, tambem entraram em jogo exigencias operacionais da Meta:

- app em modo development nao entrega producao normal;
- necessidade de `Privacy Policy URL` valida para ativacao;
- revisao de tester roles;
- confirmacao de credenciais e secrets no Railway.

Essa parte nao foi mero detalhe burocratico. Ela influenciou diretamente o fato de eventos reais chegarem ou nao ao webhook.

### Etapa 7 - Investigacao profunda de assinatura do webhook Meta

Esse foi um dos blocos mais importantes da segunda sessao.

Problema observado:

- DMs reais do Instagram chegavam ao endpoint com `User-Agent` real da Meta (`facebookexternalua`), mas eram rejeitadas por `401 Invalid Meta signature`.

Trabalho realizado no codigo:

- reforco da verificacao em `app/core/security.py`;
- suporte a `sha256` e `sha1`;
- parse mais robusto de digest;
- tolerancia a formatos de payload com escapes diferentes;
- suporte a secret atual + secret anterior;
- log enriquecido com hashes, prefixos de assinatura, `object`, `entry_id` e `user_agent_prefix`.

Arquivos principais:

- `app/core/security.py`
- `app/api/routes/webhooks_meta.py`
- `tests/test_security.py`
- `app/core/config.py`

Tambem foi introduzido:

- `META_APP_SECRET_PREVIOUS`

Objetivo:

- cobrir o cenario de rotacao de segredo sem derrubar a recepcao de eventos.

### Etapa 8 - Validacao sintetica com assinatura realista

Nao foi feita validacao mascarada. Foram disparados eventos sinteticos com:

- segredo atual;
- segredo anterior;
- segredo invalido.

Resultados:

- segredo atual: aceito;
- segredo anterior: aceito;
- segredo invalido: rejeitado corretamente.

Essa bateria foi decisiva para provar que o backend conseguia validar assinatura dentro dos cenarios previstos.

### Etapa 9 - Implementacao de envio outbound para Instagram

Foi identificado um gap objetivo de implementacao:

- o sistema persistia resposta outbound para Instagram no banco;
- porem nao havia dispatch real para o endpoint de mensagens da Graph API.

Correcoes implementadas:

- recriacao e evolucao de `app/services/instagram_service.py`;
- integracao do `generate_reply` em `app/workers/tasks.py` para chamar `InstagramService().send_text_message(...)` quando a plataforma e `instagram`;
- novos testes unitarios para o servico.

Arquivos principais:

- `app/services/instagram_service.py`
- `app/workers/tasks.py`
- `tests/test_instagram_service.py`

### Etapa 10 - Correcao de credenciais no worker

Outro problema real encontrado:

- `worker` nao tinha todas as variaveis necessarias para decifrar e usar corretamente o token OAuth persistido.

Variaveis alinhadas:

- `TOKEN_ENCRYPTION_SECRET`
- `META_APP_ID`
- `META_OAUTH_REDIRECT_URI`
- `OAUTH_STATE_SECRET`

Impacto:

- o worker deixou de cair para token incorreto/invalidado;
- passou a usar o conjunto de credenciais de forma mais consistente com a API.

### Etapa 11 - Resolucao de Page Access Token para Instagram DM

Foi identificado que o envio de DM Instagram nao podia usar qualquer token de forma simplista. Para o endpoint de mensagens, a chamada precisava ser resolvida a partir do contexto da pagina/ativo correto.

Ajuste implementado:

- lookup de `me/accounts`;
- resolucao do `Page Access Token` correspondente ao `instagram_business_account_id`;
- uso desse token na chamada `/{ig_id}/messages`.

Resultado da validacao:

- o codigo avancou da falha de token invalido para a falha de capacidade da app;
- ou seja, a camada de runtime passou a chamar o endpoint correto com autenticacao melhor resolvida.

### Etapa 12 - Fallback controlado para inbound Instagram sem assinatura valida

Como as DMs reais continuavam chegando com comportamento inconsistente de assinatura, foi implementado um fallback controlado por flag para destravar operacao de inbound enquanto a causa raiz externa nao e completamente eliminada.

Foi adicionado:

- `META_ALLOW_UNSIGNED_INSTAGRAM`

Comportamento:

- quando ativo, permite bypass apenas para eventos `object=instagram` com cabecalho presente;
- o bypass fica auditado e logado;
- nao abre o sistema inteiro para qualquer webhook.

Esse ponto foi uma decisao pragmatica de operacao: melhor capturar a DM real com trilha de auditoria do que perder atendimento enquanto a Meta mantem comportamento inconsistente.

### Etapa 13 - Correcao de classificacao errada entre Facebook e Instagram

Um bug importante apareceu na validacao de `real-03`:

- a DM entrou;
- foi persistida;
- mas foi classificada como `facebook` porque o payload real veio sem `messaging_product`.

Correcao aplicada:

- quando `object=instagram` e `messaging_product` vier ausente, o sistema passa a classificar o evento como `instagram`;
- foi criado teste especifico para garantir esse comportamento.

Arquivos:

- `app/api/routes/webhooks_meta.py`
- `tests/test_webhooks_meta.py`

### Validacao objetiva da Sessao 2

Ao longo da sessao foram executados:

- deploys do `projeto-automacao`;
- deploys do `worker`;
- validacoes de status via Railway;
- consultas a `logs`;
- consultas a `/messages`;
- consultas a `/health/meta-live`, `/health/meta-live/inbound` e `/health/meta-live/outbound`;
- testes sinteticos assinados e nao assinados;
- verificacoes do comportamento real do worker.

Suites e testes executados em momentos diferentes:

- `python -m unittest tests.test_security -v`
- `python -m unittest tests.test_security tests.test_oauth_meta_asset_selection tests.test_meta_oauth_service tests.test_webhooks_evolution -v`
- `python -m unittest tests.test_instagram_service tests.test_whatsapp_service tests.test_security -v`
- `python -m unittest tests.test_webhooks_meta tests.test_security tests.test_instagram_service -v`
- `python -m unittest tests.test_webhooks_evolution tests.test_meta_oauth_service tests.test_oauth_meta_asset_selection tests.test_customer_identity_service -v`

Todos esses blocos fecharam verdes nas rodadas executadas.

### Estado tecnico no fechamento da Sessao 2

#### O que ficou resolvido

- provisionamento e deploy da Evolution no Railway;
- coexistencia Meta + Evolution;
- fluxo de ingestao consolidado;
- correcoes de assinatura e observabilidade do webhook;
- suporte a secret atual + anterior;
- classificacao correta de eventos `object=instagram` sem `messaging_product`;
- implementacao de dispatch outbound para Instagram no codigo;
- alinhamento de variaveis criticas do worker;
- capacidade de rastrear com precisao onde o fluxo quebra.

#### O que ficou objetivamente provado

1. O inbound Instagram agora consegue entrar no backend e ser persistido.
2. O worker processa a mensagem e tenta efetivamente chamar a Graph API.
3. O bloqueio restante do outbound Instagram nao e mais um "erro nebuloso do sistema".
4. O erro atual e especifico e rastreavel:
   `OAuthException code 3 - Application does not have the capability to make this API call`.

#### Leitura tecnica do bloqueio atual

Isso significa que o principal impeditivo restante do Instagram e externo ao core do backend:

- capability/permissao da app Meta;
- possivel escopo liberado mas sem capacidade habilitada para a operacao especifica;
- possivel restricao de produto/painel/app mode mesmo com token valido.

Em outras palavras:

- o backend ja avancou ate o ponto certo;
- a lacuna remanescente esta na configuracao/capacidade da app Meta.

### Arquivos principais tocados na segunda sessao

- `app/api/routes/webhooks_meta.py`
- `app/core/config.py`
- `app/core/security.py`
- `app/services/instagram_service.py`
- `app/workers/tasks.py`
- `app/services/__init__.py`
- `tests/test_security.py`
- `tests/test_instagram_service.py`
- `tests/test_webhooks_meta.py`

## Frente Paralela - Avatar IA da Chefe (Nano Banana + Higgs)

### Objetivo da frente

Construir um avatar hiper-realista da chefe para uso em conteudo educacional e institucional, com foco em:

- introducoes de cursos com 3 a 5 minutos;
- substituicao parcial da presenca dela em video;
- fidelidade alta de identidade visual;
- possibilidade de pequenas variacoes de roupa e cenario sem descaracterizar a pessoa.

### Conclusao central

O projeto e tecnicamente viavel, mas o realismo confiavel nao deve ser tratado como "perfeito". O intervalo mais honesto hoje fica entre 80% e 90%, dependendo da qualidade da imagem base, do tipo de take e da tolerancia do observador.

O principal aprendizado do trabalho ate aqui foi o seguinte:

- tentar corrigir no video aquilo que nasceu errado na imagem e um caminho caro e ineficiente;
- a imagem base define o teto de qualidade do movimento, do olhar e da naturalidade final;
- o modelo de video amplifica tanto as qualidades quanto os defeitos da imagem de origem.

### Erro estrategico inicial

O fluxo inicial seguiu um caminho comum, mas tecnicamente inadequado:

1. gerar uma imagem muito idealizada;
2. animar essa imagem;
3. tentar compensar os defeitos do resultado apenas com prompt.

Esse caminho falhou porque:

- a imagem "perfeita demais" gerava rigidez facial;
- o olhar excessivamente centralizado criava estranheza;
- o excesso de suavizacao eliminava vida na pele;
- o video apenas herdava e amplificava esses problemas.

O caminho correto, consolidado agora, e:

1. preservar identidade real;
2. aceitar pequenas imperfeicoes naturais;
3. ajustar somente o necessario na imagem base;
4. animar a partir dessa base mais humana e menos plastica.

### Dificuldades principais, em ordem da mais dificil para a menos dificil

#### 1. Geracao de video a partir de um banco de imagens do Nano Banana

Esse e o ponto mais dificil da frente inteira.

Problema real:

- nao basta ter varias imagens boas isoladamente;
- e preciso ter consistencia de identidade, iluminacao, textura e geometria entre as imagens;
- quando a base e heterogenea, o modelo de video nao entende uma pessoa estavel, mas varias interpretacoes diferentes da mesma pessoa.

Consequencias praticas:

- os videos variam demais entre takes;
- a face oscila em detalhes sutis;
- a expressao muda de um jeito pouco organico;
- elementos como olhos, boca, mandibula e cabelo perdem continuidade.

Leitura tecnica:

- banco de imagens serve como materia-prima, nao como garantia de consistencia;
- sem uma imagem base definitiva e padronizada, o pipeline vira retrabalho.

#### 2. Olhos

Os olhos se mostraram o ponto mais sensivel de realismo.

Problemas observados:

- olhar fixo demais;
- ausencia de micro movimentacao ocular;
- piscadas artificiais;
- reflexos agressivos por causa dos oculos;
- direcao de olhar "travada" e excessivamente perfeita.

Causas identificadas:

- imagem base centralizada demais;
- lentes com brilho forte;
- tentativa de controle excessivo por prompt;
- excesso de limpeza/beleza na face original.

Conclusao:

- se os olhos nascem artificiais na base, o video quase nunca corrige isso sozinho;
- o video pode esconder um pouco, mas nao resolver de fato.

#### 3. Face com aspecto artificial

Problemas:

- pele lisa demais;
- textura sem vida;
- pouca deformacao facial em fala e micro expressao;
- expressao "congelada".

Causa:

- a imagem base estava mais proxima de um retrato idealizado do que de um frame humano crivel;
- o modelo suaviza ainda mais o que ja esta suavizado.

Licao:

- realismo nao vem de perfeicao;
- realismo vem de assimetria controlada, textura, volume organico e micro imperfeicao.

#### 4. Corpo pouco natural

Problemas:

- cabeca movimenta e o resto do corpo quase nao acompanha;
- ombros e bracos parecem contidos;
- cabelo reage pouco;
- linguagem corporal global fica abaixo do nivel da face.

Causa:

- limitacao natural do Higgs/Kling no tipo de animacao pretendida;
- expectativa inicial acima do que a ferramenta entrega bem hoje.

Leitura tecnica:

- a ferramenta funciona melhor em enquadramento de busto, camera estatica e movimento minimo;
- quanto mais se exige fisica corporal completa, mais rapido o resultado perde credibilidade.

#### 5. Artefatos e elementos inesperados

Problemas:

- textos aleatorios;
- pequenos elementos estranhos na cena;
- detalhes surgindo sem pedido explicito.

Causas:

- falta de restricoes claras no prompt;
- comportamento inerente do modelo em areas ambiguanas da cena.

#### 6. Expressao inconsistente

Problemas:

- sorriso exagerado ou persistente;
- ou, no extremo oposto, comportamento rigido e frio demais.

Causas:

- prompts desequilibrados;
- tentativa de dirigir o modelo por extremos;
- falta de referencia intermediaria entre simpatia e sobriedade.

### Mudanca de estrategia consolidada

O direcionamento atualizado passou a evitar:

- pele plastificada;
- simetria excessiva;
- olhar totalmente frontal;
- estica "perfeita";
- direcao facial travada.

Passou a priorizar:

- textura real de pele;
- presenca de micro imperfeicoes;
- direcao de olhar levemente fora do centro;
- expressao neutra e relaxada;
- iluminacao suave e previsivel.

### Pipeline tecnico recomendado

#### 1. Nano Banana

Uso recomendado:

- nao recriar a pessoa do zero;
- usar a ferramenta para ajuste controlado da imagem base.

Ajustes ideais nessa fase:

- reduzir reflexo do oculos;
- corrigir discretamente a direcao do olhar;
- recuperar textura de pele;
- preservar a identidade real.

#### 2. Higgs / Kling Avatars 2.0

Uso recomendado:

- trabalhar com imagem base ja consolidada;
- gerar takes curtos de 5 a 10 segundos;
- evitar depender de um unico take longo.

#### 3. Audio

Ferramenta sugerida:

- ElevenLabs

Premissas:

- ritmo natural;
- pausas reais;
- sem locucao excessivamente polida;
- sem entonacao radiofonica artificial.

#### 4. Edicao

Estrutura recomendada:

- juntar varios takes curtos;
- fazer cortes em pontos de respiracao;
- evitar video unico e continuo muito longo.

Essa decisao reduz:

- acumulacao de artefatos;
- degradacao de naturalidade ao longo da fala;
- risco de um erro inutilizar todo o take.

### Configuracao visual ideal da imagem base

A imagem base definitiva deve ter:

- oculos com reflexo minimo;
- olhos visiveis e legiveis;
- olhar levemente fora da lente;
- palpebras relaxadas;
- textura de pele real;
- expressao neutra;
- ausencia de rigidez facial;
- iluminacao suave e limpa;
- enquadramento de busto;
- composicao horizontal coerente com o uso final.

### Evolucao observada dos prompts

#### Fase 1

- controle excessivo;
- resultado robotico;
- face muito dirigida e pouco viva.

#### Fase 2

- suavizacao excessiva;
- resultado plastico/artificial;
- perda de identidade.

#### Fase 3

- equilibrio melhor entre controle e naturalidade;
- menos obsessao por perfeicao;
- foco maior em preservar humanidade.

### Descoberta principal da frente

O problema dos olhos nao e um problema "de video". E um problema de base visual.

Se a imagem inicial tiver:

- reflexo forte;
- simetria dura;
- olhar travado;

o video continuara artificial, mesmo com prompt bom.

### Limitacoes reais do Higgs

Nao e razoavel esperar:

- corpo totalmente natural;
- cabelo fisicamente convincente o tempo inteiro;
- maos perfeitas;
- lip sync impecavel em takes longos.

E razoavel esperar:

- bom movimento de cabeca;
- expressao facial aceitavel;
- consistencia geral de rosto;
- resultado forte em enquadramento controlado.

### Decisoes ja consolidadas

- uso obrigatorio de oculos;
- roupa padrao;
- fundo de escritorio;
- enquadramento em busto;
- estilo calmo, didatico e institucional;
- formato horizontal.

### Estimativa de producao

- setup inicial da base: 1 a 2 dias;
- producao por video: 1 a 2 horas;
- conjunto de 20 aulas: aproximadamente 20 a 40 horas.

### Status atual da frente de avatar

O projeto nao esta parado nem travado conceitualmente. Ele esta em fase de refinamento fino.

Os problemas restantes concentram-se principalmente em:

- consolidacao de uma imagem base definitiva;
- refinamento de olhos, reflexo e textura;
- equilibrio fino entre naturalidade e controle.

### Proximo passo recomendado

Produzir uma imagem base final unica, com:

- menos reflexo no oculos;
- olhar corrigido;
- pele com textura natural;
- expressao neutra e relaxada.

Essa etapa deve resolver grande parte dos problemas acumulados e aumentar a taxa de acerto dos videos seguintes.

## Arquivos e Entregas Tecnicas Mais Relevantes do Dia

### Backend e integracao

- `app/services/webhook_ingestion_service.py`
- `app/api/routes/webhooks_meta.py`
- `app/api/routes/webhooks_evolution.py`
- `app/core/security.py`
- `app/core/config.py`
- `app/services/instagram_service.py`
- `app/workers/tasks.py`
- `app/services/__init__.py`
- `qa_tudo.py`
- `README.md`
- `.gitignore`

### Testes

- `tests/test_security.py`
- `tests/test_instagram_service.py`
- `tests/test_webhooks_meta.py`
- `tests/test_webhooks_evolution.py`
- `tests/test_customer_identity_service.py`
- `tests/test_meta_oauth_service.py`
- `tests/test_oauth_meta_asset_selection.py`

### Infra / operacao

- deploys e validacoes no Railway para:
  - `projeto-automacao`
  - `worker`
  - `evolution-api`
- configuracao de variaveis em servicos de runtime;
- verificacoes de status, logs e health endpoints;
- testes operacionais contra a URL de producao.

## Riscos Abertos no Fechamento do Dia

1. O inbound Instagram foi destravado com fallback controlado para assinatura, mas a causa externa exata da inconsistência de assinatura da Meta ainda merece monitoramento continuo.
2. O outbound Instagram ainda depende de capability/permissao da app Meta para a chamada de envio real.
3. O pareamento do WhatsApp na Evolution depende de desbloqueio/comportamento do lado do WhatsApp e do dispositivo, nao apenas do backend.
4. O avatar IA continua dependente da construcao de uma imagem base definitiva; sem isso, o teto de qualidade do video nao sobe de forma consistente.

## Conclusao Final do Dia

O dia gerou avancos reais em duas frentes diferentes, mas complementares.

No `bot-multiredes`, houve amadurecimento estrutural e operacional. A primeira sessao deixou o backend mais limpo e modular. A segunda foi mais dura e mais importante do ponto de vista de negocio: ela empurrou o sistema ate o limite real da integracao, separando o que era problema interno do que e problema de capacidade/permissao externa da Meta. Esse e o principal ganho do dia: o sistema parou de falhar de forma ambigua e passou a expor com precisao o ponto exato de bloqueio.

Na frente do avatar IA da chefe, a principal conquista nao foi "terminar o avatar", e sim corrigir o metodo. O trabalho saiu da tentativa de compensar tudo por prompt e passou para um pipeline tecnicamente mais maduro, onde a imagem base vira o centro da qualidade. Isso reduz retrabalho, melhora previsibilidade e aumenta a chance de produzir videos mais criveis com menos desperdicio de tempo.

Em termos de maturidade tecnica, o saldo do dia foi forte:

- melhor arquitetura;
- melhor observabilidade;
- melhor prova de producao;
- melhor entendimento do gargalo real;
- melhor estrategia para a frente de video/avatar.
