@echo off
chcp 65001 >nul
setlocal
if /I "%~1"=="online" goto online
if not "%~1"=="" if /I not "%~1"=="offline" (
  echo Cách dùng: run_demo.bat [offline^|online]
  exit /b 1
)
set "JWT_CHECK_ACCOUNT_STATE=False"
echo Demo SOA (offline): xác minh JWT tại chỗ. Access token đã cấp vẫn dùng được đến khi hết hạn.
goto launch
:online
set "JWT_CHECK_ACCOUNT_STATE=True"
echo Demo SOA (online): hỏi Identity trạng thái tài khoản mỗi request. Identity tắt thì trả 503.
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
