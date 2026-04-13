@echo off
setlocal

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
  echo [ERRO] Python da venv nao encontrado em .venv\Scripts\python.exe
  echo Crie a venv primeiro.
  exit /b 1
)

echo Instalando/atualizando PyInstaller...
".\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet pyinstaller
if errorlevel 1 (
  echo [ERRO] Falha ao instalar PyInstaller.
  exit /b 1
)

echo Gerando EXE do road test...
".\.venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name chat_estudio_road_test ^
  --add-data "app\prompts\studio_agendamento.md;app\prompts" ^
  road_test\chat_test_app.py

if errorlevel 1 (
  echo [ERRO] Falha ao gerar EXE.
  exit /b 1
)

echo.
echo [OK] EXE gerado em: dist\chat_estudio_road_test.exe
echo.
echo Para executar:
echo dist\chat_estudio_road_test.exe

endlocal
