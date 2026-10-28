"""Kiểm tra (chỉ đọc) kết nối SQL Server đã cấu hình và các migration chưa áp dụng."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SERVICES=("student-service","thesis-service","registration-service","identity-service")
CHECK = r"""
import os,json
os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
import django
django.setup()
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
options=settings.DATABASES['default'].setdefault('OPTIONS',{})
options.update(connection_timeout=4,connection_retries=0,query_timeout=4)
result={'host':settings.DATABASES['default'].get('HOST'),'database':settings.DATABASES['default'].get('NAME')}
try:
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        cursor.fetchone()
    executor=MigrationExecutor(connection)
    result.update(connected=True,pending_migrations=[f'{m.app_label}.{m.name}' for m,backwards in executor.migration_plan(executor.loader.graph.leaf_nodes())])
except Exception as exc:
    result.update(connected=False,error_type=type(exc).__name__,error=str(exc))
finally:
    connection.close()
print(json.dumps(result))
"""


def main():
    results=[]
    for service in SERVICES:
        try:
            completed=subprocess.run([sys.executable,'-B','-c',CHECK],cwd=ROOT/service,
                                     env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'},
                                     capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
            result=json.loads(completed.stdout.strip().splitlines()[-1])
        except (subprocess.TimeoutExpired,ValueError,IndexError) as exc:
            result={'connected':False,'error_type':type(exc).__name__,'error':'Connection check failed or timed out. Check SQL Server access from this terminal.'}
        result['service']=service
        results.append(result)
        print(service+': '+('OK; pending migrations: '+str(len(result.get('pending_migrations',[]))) if result['connected'] else 'FAILED; '+result.get('error_type','error')),flush=True)
    report={'all_connected':all(row['connected'] for row in results),'read_only':True,'results':results}
    output=ROOT/'work'/'sql-server-check.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not report['all_connected']:
        print('Run this check in a normal Windows terminal with SQL Server access. No server settings or databases were changed.')
    print('Details: '+str(output))
    return 0 if report['all_connected'] else 1


if __name__=='__main__':
    sys.exit(main())
