"""
Kiểm tra chống vượt chỉ tiêu khi nhiều sinh viên đăng ký CÙNG LÚC.

Cách làm:
  1. Đăng nhập admin ở Identity Service (8004).
  2. Tạo 1 đề tài tạm (max_students=1) ở Thesis Service và N sinh viên tạm ở Student Service.
  3. Gửi N request POST /api/registrations/ song song (mỗi sinh viên một request) vào đề tài đó.
  4. Kết quả đúng: đúng 1 request 201, còn lại 400 "Thesis has reached maximum students".
  5. Dọn dẹp: xóa đăng ký, đề tài và sinh viên tạm.

Cần chạy đủ 4 service 8001-8004 (với SQL Server thật) với các migration mới nhất.
Chạy từ thư mục gốc SOA_GK, đã activate venv:

    python registration-service\\scripts\\concurrency_test.py
    python registration-service\\scripts\\concurrency_test.py --students 20 --password Admin@2026
"""
import argparse
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import requests

IDENTITY = "http://127.0.0.1:8004"
STUDENT = "http://127.0.0.1:8001"
THESIS = "http://127.0.0.1:8002"
REGISTRATION = "http://127.0.0.1:8003"


def body_of(response):
    try:
        return response.json()
    except ValueError:  # ví dụ lỗi 500 trả HTML
        return {"error": f"HTTP {response.status_code} (không phải JSON - xem log của service)"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--students", type=int, default=10, help="số request song song (mặc định 10)")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="Admin@2026")
    args = parser.parse_args()
    if not 2 <= args.students <= 50:
        parser.error("--students must be between 2 and 50 for this small demo")

    login = requests.post(f"{IDENTITY}/api/auth/login/",
                          json={"username": args.username, "password": args.password}, timeout=10)
    if login.status_code != 200:
        sys.exit(f"Đăng nhập thất bại: {login.status_code} {login.text}")
    headers = {"Authorization": f"Bearer {login.json()['access']}"}

    tag = uuid.uuid4().hex[:8]
    thesis = requests.post(f"{THESIS}/api/theses/", headers=headers, timeout=10, json={
        "thesis_code": f"TMP{tag}", "title": "Đề tài thử tải đồng thời", "max_students": 1,
    })
    if thesis.status_code != 201:
        sys.exit(f"Không tạo được đề tài tạm: {thesis.status_code} {thesis.text}")
    thesis_id = thesis.json()["id"]

    student_ids = []
    ok = False
    try:
        for i in range(args.students):
            r = requests.post(f"{STUDENT}/api/students/", headers=headers, timeout=10, json={
                "student_code": f"T{tag}{i:02d}", "full_name": f"Sinh viên thử {i}",
                "email": f"t{tag}{i:02d}@test.local",
            })
            if r.status_code != 201:
                sys.exit(f"Không tạo được sinh viên tạm: {r.status_code} {r.text}")
            student_ids.append(r.json()["id"])

        barrier = Barrier(len(student_ids))  # cho tất cả thread bấm "gửi" cùng một lúc

        def register(student_id):
            barrier.wait()
            response = requests.post(f"{REGISTRATION}/api/registrations/", headers=headers, timeout=30,
                                     json={"student_id": student_id, "thesis_id": thesis_id})
            return response.status_code, body_of(response)

        with ThreadPoolExecutor(max_workers=len(student_ids)) as pool:
            results = list(pool.map(register, student_ids))

        created = [body for code, body in results if code == 201]
        print(f"Gửi {len(results)} request song song vào đề tài id={thesis_id} (tối đa 1 sinh viên):")
        summary = {}
        for code, body in results:
            key = f"{code} {body.get('error', 'Created')}"
            summary[key] = summary.get(key, 0) + 1
        for key, count in sorted(summary.items()):
            print(f"  {count:>3} x {key}")

        active = requests.get(f"{REGISTRATION}/api/registrations/", headers=headers, timeout=10,
                              params={"thesis_id": thesis_id, "active": "true"}).json()
        print(f"Số đăng ký còn hiệu lực trong database: {len(active)}")
        rejected = [body for code, body in results if code == 400 and body.get("error") == "Thesis has reached maximum students"]
        ok = len(created) == 1 and len(active) == 1 and len(rejected) == len(student_ids) - 1
        print("KẾT QUẢ: ĐẠT - không vượt chỉ tiêu" if ok else "KẾT QUẢ: KHÔNG ĐẠT - kiểm tra chỉ tiêu, mã lỗi và log service")
    finally:
        # Dọn dữ liệu tạm (xóa đăng ký trước, rồi mới xóa được đề tài / sinh viên)
        leftovers = requests.get(f"{REGISTRATION}/api/registrations/", headers=headers, timeout=10,
                                 params={"thesis_id": thesis_id}).json()
        for registration in leftovers:
            requests.delete(f"{REGISTRATION}/api/registrations/{registration['id']}/", headers=headers, timeout=10)
        requests.delete(f"{THESIS}/api/theses/{thesis_id}/", headers=headers, timeout=10)
        for student_id in student_ids:
            requests.delete(f"{STUDENT}/api/students/{student_id}/", headers=headers, timeout=10)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
