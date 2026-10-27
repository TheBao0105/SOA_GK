"""Apply additive migrations using each service's existing configured database."""
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
# Verify every database before applying any migration; preserve all .env settings.
check=subprocess.run([sys.executable,"-B",str(root/"scripts"/"check_sql_server.py")],cwd=root)
if check.returncode:
    sys.exit(check.returncode)
for service in ("student-service","thesis-service","registration-service","identity-service"):
    print(f"Migrating {service} with its existing database configuration...",flush=True)
    result=subprocess.run([sys.executable,"-B","manage.py","migrate","--noinput"],cwd=root/service,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"})
    if result.returncode:
        sys.exit(result.returncode)
print("All migrations applied. Start services with run_all.bat.")
