"""Áp dụng migration còn thiếu cho từng service theo database đang cấu hình của service đó."""
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
# Kiểm tra mọi database trước khi áp dụng migration nào; giữ nguyên cấu hình .env.
check=subprocess.run([sys.executable,"-B",str(root/"scripts"/"check_sql_server.py")],cwd=root)
if check.returncode:
    sys.exit(check.returncode)
for service in ("student-service","thesis-service","registration-service","identity-service"):
    print(f"Migrating {service} with its existing database configuration...",flush=True)
    result=subprocess.run([sys.executable,"-B","manage.py","migrate","--noinput"],cwd=root/service,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"})
    if result.returncode:
        sys.exit(result.returncode)
print("All migrations applied. Start services with run_all.bat.")
