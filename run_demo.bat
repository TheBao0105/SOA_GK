@echo off
setlocal
if /I "%~1"=="online" goto online
if not "%~1"=="" if /I not "%~1"=="offline" (
  echo Usage: run_demo.bat [offline^|online]
  exit /b 1
)
set "JWT_CHECK_ACCOUNT_STATE=False"
echo SOA demo: local JWT verification. Existing access tokens remain valid until expiry.
goto launch
:online
set "JWT_CHECK_ACCOUNT_STATE=True"
echo SOA demo: verify current account state with Identity. Identity outage returns 503.
:launch
set "DEBUG=True"
set "ALLOWED_HOSTS=localhost,127.0.0.1,[::1]"
set "SECURE_SSL_REDIRECT=False"
set "SESSION_COOKIE_SECURE=False"
set "CSRF_COOKIE_SECURE=False"
pushd "%~dp0"
call run_all.bat
popd
endlocal
