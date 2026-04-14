@echo off
setlocal

set "ROOT=%~dp0.."
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "SCRIPT=%ROOT%\road_test\chat_railway_prod.py"

if not exist "%PY%" (
  echo [ERRO] Python da venv nao encontrado: "%PY%"
  echo Execute primeiro: cmd /c .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)

"%PY%" "%SCRIPT%" %*
exit /b %errorlevel%
