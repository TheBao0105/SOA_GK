@echo off
chcp 65001 >nul
setlocal
set "SOA_PROJECT=%~dp0"
if not exist "%SOA_PROJECT%\.venv\Scripts\python.exe" (
  echo Không tìm thấy môi trường ảo Python (.venv) trong %SOA_PROJECT%.
  pause
  exit /b 1
)
cd /d "%SOA_PROJECT%"
echo Đang áp dụng các migration còn thiếu với cấu hình SQL Server hiện tại...
"%SOA_PROJECT%\.venv\Scripts\python.exe" -B "%SOA_PROJECT%\scripts\migrate_all.py"
if errorlevel 1 (
  echo Migration thất bại. Xem lỗi phía trên. Cấu hình database chưa bị thay đổi.
  pause
  exit /b 1
)
echo Migration hoàn tất. Khởi động lại toàn bộ service bằng run_all.bat.
echo Kiểm thử trên SQL Server: .venv\Scripts\python.exe -B scripts\test_all.py --sql-server
pause
