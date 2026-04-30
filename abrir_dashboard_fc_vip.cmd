@echo off
setlocal

set "BASE_URL=https://projeto-automacao-production.up.railway.app"
set "DASHBOARD_URL_1=%BASE_URL%/dashboard"
set "DASHBOARD_URL_2=%BASE_URL%/dashboard/op"

echo Verificando dashboard em producao...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue';" ^
  "$urls=@('%DASHBOARD_URL_1%','%DASHBOARD_URL_2%');" ^
  "$ok=$null;" ^
  "foreach($u in $urls){" ^
  "  try {" ^
  "    $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 15;" ^
  "    if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { $ok=$u; break }" ^
  "  } catch {" ^
  "    $code = $_.Exception.Response.StatusCode.value__ 2>$null;" ^
  "    if ($code -eq 401 -or $code -eq 403) { $ok=$u; break }" ^
  "  }" ^
  "}" ^
  "if ($ok) { Write-Output ('OPEN='+$ok); exit 0 } else { exit 1 }"

if errorlevel 1 (
  echo [ERRO] Nao foi possivel confirmar dashboard em producao agora.
  echo Tente abrir manualmente:
  echo 1) %DASHBOARD_URL_1%
  echo 2) %DASHBOARD_URL_2%
  pause
  exit /b 1
)

for /f "tokens=1,* delims==" %%A in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $urls=@('%DASHBOARD_URL_1%','%DASHBOARD_URL_2%'); $ok=$null; foreach($u in $urls){ try { $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 15; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 400){ $ok=$u; break } } catch { $code = $_.Exception.Response.StatusCode.value__ 2>$null; if($code -eq 401 -or $code -eq 403){ $ok=$u; break } } }; if($ok){ 'OPEN='+$ok }"') do (
  if /i "%%A"=="OPEN" set "OPEN_URL=%%B"
)

if not defined OPEN_URL set "OPEN_URL=%DASHBOARD_URL_1%"
echo Abrindo: %OPEN_URL%
start "" "%OPEN_URL%"
exit /b 0
