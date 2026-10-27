"""Read-only login and cross-service access diagnosis. Never logs passwords/tokens."""
import getpass
import json
from pathlib import Path
import subprocess
import sys
import requests

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("identity-service", "student-service", "thesis-service", "registration-service", "web-portal")


def main():
    configurations = {}
    failed = False
    # Import each service in its own process: Django settings must not leak between services.
    code = """import os,json,hashlib;os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
from django.conf import settings
from pathlib import Path
key=Path(settings.JWT_PUBLIC_KEY_PATH) if hasattr(settings,'JWT_PUBLIC_KEY_PATH') else None
print(json.dumps({'issuer':getattr(settings,'JWT_ISSUER',None),'public_key_sha256':hashlib.sha256(key.read_bytes()).hexdigest() if key and key.is_file() else None,'key_exists':key.is_file() if key else None,'account_check':getattr(settings,'JWT_CHECK_ACCOUNT_STATE',None),'urls':{n:getattr(settings,n) for n in ('IDENTITY_SERVICE_URL','STUDENT_SERVICE_URL','THESIS_SERVICE_URL','REGISTRATION_SERVICE_URL') if hasattr(settings,n)}}))
"""
    for service in SERVICES:
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT/service,
                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20)
        if result.returncode:
            print(f"FAIL {service}: cannot load settings; run manage.py check in that directory.")
            failed = True
            continue
        configurations[service] = json.loads(result.stdout.strip().splitlines()[-1])
        print(service + ': ' + json.dumps(configurations[service], ensure_ascii=True))
    identity = configurations.get('identity-service', {})
    for service in SERVICES[1:4]:
        config = configurations.get(service, {})
        if not config.get('key_exists') or config.get('public_key_sha256') != identity.get('public_key_sha256') or config.get('issuer') != identity.get('issuer'):
            print(f"FAIL {service}: missing/different public key or JWT issuer; fix local .env paths and restart services.")
            failed = True
    portal = configurations.get('web-portal', {}).get('urls', {})
    if not portal:
        return 1
    username = input('Identity username/email: ').strip()
    password = getpass.getpass('Password (hidden): ')
    try:
        with requests.Session() as client:
            response = client.post(portal['IDENTITY_SERVICE_URL'].rstrip('/')+'/api/auth/login/',
                                   json={'username': username, 'password': password}, timeout=10, allow_redirects=False)
            password = None
            print('Identity login HTTP', response.status_code)
            if response.status_code != 200:
                print('FAIL: login rejected. Check Identity terminal; no token was printed.')
                return 1
            data = response.json()
            user = data.get('user', {})
            if not isinstance(user, dict):
                print('FAIL: Identity returned invalid user metadata.')
                return 1
            print('Identity role:', user.get('role'))
            if user.get('role') not in ('ADMIN', 'LECTURER', 'STUDENT'):
                print('FAIL: unsupported account role. An administrator must check this account.')
                failed = True
            headers = {'Authorization': 'Bearer '+data['access']}
            endpoints = (('IDENTITY_SERVICE_URL','/api/auth/me/'),
                         ('STUDENT_SERVICE_URL','/api/students/'),
                         ('THESIS_SERVICE_URL','/api/theses/'),
                         ('REGISTRATION_SERVICE_URL','/api/registrations/'),
                         ('REGISTRATION_SERVICE_URL','/api/periods/current/'))
            for name, path in endpoints:
                try:
                    response = client.get(portal[name].rstrip('/')+path, headers=headers, timeout=10, allow_redirects=False)
                    print(f"{name} {path}: HTTP {response.status_code}")
                    if response.status_code == 403:
                        print('FAIL: this service denies the fresh Identity token. Check its permissions, running code version and account role; Portal cookies are not the cause.')
                    elif response.status_code == 401:
                        print('FAIL: token rejected. Check public key/issuer, system clock and online Identity URL.')
                    elif response.status_code >= 500:
                        print('FAIL: inspect this service terminal, database and Identity availability.')
                    no_period = path == '/api/periods/current/' and response.status_code == 404
                    if no_period:
                        print('OK: no current registration period on this database.')
                    failed |= response.status_code != 200 and not no_period
                except requests.RequestException:
                    print(f'FAIL {name}: connection failed. Check URL and running process.')
                    failed = True
    except (requests.RequestException, ValueError, KeyError, TypeError):
        print('FAIL: Identity connection or response invalid; inspect its terminal. No credentials printed.')
        return 1
    print('PASS: fresh token accepted by all APIs.' if not failed else 'FAIL: fix the reported service/configuration, restart all five processes and rerun.')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
