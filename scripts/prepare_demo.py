"""Tạo bộ dữ liệu demo riêng qua REST, chạy lại nhiều lần được; không đặt lại mật khẩu cũ, không xóa bản ghi."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import sys

from dotenv import dotenv_values
import requests

ROOT=Path(__file__).resolve().parents[1]
DEMO_PASSWORD="Demo@2026_SOA!"



class DemoError(Exception):
    pass


class DemoApi:
    def __init__(self,urls):
        self.urls=urls
        self.session=requests.Session()

    def call(self,service,method,path,body=None,params=None,expected=(200,)):
        try:
            response=self.session.request(method,self.urls[service]+path,json=body,params=params,timeout=10)
        except requests.RequestException as exc:
            raise DemoError(f"{service} không phản hồi; hãy khởi động đủ service.") from exc
        if response.status_code not in expected:
            # Không bao giờ in toàn bộ phản hồi đăng nhập hay bearer token.
            raise DemoError(f"{service} {method} {path}: HTTP {response.status_code}; xem log service để biết chi tiết.")
        try:
            data=response.json()
        except ValueError as exc:
            raise DemoError(f"{service} trả JSON không hợp lệ.") from exc
        if not isinstance(data,(dict,list)):
            raise DemoError(f"{service} trả cấu trúc JSON không hợp lệ.")
        return data

    def ensure(self,service,path,key,value,body,params=None):
        rows=self.call(service,'GET',path,params=params)
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
            raise DemoError(f"{service}: API danh sách không đúng hợp đồng.")
        matches=[row for row in rows if row.get(key)==value]
        if len(matches)>1:
            raise DemoError(f"Trùng dữ liệu demo: {value}; hãy kiểm tra trên giao diện.")
        if matches:
            return matches[0],False
        return self.call(service,'POST',path,body=body,expected=(201,)),True


def prepare(api,tag):
    report={'tag':tag,'accounts':[],'students':[],'theses':[],'warnings':[]}
    def account(username,role,full_name,student_id=None):
        user,created=api.ensure('identity','/api/users/','username',username,
              {'username':username,'email':username+'@example.test','full_name':full_name,
               'role':role,'student_id':student_id,'password':DEMO_PASSWORD},params={'search':username})
        if user.get('role')!=role or user.get('student_id')!=student_id or not user.get('is_active'):
            raise DemoError(f"Tài khoản {username} đã có cấu hình khác; script không ghi đè. Hãy chọn --tag khác.")
        if user.get('locked_until'):
            report['warnings'].append(f"Kiểm tra/mở khóa {username} tại trang Tài khoản trước khi demo.")
        report['accounts'].append({'id':user['id'],'username':username,'role':role,'student_id':student_id,'created':created})
        return user
    lecturers=[account(f'demo.{tag}.gv{i}','LECTURER',f'Giảng viên demo {tag} {i}') for i in (1,2)]
    for i in (1,2,3):
        code=f'DEMO_{tag.upper()}_SV{i}'
        student,_=api.ensure('student','/api/students/','student_code',code,
              {'student_code':code,'full_name':f'Sinh viên demo {tag} {i}','email':f'demo.{tag}.sv{i}@example.test','class_name':'SOA-DEMO','major':'CNTT'},params={'search':code})
        report['students'].append({'id':student['id'],'student_code':code})
        account(f'demo.{tag}.sv{i}','STUDENT',student['full_name'],student['id'])
    for i,status in ((1,'OPEN'),(2,'OPEN'),(3,'CLOSED')):
        code=f'DEMO_{tag.upper()}_DT{i}'
        lecturer=lecturers[0 if i!=2 else 1]
        topic,_=api.ensure('thesis','/api/theses/','thesis_code',code,
              {'thesis_code':code,'title':f'Đề tài demo {tag} {i}','supervisor_id':lecturer['id'],
               'supervisor':lecturer.get('full_name') or lecturer['username'],'status':status,'max_students':1},params={'search':code})
        report['theses'].append({'id':topic['id'],'thesis_code':code,'status':topic['status'],'max_students':topic['max_students'],'supervisor_id':topic.get('supervisor_id')})
        if topic.get('supervisor_id')!=lecturer['id'] or topic.get('status')!=status or topic.get('max_students')!=1:
            report['warnings'].append(f"{code} đã thay đổi qua demo; dữ liệu được giữ nguyên. Dùng --tag khác để có bộ mới.")
    return report


def main():
    # Console Windows khi chuyển hướng output có thể dùng bảng mã không in được tiếng Việt.
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',default='soa',help='1-6 lowercase letters/digits; choose another tag for a fresh dataset')
    parser.add_argument('--admin-user',default='admin')
    parser.add_argument('--report-dir',type=Path,default=ROOT/'work',help='Location for the ID-only demo report')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9]{1,6}',args.tag):
        parser.error('--tag must contain 1-6 lowercase letters/digits')
    config=dotenv_values(ROOT/'web-portal'/'.env')
    if os.getenv('DEBUG',config.get('DEBUG','True'))!='True':
        parser.error('This data preparation script is only for local DEBUG=True demos.')
    urls={name:(os.getenv(name.upper()+'_SERVICE_URL') or config.get(name.upper()+'_SERVICE_URL') or f'http://127.0.0.1:{port}').rstrip('/')
          for name,port in [('identity',8004),('student',8001),('thesis',8002),('registration',8003)]}
    api=DemoApi(urls)
    try:
        password=os.getenv('SOA_DEMO_ADMIN_PASSWORD') or getpass.getpass('Mật khẩu Admin hiện tại (không hiển thị): ')
        login=api.call('identity','POST','/api/auth/login/',body={'username':args.admin_user,'password':password})
        if not isinstance(login.get('access'),str) or (login.get('user') or {}).get('role')!='ADMIN':
            raise DemoError('Cần đăng nhập bằng tài khoản ADMIN.')
        api.session.headers['Authorization']='Bearer '+login['access']
        report=prepare(api,args.tag)
        output=args.report_dir/f'demo-data-{args.tag}.json'
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
        print('Mật khẩu của các tài khoản demo MỚI: '+DEMO_PASSWORD)
        print('Tài khoản đã có được giữ nguyên mật khẩu. Không xóa đăng ký, điểm hay dữ liệu cũ.')
        print('Dữ liệu demo: '+str(output))
        return 0
    except DemoError as exc:
        print(str(exc),file=sys.stderr)
        return 1
    finally:
        api.session.close()


if __name__=='__main__':
    sys.exit(main())
