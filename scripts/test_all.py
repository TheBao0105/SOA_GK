r"""Run isolated service tests without modifying runtime settings or application databases.
Usage: .venv\Scripts\python scripts\test_all.py --sqlite
       .venv\Scripts\python scripts\test_all.py --sql-server
"""
import argparse
import json
import re
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("student-service", "thesis-service", "registration-service", "identity-service", "web-portal")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sqlite",action="store_true",help="In-memory logic tests; not SQL Server locking verification")
    group.add_argument("--sql-server",action="store_true",help="Uses configured SQL Server; creates unique temporary test databases")
    args=parser.parse_args()
    if args.sql_server:
        preflight=subprocess.run([sys.executable,"-B",str(ROOT/"scripts"/"check_sql_server.py")],cwd=ROOT)
        if preflight.returncode:
            output=ROOT/"work"/"sql-server-test-result.json"
            output.parent.mkdir(exist_ok=True)
            output.write_text(json.dumps({"mode":"sql-server","passed":False,"blocked":"database_connection","total_tests":0},indent=2),encoding="utf-8")
            print("SQL Server tests were not run: connection preflight failed.")
            return preflight.returncode
    tmp=ROOT/"work"/"test-temp"
    tmp.mkdir(parents=True,exist_ok=True)
    failed=[]
    results=[]
    for service in SERVICES:
        setup="settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}};" if args.sqlite or service=="web-portal" else f"settings.DATABASES['default']['TEST']={{'NAME':'test_soa_{uuid.uuid4().hex}'}};"
        code=("import os,tempfile;tempfile.tempdir="+repr(str(tmp))+";os.environ['DJANGO_SETTINGS_MODULE']='config.settings';"
              "from django.conf import settings;"+setup+
              "import django;django.setup();from django.core.management import call_command;"
              "call_command('makemigrations',check=True,dry_run=True,verbosity=0);"
              "call_command('test',verbosity=1,interactive=False)")
        print(f"\n=== {service} ({'SQLite' if args.sqlite else 'configured SQL Server'}) ===",flush=True)
        result=subprocess.run([sys.executable,"-B","-c",code],cwd=ROOT/service,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","PYTHONIOENCODING":"utf-8"},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace")
        print(result.stdout,flush=True)
        count=re.search(r"Ran (\d+) tests?",result.stdout)
        skipped=re.search(r"skipped=(\d+)",result.stdout)
        results.append({"service":service,"exit_code":result.returncode,"tests":int(count.group(1)) if count else 0,"skipped":int(skipped.group(1)) if skipped else 0})
        if result.returncode:
            failed.append(service)
    report={"mode":"sqlite" if args.sqlite else "sql-server","passed":not failed,"total_tests":sum(row["tests"] for row in results),"results":results}
    report["skipped_tests"]=sum(row["skipped"] for row in results)
    report["executed_tests"]=report["total_tests"]-report["skipped_tests"]
    (ROOT/"work"/"unit-test-result.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    (ROOT/"work"/("sql-server-test-result.json" if args.sql_server else "sqlite-test-result.json")).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("\nFailed: "+", ".join(failed) if failed else "\nAll service test suites passed.")
    return bool(failed)


if __name__=="__main__":
    sys.exit(main())
