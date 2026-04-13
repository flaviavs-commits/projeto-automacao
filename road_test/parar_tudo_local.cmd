@echo off
setlocal EnableExtensions

cd /d "%~dp0\.."

set "OLLAMA_EXE=C:\Users\%USERNAME%\AppData\Local\Programs\Ollama\ollama.exe"
if not exist "%OLLAMA_EXE%" (
  for /f "delims=" %%I in ('where ollama 2^>nul') do (
    set "OLLAMA_EXE=%%I"
    goto :ollama_found
  )
)

:ollama_found
echo Encerrando chat de teste...
taskkill /IM chat_estudio_road_test.exe /F >nul 2>nul
if errorlevel 1 (
  echo [OK] Chat ja estava fechado.
) else (
  echo [OK] Chat encerrado.
)

if exist "%OLLAMA_EXE%" (
  echo Descarregando modelos...
  "%OLLAMA_EXE%" stop qwen2.5:0.5b-instruct >nul 2>nul
  "%OLLAMA_EXE%" stop qwen2.5:1.5b-instruct >nul 2>nul
  "%OLLAMA_EXE%" stop qwen2.5:7b-instruct >nul 2>nul
)

echo Encerrando runtime Ollama...
taskkill /IM ollama.exe /F >nul 2>nul
taskkill /IM "ollama app.exe" /F >nul 2>nul
echo [OK] Runtime local finalizado.

endlocal

