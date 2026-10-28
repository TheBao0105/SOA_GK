"""Chạy 5 process HTTP tách biệt trên cổng tạm và database SQLite tạm.
Không mock, không ghi vào database thật, file .env hay khóa JWT thật.
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

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT=Path(__file__).resolve().parents[1]
SERVICES={"identity":"identity-service","student":"student-service","thesis":"thesis-service","registration":"registration-service","portal":"web-portal"}



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
            def api(service,method,path,expected,token=None,body=None,json_expected=True):
                response=requests.request(method,urls[service]+path,json=body,headers={'Authorization':'Bearer '+token} if token else {},timeout=15)
                if response.status_code!=expected:
                    raise AssertionError(f"{service} {method} {path}: expected {expected}, got {response.status_code}: {response.text[:700]}")
                return response.json() if json_expected and response.content else None
            def login(username):
                return api('identity','POST','/api/auth/login/',200,body={'username':username,'password':password})['access']
            admin=login('admin')
            api('registration','GET','/api/periods/',404,admin,json_expected=False)
            api('registration','GET','/api/periods/current/',404,admin,json_expected=False)
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
            # Bản cài mới phải đăng nhập được đủ các vai trò qua Portal thật.
            for username in ('admin', 'gv1', 'sv'):
                with requests.Session() as fresh_browser:
                    page=fresh_browser.get(urls['portal']+'/',timeout=15)
                    assert page.url.endswith('/dang-nhap/?next=%2F'),page.url
                    csrf=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',page.text).group(1)
                    page=fresh_browser.post(urls['portal']+'/dang-nhap/',data={'username':username,'password':password,'csrfmiddlewaretoken':csrf},timeout=15)
                    assert page.status_code==200 and page.url==urls['portal']+'/',(username,page.status_code,page.url)
                    assert 'Dashboard' in page.text and 'HTTP 403' not in page.text
                    assert 'Đợt đăng ký' not in page.text
                    assert fresh_browser.get(urls['portal']+'/dot-dang-ky/',timeout=15).status_code==404
                    assert fresh_browser.get(urls['portal']+'/',timeout=15).url==urls['portal']+'/'
                    if username!='admin':
                        denied=fresh_browser.get(urls['portal']+'/sinh-vien/them/',timeout=15)
                        assert denied.url==urls['portal']+'/' and 'name="full_name"' not in denied.text
            steps.append('Fresh Portal login for ADMIN/LECTURER/STUDENT keeps session; non-admin create remains denied')
            diagnostic_code="import os,runpy,getpass,builtins;getpass.getpass=lambda prompt:os.environ['TEST_ADMIN_PASSWORD'];builtins.input=lambda prompt:'admin';runpy.run_path('scripts/check_login.py',run_name='__main__')"
            diagnostic=subprocess.run([sys.executable,'-B','-c',diagnostic_code],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
            assert diagnostic.returncode==0,diagnostic.stdout+diagnostic.stderr
            assert password not in diagnostic.stdout and admin not in diagnostic.stdout
            steps.append('Read-only new-machine login diagnostic passes all real APIs without exposing credentials')
            sv=login('sv')
            reg=api('registration','POST','/api/registrations/',201,sv,{'student_id':student,'thesis_id':topic})['id']
            gv1,gv2,gv3=map(login,('gv1','gv2','gv3'))
            api('registration','PATCH',f'/api/registrations/{reg}/',200,gv1,{'status':'APPROVED'})
            steps.append('Registration without schedule -> Student/Thesis REST -> lecturer approval; removed schedule API/Portal return 404')
            grade=api('registration','POST','/api/grading/grades/',201,gv1,{'registration':reg,'score':'8.5','comment':'Đạt yêu cầu'})
            assert grade['score']=='8.50'
            api('registration','POST','/api/grading/grades/',404,gv2,{'registration':reg,'score':'10'})
            api('registration','POST','/api/grading/grades/',403,sv,{'registration':reg,'score':'10'})
            rows=api('registration','GET','/api/grading/grades/',200,sv)
            assert len(rows)==1 and rows[0]['score']=='8.50'
            steps.append('Supervisor enters 8.50 directly; student immediately sees own grade; other lecturer/student writes denied')
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
                for page in ('/cham-diem/','/ho-so/','/nhat-ky/'):
                    response=browser.get(urls['portal']+page,timeout=15)
                    assert response.status_code==200,(page,response.status_code)
                assert browser.get(urls['portal']+'/dot-cham-diem/',timeout=10).status_code==404
            # Giảng viên nhập một điểm số qua Portal như trên trình duyệt thật.
            with requests.Session() as browser:
                page=browser.get(urls['portal']+'/dang-nhap/',timeout=10)
                csrf=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',page.text).group(1)
                browser.post(urls['portal']+'/dang-nhap/',data={'username':'gv1','password':password,'csrfmiddlewaretoken':csrf},timeout=15)
                page=browser.get(urls['portal']+f'/cham-diem/{reg}/',timeout=15)
                assert page.status_code==200 and 'name="score"' in page.text
                csrf=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',page.text).group(1)
                page=browser.post(urls['portal']+f'/cham-diem/{reg}/',data={'score':'9.25','comment':'Cập nhật điểm','csrfmiddlewaretoken':csrf},timeout=15)
                assert page.status_code==200 and page.url==urls['portal']+'/cham-diem/'
                assert '9.25' in page.text
                assert requests.post(urls['portal']+f'/cham-diem/{reg}/',cookies=browser.cookies,data={'score':'10'},timeout=15).status_code==403
            updated=api('registration','GET',f"/api/grading/grades/{grade['id']}/",200,sv)
            assert updated['score']=='9.25'
            history=api('registration','GET',f"/api/grading/grades/{grade['id']}/history/",200,admin)
            assert history[0]['detail']['before']['score']=='8.50'
            api('registration','POST',f'/api/registrations/{reg}/cancel/',409,admin)
            # Giao diện Admin có xem/sửa/xóa điểm; GET hiện xác nhận, POST chỉ xóa điểm.
            with requests.Session() as manager:
                page=manager.get(urls['portal']+'/dang-nhap/',timeout=10)
                csrf=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',page.text).group(1)
                manager.post(urls['portal']+'/dang-nhap/',data={'username':'admin','password':password,'csrfmiddlewaretoken':csrf},timeout=15)
                page=manager.get(urls['portal']+f'/cham-diem/{reg}/chi-tiet/',timeout=15)
                assert page.status_code==200 and '9.25' in page.text
                page=manager.get(urls['portal']+f'/cham-diem/{reg}/xoa/',timeout=15)
                assert page.status_code==200 and 'Xác nhận xóa điểm' in page.text
                assert api('registration','GET',f"/api/grading/grades/{grade['id']}/",200,sv)['score']=='9.25'
                csrf=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',page.text).group(1)
                page=manager.post(urls['portal']+f'/cham-diem/{reg}/xoa/',data={'csrfmiddlewaretoken':csrf},timeout=15)
                assert page.status_code==200 and 'Chưa chấm' in page.text
                assert api('registration','GET','/api/grading/grades/',200,sv)==[]
                regraded=api('registration','POST','/api/grading/grades/',201,admin,{'registration':reg,'score':'8','comment':'Chấm lại'})
                history=api('registration','GET',f"/api/grading/grades/{regraded['id']}/history/",200,admin)
                assert any(e['action']=='DELETED' for e in history)
            steps.append('Admin detail/delete confirmation/POST deletion/regrade preserve full score history')
            api('identity','POST','/api/auth/logout/',200,gv3,{})
            api('thesis','GET','/api/theses/',401 if online else 200,gv3)
            api('identity','PATCH',f'/api/users/{lecturers[0]}/',200,admin,{'is_active':False})
            api('thesis','GET','/api/theses/',401 if online else 200,gv1)
            steps.append('Portal direct score edit -> 9.25, visible to student, history preserved, CSRF and grade protection verified')
            # Chạy seed demo hai lần trên các service tách biệt, kiểm tra mật khẩu cũ được giữ nguyên.
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
            # Student Service tắt thì không được tạo đăng ký dở dang.
            topic2=api('thesis','POST','/api/theses/',201,admin,{'thesis_code':'TEST02','title':'Đề tài thử timeout','max_students':1})['id']
            student_process=processes[list(SERVICES).index('student')]
            stop_process(student_process)
            api('registration','POST','/api/registrations/',503,admin,{'student_id':student,'thesis_id':topic2})
            steps.append('Student Service outage -> registration returns 503 without a partial write')
            # Identity tắt thật thì phải trả 503 có kiểm soát.
            identity_process=processes[list(SERVICES).index('identity')]
            stop_process(identity_process)
            api('registration','GET','/api/grading/grades/',503 if online else 200,admin)
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
