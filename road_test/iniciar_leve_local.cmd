@echo off
setlocal EnableExtensions

cd /d "%~dp0\.."

set "DEFAULT_MODEL=qwen2.5:1.5b-instruct"
set "OLLAMA_EXE=C:\Users\%USERNAME%\AppData\Local\Programs\Ollama\ollama.exe"

if not exist "%OLLAMA_EXE%" (
  for /f "delims=" %%I in ('where ollama 2^>nul') do set "OLLAMA_EXE=%%I"
)

if not exist "%OLLAMA_EXE%" (
  echo [ERRO] Ollama nao encontrado.
  echo Instale primeiro com: winget install -e --id Ollama.Ollama
  exit /b 1
)

echo [OK] Ollama detectado em: %OLLAMA_EXE%

curl.exe -sS "http://127.0.0.1:11434/api/tags" >nul 2>nul
if errorlevel 1 (
  echo Iniciando Ollama local...
  set "OLLAMA_NUM_PARALLEL=1"
  set "OLLAMA_MAX_LOADED_MODELS=1"
  set "OLLAMA_KEEP_ALIVE=10m"
  start "" "%OLLAMA_EXE%" serve >nul 2>nul

  for /l %%S in (1,1,40) do (
    timeout /t 1 /nobreak >nul
    curl.exe -sS "http://127.0.0.1:11434/api/tags" >nul 2>nul
    if not errorlevel 1 goto server_ready
  )
  echo [ERRO] Nao foi possivel inicializar a API do Ollama na porta 11434.
  exit /b 1
) else (
  echo [OK] Ollama API ja esta respondendo em 11434.
  goto server_ready
)

:server_ready
"%OLLAMA_EXE%" list | findstr /I /C:"%DEFAULT_MODEL%" >nul
if errorlevel 1 (
  echo Modelo %DEFAULT_MODEL% nao encontrado. Baixando...
  "%OLLAMA_EXE%" pull %DEFAULT_MODEL%
  if errorlevel 1 (
    echo [ERRO] Falha ao baixar %DEFAULT_MODEL%.
    exit /b 1
  )
)
echo [OK] Modelo leve pronto: %DEFAULT_MODEL%

if /I "%~1"=="--check" (
  echo [OK] Runtime local leve pronto.
  exit /b 0
)

if not exist "dist\chat_estudio_road_test.exe" (
  echo [ERRO] EXE nao encontrado em dist\chat_estudio_road_test.exe
  echo Gere com: road_test\build_chat_test_exe.cmd
  exit /b 1
)

echo Abrindo chat de teste...
start "" "%CD%\dist\chat_estudio_road_test.exe"
echo [OK] Chat iniciado.
exit /b 0
