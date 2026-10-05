@echo off
REM Mo 4 cua so, moi cua so chay mot service
cd /d %~dp0
start "Student Service - 8001"      /D student-service      cmd /k "..\.venv\Scripts\python manage.py runserver 8001"
start "Thesis Service - 8002"       /D thesis-service       cmd /k "..\.venv\Scripts\python manage.py runserver 8002"
start "Registration Service - 8003" /D registration-service cmd /k "..\.venv\Scripts\python manage.py runserver 8003"
start "Web Portal - 8000"           /D web-portal           cmd /k "..\.venv\Scripts\python manage.py runserver 8000"
echo Da mo 4 service. Giao dien: http://127.0.0.1:8000/
