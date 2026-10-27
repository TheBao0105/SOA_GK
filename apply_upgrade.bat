@echo off
setlocal
set "SOA_PROJECT=C:\Users\Admin\SOA_GK"
if not exist "%SOA_PROJECT%\.venv\Scripts\python.exe" (
  echo Python virtual environment not found in %SOA_PROJECT%.
  pause
  exit /b 1
)
cd /d "%SOA_PROJECT%"
echo Applying additive migrations using the existing SQL Server configuration...
"%SOA_PROJECT%\.venv\Scripts\python.exe" -B "%SOA_PROJECT%\scripts\migrate_all.py"
if errorlevel 1 (
  echo Migration failed. Read the error above. Database configuration has not been changed.
  pause
  exit /b 1
)
echo Migration completed. Restart all services with run_all.bat.
echo To verify SQL Server tests: .venv\Scripts\python.exe -B scripts\test_all.py --sql-server
pause
