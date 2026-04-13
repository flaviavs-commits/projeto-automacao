# Relatorio Diario - Gabriel F

- Data: 13/04/2026
- Projeto: intelligent-vitality (Railway)
- Repositorio: flaviavs-commits/projeto-automacao

## Resumo Executivo

Hoje o foco foi colocar o LLM para rodar de forma estavel sem depender da maquina local.  
Foi criado um servico dedicado `llm-runtime` no Railway, integrado com API e worker por rede interna.  
Tambem foram aplicadas referencias entre servicos, tuning de performance e correcoes de compatibilidade no banco para eliminar erro 500 no webhook.

## O que foi entregue

1. Servico LLM dedicado no Railway
- servico criado: `llm-runtime`;
- deploy isolado com:
  - `infra/llm-runtime/Dockerfile`
  - `infra/llm-runtime/start.sh`;
- volume persistente anexado em `/root/.ollama`.

2. Integracao da API e do worker com o runtime interno
- `LLM_BASE_URL` apontado para dominio interno do `llm-runtime`;
- fluxo validado com chamada real:
  - `POST http://llm-runtime.railway.internal:11434/api/chat` com `200`.

3. References entre servicos no Railway
- `DATABASE_URL` montada com referencias do `Postgres-w1Lp`;
- `REDIS_URL` referenciada do `Redis`;
- `LLM_BASE_URL`, `LLM_MODEL` e `LLM_KEEP_ALIVE` referenciadas do `llm-runtime`.

4. Tuning de performance
- modelo padrao ajustado para `qwen2.5:0.5b-instruct`;
- runtime com `OLLAMA_NUM_PARALLEL=2` e `OLLAMA_KEEP_ALIVE=30m`;
- API/worker com contexto e saida reduzidos para baixar latencia.

5. Correcao de erro critico em producao
- erro 500 no webhook por `customer_id` nulo em caminho legado;
- mitigacao aplicada no Postgres:
  - default de `customer_id`;
  - preenchimento de registros nulos.

## Validacao final

- todos os servicos em `SUCCESS`:
  - `projeto-automacao`
  - `worker`
  - `llm-runtime`
  - `Postgres-w1Lp`
  - `Redis`
- `GET /health` retornando `status=ok`;
- webhook de teste aceito e enfileirado;
- mensagem outbound gerada com `llm_status=completed`.

## Ganho observado

- tempo de processamento de mensagem com LLM:
  - antes: ~11.1s
  - depois do tuning: ~5.19s

## Pendencias

1. Ajustar token/credenciais reais da Meta para envio outbound sem `401`.
2. Subir qualidade de resposta comercial (o `0.5b` e mais rapido, mas responde pior que `1.5b`).

## Conclusao

O objetivo principal do dia foi cumprido:  
o LLM saiu da maquina local, passou a rodar no Railway em servico separado, integrado e estavel para o fluxo real.
