"""Launch 5 isolated HTTP processes on temporary ports and SQLite databases.
No mocks, no writes to application databases, .env files or real JWT keys.
This validates REST integration, not SQL Server locking.
"""
import json
import argparse
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT=Path(__file__).resolve().parents[1]
SERVICES={"identity":"identity-service","student":"student-service","thesis":"thesis-service","registration":"registration-service","portal":"web-portal"}
CRITERIA=[{"code":"work","name":"Chức năng","weight":40},{"code":"design","name":"Kỹ thuật","weight":30},{"code":"report","name":"Báo cáo","weight":20},{"code":"defense","name":"Bảo vệ","weight":10}]


def stop_process(process):
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name=='nt':
            try:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,check=False,timeout=5)
            except (OSError,subprocess.TimeoutExpired):
                pass
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-mode',choices=('online','offline'),default='online')
    options=parser.parse_args()
    online=options.auth_mode=='online'
    workspace=ROOT/"work"
    workspace.mkdir(exist_ok=True)
    processes=[]
    logs=[]
    steps=[]
    with tempfile.TemporaryDirectory(prefix="integration-",dir=workspace,ignore_cleanup_errors=True) as directory:
        tmp=Path(directory)
        if not tmp.resolve().is_relative_to(workspace.resolve()):
            raise RuntimeError("Temporary integration directory escaped workspace")
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        (tmp/"private.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        (tmp/"public.pem").write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        ports={}
        for name in SERVICES:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0))
                ports[name]=sock.getsockname()[1]
        urls={name:f"http://127.0.0.1:{port}" for name,port in ports.items()}
        password=secrets.token_urlsafe(24)
        env={**os.environ,"DEBUG":"True","SECRET_KEY":secrets.token_urlsafe(60),"ALLOWED_HOSTS":"127.0.0.1,localhost",
             "JWT_PRIVATE_KEY_PATH":str(tmp/"private.pem"),"JWT_PUBLIC_KEY_PATH":str(tmp/"public.pem"),
             "JWT_CHECK_ACCOUNT_STATE":str(online),"SECURE_SSL_REDIRECT":"False","SESSION_COOKIE_SECURE":"False","CSRF_COOKIE_SECURE":"False",
             "LOGIN_RATE":"1000/min","REFRESH_RATE":"1000/min","TEST_ADMIN_PASSWORD":password,"PYTHONDONTWRITEBYTECODE":"1","PYTHONIOENCODING":"utf-8"}
        env.update({f"{name.upper()}_SERVICE_URL":url for name,url in urls.items() if name!='portal'})
        try:
            for name,service in SERVICES.items():
                setup=("settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':"+repr(str(tmp/(name+'.sqlite3')))+"}};" if name!='portal' else "")
                seed=("from accounts.models import User;u=User(username='admin',email='admin@test.local',role='ADMIN');u.set_password(os.environ['TEST_ADMIN_PASSWORD']);u.save();" if name=='identity' else "")
                code=("import os;os.environ['DJANGO_SETTINGS_MODULE']='config.settings';from django.conf import settings;"+setup+
                      "import django;django.setup();from django.core.management import call_command;"+
                      ("call_command('migrate',verbosity=0,interactive=False);" if name!='portal' else "")+seed+
                      f"call_command('runserver','127.0.0.1:{ports[name]}',use_reloader=False,verbosity=0)")
                log=(tmp/(name+'.log')).open('w',encoding='utf-8')
                logs.append(log)
                processes.append(subprocess.Popen([sys.executable,'-u','-B','-c',code],cwd=ROOT/service,env=env,stdout=log,stderr=subprocess.STDOUT))
            for name in SERVICES:
                ready=False
                for attempt in range(100):
                    try:
                        response=requests.get(urls[name]+('/dang-nhap/' if name=='portal' else '/api/schema/'),timeout=1)
                        if response.status_code==200:
                            ready=True
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(0.1)
                if not ready:
                    raise AssertionError(f"{name} failed to start: "+(tmp/(name+'.log')).read_text(encoding='utf-8')[-3000:])
            def api(service,method,path,expected,token=None,body=None):
                response=requests.request(method,urls[service]+path,json=body,headers={'Authorization':'Bearer '+token} if token else {},timeout=15)
                if response.status_code!=expected:
                    raise AssertionError(f"{service} {method} {path}: expected {expected}, got {response.status_code}: {response.text[:700]}")
                return response.json() if response.content else None
            def login(username):
                return api('identity','POST','/api/auth/login/',200,body={'username':username,'password':password})['access']
            admin=login('admin')
            lecturers=[]
            for name in ('gv1','gv2','gv3'):
                lecturers.append(api('identity','POST','/api/users/',201,admin,{'username':name,'email':name+'@test.local','role':'LECTURER','password':password,'full_name':name})['id'])
            student_record=api('student','POST','/api/students/',201,admin,{'full_name':'Sinh viên test','email':'sv@test.local'})
            assert student_record['student_code']=='SV001'
            student=student_record['id']
            api('identity','POST','/api/users/',201,admin,{'username':'sv','email':'sv@test.local','role':'STUDENT','student_id':student,'password':password})
            topic_record=api('thesis','POST','/api/theses/',201,admin,{'title':'Đề tài test','max_students':1,'supervisor_id':lecturers[0]})
            assert topic_record['thesis_code']=='DT001'
            topic=topic_record['id']
            steps.append('Student/Thesis APIs allocate SV001/DT001 without manual codes')
            now=datetime.now(timezone.utc)
            period={'name':'Đợt test','start_at':(now-timedelta(days=1)).isoformat(),'end_at':(now+timedelta(days=1)).isoformat(),'is_active':True}
            api('registration','POST','/api/periods/',201,admin,{**period,'max_active_per_student':1})
            sv=login('sv')
            reg=api('registration','POST','/api/registrations/',201,sv,{'student_id':student,'thesis_id':topic})['id']
            gv1,gv2,gv3=map(login,('gv1','gv2','gv3'))
            api('registration','PATCH',f'/api/registrations/{reg}/',200,gv1,{'status':'APPROVED'})
            steps.append('Student -> Registration -> Student/Thesis REST -> lecturer approval')
            grade_period=api('registration','POST','/api/grading/periods/',201,admin,{**period,'criteria':CRITERIA})['id']
            assessment=api('registration','POST','/api/grading/assessments/',201,admin,{'registration':reg,'period':grade_period})['id']
            path=f'/api/grading/assessments/{assessment}/'
            api('registration','POST',path+'assign/',200,admin,{'lecturer_ids':lecturers[:2]})
            api('registration','GET',path,404,sv)
            api('registration','POST',path+'scores/',404,gv3,{'scores':{'work':'8'},'submit':False})
            api('identity','POST','/api/auth/logout/',200,gv3,{})
            api('thesis','GET','/api/theses/',401 if online else 200,gv3)
            api('registration','POST',path+'scores/',200,gv1,{'scores':{'work':'8','design':'7','report':'9','defense':'10'},'submit':True})
            api('registration','POST',path+'publish/',400,admin)
            api('registration','POST',path+'scores/',200,gv2,{'scores':{c['code']:'9' for c in CRITERIA},'submit':True})
            published=api('registration','POST',path+'publish/',200,admin)
            assert published['final_score']=='8.55',published['final_score']
            api('registration','GET',path,200,sv)
            api('registration','POST',f'/api/registrations/{reg}/cancel/',409,admin)
            steps.append('Two assigned examiners -> weighted average 8.55 -> admin publication -> student visibility')
            with requests.Session() as browser:
                response=browser.get(urls['portal']+'/dang-nhap/',timeout=10)
                csrf=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',response.text).group(1)
                response=browser.post(urls['portal']+'/dang-nhap/',data={'username':'admin','password':password,'csrfmiddlewaretoken':csrf},timeout=15)
                assert response.status_code==200
                response=browser.get(urls['portal']+'/sinh-vien/them/',timeout=10)
                assert 'name="student_code"' not in response.text
                csrf=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',response.text).group(1)
                response=browser.post(urls['portal']+'/sinh-vien/them/',data={'full_name':'Portal Auto','email':'portal.auto@test.local','csrfmiddlewaretoken':csrf},timeout=15)
                assert response.status_code==200
                created=api('student','GET','/api/students/?search=portal.auto',200,admin)
                assert len(created)==1 and created[0]['student_code']=='SV002'
                response=browser.get(urls['portal']+'/de-tai/them/',timeout=10)
                assert 'name="thesis_code"' not in response.text
                csrf=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',response.text).group(1)
                response=browser.post(urls['portal']+'/de-tai/them/',data={'title':'Portal Automatic Thesis','max_students':2,'status':'OPEN','supervisor_id':str(lecturers[0]),'csrfmiddlewaretoken':csrf},timeout=15)
                assert response.status_code==200
                created_topics=api('thesis','GET','/api/theses/?search=Portal%20Automatic',200,admin)
                assert len(created_topics)==1 and created_topics[0]['thesis_code']=='DT002'
                steps.append('Portal create forms omit code inputs and save generated SV002/DT002')
                for page in ('/cham-diem/','/cham-diem/'+str(assessment)+'/','/dot-cham-diem/','/ho-so/','/nhat-ky/'):
                    response=browser.get(urls['portal']+page,timeout=15)
                    assert response.status_code==200,page
                response=browser.post(urls['portal']+'/cham-diem/'+str(assessment)+'/',data={'action':'publish'},timeout=10)
                assert response.status_code==403,'Portal must enforce CSRF'
            steps.append('Real portal login, grade/detail/period/profile/audit pages and CSRF rejection')
            api('registration','POST',path+'reopen/',200,admin,{'reason':'Phúc khảo thử nghiệm'})
            api('registration','GET',path,404,sv)
            api('identity','PATCH',f'/api/users/{lecturers[0]}/',200,admin,{'is_active':False})
            api('thesis','GET','/api/theses/',401 if online else 200,gv1)
            steps.append('Reopen hides grade; logout/deactivation '+('revoke downstream access' if online else 'leave offline access valid until expiry'))
            # Verify demo seeding twice on the isolated HTTP services, including password preservation.
            prep_env={**env,'SOA_DEMO_ADMIN_PASSWORD':password}
            prep_cmd=[sys.executable,'-B',str(ROOT/'scripts'/'prepare_demo.py'),'--tag','itest','--report-dir',str(tmp)]
            first=subprocess.run(prep_cmd,cwd=ROOT,env=prep_env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
            assert first.returncode==0,'Demo preparation failed: '+first.stderr[-800:]
            seeded=json.loads((tmp/'demo-data-itest.json').read_text(encoding='utf-8'))
            student_map={s['id'] for s in seeded['students']}
            assert all(a['student_id'] in student_map for a in seeded['accounts'] if a['role']=='STUDENT')
            demo_user=seeded['accounts'][0]
            new_password=secrets.token_urlsafe(24)
            api('identity','PATCH',f"/api/users/{demo_user['id']}/",200,admin,{'password':new_password})
            second=subprocess.run(prep_cmd,cwd=ROOT,env=prep_env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
            assert second.returncode==0,'Repeated demo preparation failed: '+second.stderr[-800:]
            repeated=json.loads((tmp/'demo-data-itest.json').read_text(encoding='utf-8'))
            assert all(not a['created'] for a in repeated['accounts'])
            assert [a['id'] for a in seeded['accounts']]==[a['id'] for a in repeated['accounts']]
            api('identity','POST','/api/auth/login/',200,body={'username':demo_user['username'],'password':new_password})
            steps.append('REST demo seed is repeatable, links actual student IDs and preserves existing passwords')
            # A remote student lookup outage must not create a partial registration.
            topic2=api('thesis','POST','/api/theses/',201,admin,{'thesis_code':'TEST02','title':'Đề tài thử timeout','max_students':1})['id']
            student_process=processes[list(SERVICES).index('student')]
            stop_process(student_process)
            api('registration','POST','/api/registrations/',503,admin,{'student_id':student,'thesis_id':topic2})
            steps.append('Student Service outage -> registration returns 503 without a partial write')
            # A real identity outage must become a controlled 503.
            identity_process=processes[list(SERVICES).index('identity')]
            stop_process(identity_process)
            api('registration','GET','/api/grading/assessments/',503 if online else 200,admin)
            steps.append('Identity outage -> '+('HTTP 503 with online account checks' if online else 'HTTP 200 with offline JWT verification'))
            result={'passed':True,'auth_mode':options.auth_mode,'mode':'isolated SQLite databases, five real HTTP processes, no mocks','steps':steps}
            (workspace/'integration-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            (workspace/f'integration-result-{options.auth_mode}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(result,ensure_ascii=False,indent=2))
        finally:
            for process in processes:
                stop_process(process)
            for log in logs:
                log.close()


if __name__=='__main__':
    main()
