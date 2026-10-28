import os
from pathlib import Path
import subprocess
import sys
from django.test import SimpleTestCase


class SimpleGradeUpgradeTests(SimpleTestCase):
    def test_existing_scores_and_drafts_are_preserved(self):
        # Chạy trong process con mới để không phải đảo ngược migration chuyển đổi một chiều.
        code = """
import os
os.environ["DJANGO_SETTINGS_MODULE"]="config.settings"
from django.conf import settings
settings.DATABASES={"default":{"ENGINE":"django.db.backends.sqlite3","NAME":":memory:"}}
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
executor=MigrationExecutor(connection)
old_targets=[("registrations","0002_periods_cancel_progress"),("grading","0001_initial")]
executor.migrate(old_targets)
old=executor.loader.project_state(old_targets).apps
now=timezone.now()
schedule=old.get_model("registrations","RegistrationPeriod").objects.create(name="Old",start_at=now-timedelta(days=1),end_at=now+timedelta(days=1))
registration=old.get_model("registrations","Registration").objects.create(student_id=100,thesis_id=200,status="APPROVED",period=schedule)
for i,score in enumerate(("8.50","9.25",None)):
    period=old.get_model("grading","GradingPeriod").objects.create(name="Old rubric "+str(i),start_at=now-timedelta(days=1),end_at=now+timedelta(days=1),criteria=[{"code":"work","name":"Work","weight":"100"}])
    assessment=old.get_model("grading","Assessment").objects.create(registration=registration,period=period,status="PUBLISHED" if score else "IN_PROGRESS",final_score=score,created_by=1)
    old.get_model("grading","GradingAssignment").objects.create(assessment=assessment,lecturer_id=2,lecturer_name="Old Examiner",scores={"work":score or "5"},comment="Keep old comment",submitted_at=now if score else None)
    old.get_model("grading","GradeEvent").objects.create(assessment=assessment,actor_id=1,action="PUBLISHED" if score else "SCORE_SAVED",detail={"old_score":score})
executor=MigrationExecutor(connection)
latest=executor.loader.graph.leaf_nodes()
executor.migrate(latest)
new=executor.loader.project_state(latest).apps
Grade=new.get_model("grading","Grade")
History=new.get_model("grading","GradeHistory")
assert Grade.objects.count()==1
assert Grade.objects.get().score==Decimal("9.25")
assert Grade.objects.get().registration_id==registration.pk
assert History.objects.count()==3
assert History.objects.filter(grade__isnull=True).count()==0
for h in History.objects.all():
    assert h.detail["assignments"][0]["comment"]=="Keep old comment"
    assert h.detail["events"][0]["actor_id"]==1
    assert h.detail["period"]["criteria"][0]["weight"]=="100"
assert "dotdangky" not in connection.introspection.table_names()
assert "dot_chamdiem" not in connection.introspection.table_names()
assert "ketqua_chamdiem" not in connection.introspection.table_names()
assert new.get_model("registrations","Registration").objects.get().status=="APPROVED"
print("Upgrade passed: latest score retained; every legacy score/draft/comment/rubric/event archived; schedules removed.")
"""
        result = subprocess.run([sys.executable,"-B","-c",code],cwd=Path(__file__).resolve().parents[1],
            env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","PYTHONIOENCODING":"utf-8"},
            capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
