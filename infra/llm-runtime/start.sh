#!/bin/sh
set -eu

MODEL="${LLM_MODEL:-qwen2.5:0.5b-instruct}"
MODELS_TO_PULL="${LLM_MODELS_TO_PULL:-$MODEL}"

export OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0:11434}"
export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:-10m}"
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-1}"
export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}"

echo "[llm-runtime] starting ollama on ${OLLAMA_HOST}"
ollama serve &
OLLAMA_PID=$!

cleanup() {
  kill "${OLLAMA_PID}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "[llm-runtime] waiting for ollama API"
READY=0
for _ in $(seq 1 60); do
  if ollama list >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

if [ "${READY}" -ne 1 ]; then
  echo "[llm-runtime] ollama API not ready after timeout"
  exit 1
fi

echo "[llm-runtime] ensuring models: ${MODELS_TO_PULL}"
for RAW_MODEL in $(echo "${MODELS_TO_PULL}" | tr ',' ' '); do
  MODEL_NAME="$(echo "${RAW_MODEL}" | xargs)"
  if [ -z "${MODEL_NAME}" ]; then
    continue
  fi

  if ollama list | awk 'NR>1 {print $1}' | grep -Fxq "${MODEL_NAME}"; then
    echo "[llm-runtime] model already present: ${MODEL_NAME}"
    continue
  fi

  echo "[llm-runtime] pulling model: ${MODEL_NAME}"
  ollama pull "${MODEL_NAME}"
done

echo "[llm-runtime] ready"
wait "${OLLAMA_PID}"
