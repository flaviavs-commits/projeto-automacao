# Relatorio Diario - Gabriel F

- Data: 20/04/2026
- Projeto: intelligent-vitality (Railway)
- Repositorio: flaviavs-commits/projeto-automacao

## Resumo Executivo

O dia foi concentrado em deixar o atendimento LLM mais leve, mais previsivel e mais seguro para rodar online no Railway, sem depender da maquina local para inferencia. A frente principal foi a melhoria do modelo e das regras de atendimento para locacao de estudio, seguida por baterias extensas de testes guiados pelos erros mais frequentes.

Tambem foram consideradas atividades executadas fora do VS Code, relacionadas a producao criativa com IA:
- estudo detalhado sobre criacao de videos a partir do Higgsfield;
- criacao das imagens/modelos da chefe;
- geracao de audio.

Resultado pratico do fechamento:
- LLM em Railway foi refatorado para operar de forma mais leve;
- API, worker e runtime LLM foram redeployados/reiniciados em producao;
- foram executadas baterias online de 100 e 300 testes;
- foi gerado relatorio especifico de perguntas e respostas separado entre acertos e erros;
- foram mapeados os temas que mais precisam de conhecimento definido ou regra geral;
- as frentes externas de video, imagem/modelo e audio foram incorporadas ao planejamento do projeto como modulo futuro de producao de conteudo.

## Objetivos do Dia

1. Refatorar o LLM local e no Railway para reduzir peso, contexto e custo de processamento.
2. Corrigir falhas frequentes observadas na avaliacao manual do atendimento.
3. Executar uma bateria online guiada pelos erros mais recorrentes.
4. Expandir a avaliacao para 300 perguntas, com 3 perguntas por tema solicitado.
5. Gerar relatorio em Markdown contendo somente perguntas e respostas, separadas em acertos e erros.
6. Registrar no mesmo relatorio diario as atividades externas de Higgsfield, imagens/modelos e audio.

## Frente 1 - Otimizacao do LLM

Foram ajustadas configuracoes e regras para manter o modelo leve e reduzir dependencia de respostas longas ou inventadas pelo LLM.

Arquivos principais trabalhados:
- `app/services/llm_reply_service.py`
- `app/core/config.py`
- `infra/llm-runtime/start.sh`
- `.env`
- `.env.example`
- `README.md`

Principais melhorias:
- cache e selecao parcial da base de conhecimento;
- limite de contexto, memorias e tamanho do prompt;
- configuracoes para modelo leve `qwen2.5:0.5b-instruct`;
- fallback controlado para modelo mais forte quando necessario;
- reducao de risco de resposta fora de dominio;
- regras deterministicas para temas que nao devem depender do modelo.

Configuracao recomendada para o runtime LLM:
- `LLM_MODEL=qwen2.5:0.5b-instruct`
- `LLM_MODELS_TO_PULL=qwen2.5:0.5b-instruct,qwen2.5:1.5b-instruct`
- `LLM_PULL_POLICY=if_missing`
- `OLLAMA_NUM_PARALLEL=1`
- `OLLAMA_MAX_LOADED_MODELS=1`
- `OLLAMA_KEEP_ALIVE=8m`

## Frente 2 - Correcoes de Atendimento

Foram corrigidos casos criticos observados na conversa manual:

1. Pedido de horario fora do funcionamento:
- problema observado: o bot respondeu como se estivesse encerrando a conversa.
- ajuste: quando o cliente pede horario fora da operacao, o atendimento deve informar que o horario nao e atendido e direcionar para o fluxo correto de agenda.

2. Coleta de informacoes do cliente:
- problema observado: o bot nao estava recolhendo informacoes suficientes.
- ajuste: memoria de contato foi reforcada para capturar nome, telefone, Instagram, perfil do cliente, intencao, horario e contexto relevante.

3. Mensagem "fui ai na sexta":
- problema observado: o bot interpretou como "mandei mensagem na sexta".
- ajuste: criada regra de feedback de visita, reconhecendo que o cliente esteve no estudio e pedindo avaliacao/relato da experiencia.

4. Perguntas pessoais ou fora de dominio:
- problema observado: respostas muito genericas, como se fosse assistente pessoal.
- ajuste: redirecionamento para o contexto FC VIP/estudio sem expor comportamento artificial demais.

5. Ofensas e mensagens agressivas:
- problema observado: respostas longas e pouco comerciais.
- ajuste: resposta curta, profissional e redirecionada ao atendimento.

6. Spam de mensagens:
- problema observado: o sistema tentava processar todas as mensagens repetidas.
- ajuste: criado controle no worker para detectar rajadas, preservar processamento e responder com base na ultima mensagem do agrupamento.

Arquivos principais:
- `app/services/llm_reply_service.py`
- `app/services/contact_memory_service.py`
- `app/workers/tasks.py`

## Frente 3 - Memoria e Identidade do Cliente

O servico de memoria foi ampliado para capturar informacoes comerciais uteis, reduzindo repeticao de perguntas e melhorando continuidade de conversa.

Campos reforcados:
- nome;
- telefone;
- Instagram do cliente;
- perfil do cliente, como fotografo, videomaker, modelo ou locacao;
- horario citado;
- intencao de agendamento;
- contexto de visita/experiencia.

Arquivo:
- `app/services/contact_memory_service.py`

## Frente 4 - Testes Online no Railway

Os testes foram feitos contra producao Railway, sem depender da maquina local para rodar o modelo.

Comando usado para chat online:

```cmd
.venv\Scripts\python.exe -u road_test\chat_railway_prod.py --base-url https://projeto-automacao-production.up.railway.app --app-secret 4e4fafdc1bdbb72df058b0d94111e0cb
```

Comandos usados para redeploy/restart:

```cmd
railway.cmd redeploy -s llm-runtime -y
railway.cmd redeploy -s projeto-automacao -y
```

Dashboard:

```cmd
start "" "https://projeto-automacao-production.up.railway.app/dashboard"
```

Observacao importante:
- houve erro `invalid_meta_signature` quando o app secret foi digitado sem o `b` final;
- o comando correto usa `4e4fafdc1bdbb72df058b0d94111e0cb`.

## Frente 5 - Bateria de 100 Testes Guiados por Erros

Script criado:
- `road_test/stress_locacao_error_guided_online.py`

Relatorios gerados:
- `.qa_tmp/stress_locacao_error_guided_100_20260420_121725.json`
- `.qa_tmp/stress_locacao_error_guided_100_20260420_121725.md`

Resultado final:
- total: 100
- acertos: 91
- erros: 9

Principais pontos de erro:
- contexto de localizacao;
- politica de audio;
- respostas que ainda exigiam melhor regra geral para evitar invencao.

Leitura tecnica:
- a taxa geral ficou boa para modelo leve;
- os erros restantes indicam lacunas de conhecimento ou necessidade de fallback seguro;
- a estrategia correta e preferir regras generalistas e redirecionamento para fonte oficial, sem aumentar demais o peso do prompt.

## Frente 6 - Bateria de 300 Perguntas por Tema

Script criado:
- `road_test/theme_coverage_300_online.py`

Relatorios gerados:
- `.qa_tmp/theme_coverage_300_20260420_140007.json`
- `.qa_tmp/theme_coverage_300_20260420_140007.md`
- `.qa_tmp/theme_coverage_300_qna_only_20260420_140007.md`

Resultado:
- total: 300
- acertos: 266
- sem resposta definida: 30
- erros do modelo: 4

O relatorio solicitado com somente perguntas e respostas foi gerado em:
- `.qa_tmp/theme_coverage_300_qna_only_20260420_140007.md`

Esse arquivo foi separado apenas em:
- Acertos
- Erros

## Temas com Maior Taxa de Erro

Os temas com maior taxa de erro ou ausencia de resposta definida foram:

1. Tarifas para feriados:
- 3 erros em 3 perguntas.
- classificacao: falta de regra comercial definida.

2. Descontos para recorrentes:
- 2 erros em 3 perguntas.
- classificacao: falta de politica comercial definida.

3. Taxas extras:
- 2 erros em 3 perguntas.
- classificacao: falta de regra objetiva para hora extra, limpeza e adicionais.

4. Capacidade de pessoas:
- 2 erros em 3 perguntas.
- classificacao: conflito ou ambiguidade de informacao.

5. Tempo de montagem:
- 2 erros em 3 perguntas.
- classificacao: falta de regra operacional clara.

6. Tempo de desmontagem:
- 2 erros em 3 perguntas.
- classificacao: falta de regra operacional clara.

Outros temas com erro pontual:
- tempo minimo de locacao;
- parcerias com fotografos;
- tarifas para finais de semana;
- formas de pagamento;
- faturamento para empresas;
- parcelamento;
- caucao/deposito de seguranca;
- prazo para cancelamento sem multa;
- multa por cancelamento;
- mudanca de duracao;
- tamanho do estudio;
- luz natural versus artificial;
- energia eletrica disponivel;
- tipos de flashes.

## Erros que Parecem Falta de Informacao Definida

Foram classificados como lacunas de conhecimento ou politica nao definida:
- tarifas para feriados;
- descontos para recorrentes;
- taxas extras;
- prazo e multa de cancelamento;
- regras de parcelamento;
- caucao/deposito;
- faturamento para empresas;
- regras de montagem e desmontagem;
- capacidade exata de pessoas;
- equipamentos extras pagos;
- troca de fundos;
- assistente tecnico disponivel.

Recomendacao:
- criar uma tabela simples de politica comercial e operacional;
- quando nao houver regra definida, o bot deve responder que a confirmacao depende da equipe e direcionar para atendimento humano ou site;
- evitar que o LLM invente numeros, prazos, descontos ou taxas.

## Erros Atribuidos ao Modelo

Foram observados 4 erros mais claramente atribuiveis ao modelo, com sinais de alucinacao ou saida fora de dominio:
- caucao/deposito de seguranca;
- tripes e suportes;
- assistente tecnico disponivel;
- ensaios fotograficos.

Padrao observado:
- o modelo tentou explicar conceitos gerais em vez de responder como FC VIP;
- em alguns casos, trouxe termos irrelevantes como hotel, escola, estudante ou conceitos genericos;
- isso reforca a necessidade de regra generalista: se o tema nao estiver definido, assumir desconhecimento operacional e direcionar para confirmacao oficial.

## Solucoes Generalistas Recomendadas

1. Regra de desconhecimento controlado:
- se a informacao nao estiver na base, responder que nao ha confirmacao por ali e direcionar para site/equipe.

2. Regra de valores e tarifas:
- nunca inventar preco, desconto, feriado, taxa extra ou reajuste.
- sempre direcionar para `https://www.fcvip.com.br/formulario` ou atendimento humano.

3. Regra de disponibilidade:
- nao prometer horario manualmente.
- orientar consulta no site.

4. Regra de capacidade:
- se exceder limite conhecido, encaminhar para avaliacao humana.
- se houver duvida, pedir confirmacao oficial antes de aceitar.

5. Regra de operacao:
- montagem, desmontagem, atraso, limpeza e hora extra devem seguir politica definida.
- enquanto nao houver politica final, responder como item sujeito a confirmacao.

6. Regra anti-alucinacao:
- bloquear respostas com termos claramente fora do negocio, como hotel, escola, companhia aerea, turismo, aluguel residencial ou conceitos bancarios.

## Frente 7 - Producao Criativa com IA

Tambem foram registradas atividades fora do VS Code que impactam a evolucao do projeto:

1. Higgsfield:
- estudo detalhado sobre criacao de videos;
- avaliacao de fluxo para transformar briefing/imagem/modelo em video final;
- potencial uso para conteudo de redes sociais e campanhas.

2. Imagens/modelos da chefe:
- criacao de imagens base para manter consistencia visual;
- possivel uso como referencia para campanhas, posts, videos e assets de marca.

3. Geracao de audio:
- estudo/pratica de geracao de audio para complementar videos;
- possibilidade de criar narracoes, chamadas comerciais e conteudo curto para redes.

Leitura tecnica:
- essa frente deve ficar separada do atendimento LLM;
- o atendimento comercial continua sendo uma frente;
- a producao criativa deve virar um modulo proprio de pipeline de conteudo.

Pipeline futuro sugerido:
- briefing;
- imagem/modelo;
- roteiro;
- voz/audio;
- geracao de video;
- revisao humana;
- exportacao;
- agendamento/publicacao.

## Railway e Operacao

Servicos envolvidos:
- `projeto-automacao` (API e dashboard)
- `worker` (Celery)
- `llm-runtime` (Ollama)
- Postgres
- Redis

Deploys/redeploys relevantes do dia:
- `llm-runtime` redeployado;
- `projeto-automacao` redeployado;
- worker havia sido atualizado em rodada anterior do dia para anti-spam e fluxo de mensagens.

Status operacional esperado:
- LLM roda online no Railway;
- dashboard abre em `https://projeto-automacao-production.up.railway.app/dashboard`;
- chat de teste online usa o pipeline real da API/worker/LLM.

## Arquivos Criados ou Alterados

Arquivos alterados:
- `.env`
- `.env.example`
- `README.md`
- `app/core/config.py`
- `app/services/contact_memory_service.py`
- `app/services/llm_reply_service.py`
- `app/workers/tasks.py`
- `infra/llm-runtime/start.sh`
- `tests/test_contact_memory_service.py`
- `tests/test_llm_reply_service.py`

Arquivos criados:
- `road_test/stress_locacao_error_guided_online.py`
- `road_test/theme_coverage_300_online.py`
- `.qa_tmp/stress_locacao_error_guided_100_20260420_121725.json`
- `.qa_tmp/stress_locacao_error_guided_100_20260420_121725.md`
- `.qa_tmp/theme_coverage_300_20260420_140007.json`
- `.qa_tmp/theme_coverage_300_20260420_140007.md`
- `.qa_tmp/theme_coverage_300_qna_only_20260420_140007.md`
- `relatorio_gabrielf_20_04.md`

## Riscos Abertos

1. O modelo leve ainda pode alucinar quando uma pergunta nao tem resposta definida.
2. Politicas comerciais incompletas podem gerar respostas inconsistentes.
3. Controle anti-spam precisa ser revalidado em producao apos redeploy.
4. Se o app secret for digitado errado, o chat de producao falha com `invalid_meta_signature`.
5. A frente de producao criativa ainda nao esta integrada ao dashboard nem ao fluxo de posts.

## Proximos Passos Recomendados

1. Revalidar anti-spam em producao com rajada controlada de mensagens.
2. Criar uma tabela objetiva de politicas comerciais pendentes.
3. Adicionar regras generalistas para feriados, descontos, taxas extras e cancelamento.
4. Revisar capacidade real do estudio e registrar a regra oficial.
5. Transformar a frente Higgsfield/imagem/audio em um modulo separado de producao de conteudo.
6. Reexecutar a bateria de 300 perguntas depois das politicas pendentes serem definidas.

## Conclusao do Dia

O dia avancou duas frentes importantes do projeto: a frente operacional de atendimento com LLM e a frente criativa de conteudo com IA.

No atendimento, o sistema ficou mais leve, mais controlado e mais adequado para rodar em producao no Railway. A bateria de 300 perguntas mostrou que a maior parte das falhas nao vem apenas do modelo, mas da ausencia de politicas definidas para alguns temas comerciais e operacionais.

Na producao criativa, o estudo com Higgsfield, imagens/modelos e audio abriu uma segunda trilha de produto: transformar o sistema em uma base nao so de atendimento, mas tambem de criacao e publicacao de conteudo.
