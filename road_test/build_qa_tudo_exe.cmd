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

echo Gerando EXE do qa_tudo...
".\.venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name qa_tudo ^
  --collect-submodules celery ^
  --collect-submodules alembic ^
  --hidden-import kombu.transport.memory ^
  qa_tudo.py

if errorlevel 1 (
  echo [ERRO] Falha ao gerar EXE.
  exit /b 1
)

echo.
echo [OK] EXE gerado em: dist\qa_tudo.exe
echo.
echo Execute na raiz do projeto:
echo dist\qa_tudo.exe --no-dashboard --no-pause

endlocal
