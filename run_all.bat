@echo off
chcp 65001 >nul
REM Mở 5 cửa sổ, mỗi cửa sổ chạy một service
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chưa có .venv. Hãy cài dự án theo hướng dẫn trong README.md trước.
  exit /b 1
)
start "Identity Service - 8004"     /D identity-service     cmd /k "..\.venv\Scripts\python manage.py runserver 8004"
start "Student Service - 8001"      /D student-service      cmd /k "..\.venv\Scripts\python manage.py runserver 8001"
start "Thesis Service - 8002"       /D thesis-service       cmd /k "..\.venv\Scripts\python manage.py runserver 8002"
start "Registration Service - 8003" /D registration-service cmd /k "..\.venv\Scripts\python manage.py runserver 8003"
start "Web Portal - 8000"           /D web-portal           cmd /k "..\.venv\Scripts\python manage.py runserver 8000"
echo Đã mở 5 service. Giao diện: http://127.0.0.1:8000/  (xem tài khoản mẫu trong README.md)
