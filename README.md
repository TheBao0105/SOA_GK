# Hệ thống quản lý đồ án tốt nghiệp — Demo SOA (Django + DRF + SQL Server)

## 1. Giới thiệu

Project giữa kỳ môn **Công nghệ Web 2026**, xây dựng hệ thống quản lý việc sinh viên đăng ký đề tài đồ án tốt nghiệp.

Hệ thống được xây dựng theo **kiến trúc hướng dịch vụ (SOA)**: gồm **4 Web Service độc lập**, mỗi service có database riêng và giao tiếp với nhau qua **HTTP/REST (JSON)**. Mọi API đều yêu cầu **đăng nhập bằng JWT** do Identity Service cấp.

| Service              | Trách nhiệm         | Port | Database          | Bảng       |
| -------------------- | ------------------- | ---- | ----------------- | ---------- |
| Student Service      | Quản lý sinh viên   | 8001 | `student_db`      | `sinhvien` |
| Thesis Service       | Quản lý đề tài      | 8002 | `thesis_db`       | `detai`    |
| Registration Service | Quản lý đăng ký     | 8003 | `registration_db` | `dangky`   |
| Identity Service     | Đăng nhập, tài khoản, cấp JWT | 8004 | `auth_db` | `taikhoan`, `token_lammoi`, `nhatky` |
| Web Portal (giao diện) | Giao diện quản lý cho người dùng | 8000 | *không có*  | —          |

**Giao diện web:** http://127.0.0.1:8000/ (cần đăng nhập). Web Portal không có database riêng, nó chỉ gọi REST API của các service.

## 2. Kiến trúc SOA

```
          Trình duyệt ──► Web Portal :8000 (Django template + Bootstrap 5)
                                 │  1) đăng nhập  ─────────────────────────► Identity Service :8004
                                 │                ◄── access + refresh JWT ─  (auth_db, giữ KHÓA BÍ MẬT)
                                 │  2) gọi API kèm  Authorization: Bearer <access token>
             ┌───────────────────┼─────────────────────────┐
             │   (hoặc Swagger UI / Postman / curl)        │
             ▼                   ▼                         ▼
  ┌──────────────────┐   ┌──────────────────┐   ┌─────────────────────────┐
  │ Student Service  │   │  Thesis Service  │   │  Registration Service   │
  │   :8001          │   │   :8002          │   │   :8003                 │
  │ /api/students/   │   │ /api/theses/     │   │ /api/registrations/     │
  └────────┬─────────┘   └────────┬─────────┘   └──┬───────────┬──────────┘
           │                      │                │           │
           │   ◄── HTTP GET /api/students/{id}/ ───┘ (chuyển tiếp token)
           │                      │   ◄── HTTP GET /api/theses/{id}/
           ▼                      ▼                            ▼
      student_db             thesis_db                 registration_db

  Student / Thesis / Registration tự xác minh chữ ký JWT bằng KHÓA CÔNG KHAI
  (identity-service/keys/jwt_public.pem) - offline: xác minh tại chỗ; online: kiểm tra thêm Identity.
```

- Mỗi service là **một Django project riêng**, chạy **một process riêng**, trên **một port riêng**.
- Mỗi service **chỉ kết nối database của chính nó**.
- Registration Service **không có ForeignKey** tới Student/Thesis: bảng `dangky` chỉ lưu `student_id`, `thesis_id` (số nguyên). Muốn biết sinh viên/đề tài có tồn tại hay không thì **gọi REST API** của service tương ứng.
- **Xác thực thống nhất giữa các service:** Identity Service ký JWT bằng thuật toán **RS256** (khóa bí mật). Mỗi service còn lại chỉ giữ **khóa công khai** để kiểm tra chữ ký, hạn dùng, issuer. Một service bị lộ cấu hình cũng không tự tạo được token giả.

## 3. Công nghệ sử dụng

- Python 3.14 (phiên bản của môi trường `.venv` hiện tại)
- Django 6.1, Django REST Framework
- Microsoft SQL Server (instance `.\MSSQLSERVER01`, Windows Authentication) qua `mssql-django` + `pyodbc`
- ODBC Driver 17 for SQL Server
- `requests` — Registration Service và Web Portal dùng để gọi HTTP sang các service khác
- `PyJWT` + `cryptography` — tạo / xác minh JWT RS256 (đã có sẵn trong `.venv`, không cài thêm thư viện mới)
- `drf-spectacular` — sinh tài liệu OpenAPI + Swagger UI (có nút **Authorize** để dán token)
- `python-dotenv` — đọc cấu hình từ file `.env`

## 4. Cấu trúc project

```
SOA_GK/
├── README.md
├── student-service/                  # Port 8001 - student_db
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── config/                       # settings.py, urls.py (Swagger tại /api/docs/)
│   │   ├── registration_api.py       # ★ Hỏi Registration Service trước khi xóa (giống ở thesis-service)
│   │   ├── jwt_auth.py               # ★ Xác minh JWT bằng khóa công khai (giống nhau ở 3 service)
│   │   ├── permissions.py            # ★ Phân quyền theo vai trò ADMIN / LECTURER / STUDENT
│   │   └── testing.py                # Tạo token giả lập cho test
│   └── students/
│       ├── models.py                 # Model Student (bảng sinhvien)
│       ├── serializers.py            # Validation
│       ├── views.py                  # ListCreateAPIView, RetrieveUpdateDestroyAPIView
│       ├── urls.py
│       ├── admin.py
│       ├── tests.py
│       └── management/commands/seed_data.py
│
├── thesis-service/                   # Port 8002 - thesis_db
│   └── theses/  (cấu trúc giống students/)
│
├── identity-service/                 # Port 8004 - auth_db (MỚI)
│   ├── .env.example                  # đường dẫn khóa JWT, thời hạn token, số lần đăng nhập sai
│   ├── keys/                         # jwt_private.pem / jwt_public.pem (tự tạo, KHÔNG commit)
│   └── accounts/
│       ├── models.py                 # User (role, student_id, khóa tạm), RefreshToken, AuditLog
│       ├── tokens.py                 # Tạo / kiểm tra JWT RS256
│       ├── authentication.py         # Xác thực Bearer token (tra lại tài khoản trong auth_db)
│       ├── views.py                  # login, refresh, logout, change-password, me, users (ADMIN)
│       ├── tests.py
│       └── management/commands/      # generate_jwt_keys, seed_users, issue_service_token
│
├── registration-service/             # Port 8003 - registration_db
│   ├── .env.example                  # có thêm STUDENT_SERVICE_URL, THESIS_SERVICE_URL
│   └── registrations/
│       ├── models.py                 # Registration (student_id, thesis_id KHÔNG phải ForeignKey),
│       │                             # RegistrationPeriod (đợt), RegistrationLock (khóa), ProgressNote (tiến độ)
│       ├── serializers.py
│       ├── views.py                  # Luồng nghiệp vụ đăng ký, hủy, đợt đăng ký, tiến độ
│       ├── urls.py
│       ├── services/
│       │   └── external_api.py       # ★ Toàn bộ code gọi HTTP sang Student/Thesis Service
│       ├── tests.py                  # Mock HTTP bằng unittest.mock
│       └── management/commands/seed_data.py   # tạo cả đợt đăng ký mẫu
│   └── scripts/concurrency_test.py   # Thử N đăng ký đồng thời vào đề tài 1 chỗ (chạy với SQL Server thật)
│
├── web-portal/                       # Port 8000 - giao diện web, KHÔNG có database
│   ├── .env.example                  # URL của các service
│   └── portal/
│       ├── auth.py                   # Bắt buộc đăng nhập, lưu token trong session cookie đã ký
│       ├── api_client.py             # Gọi REST API của các service, gửi kèm token, tự làm mới token
│       ├── forms.py                  # Form Django (thêm/sửa sinh viên, đề tài, đăng ký)
│       ├── views.py                  # Dashboard, Sinh viên, Đề tài, Đăng ký, API Docs
│       ├── urls.py
│       ├── templates/portal/         # Bootstrap 5: base.html, *_list.html, *_form.html
│       └── tests.py
│
└── run_all.bat                       # Mở 5 cửa sổ chạy 5 process cùng lúc
```

## 5. Cấu hình SQL Server

Các service kết nối SQL Server tại instance `.\MSSQLSERVER01` bằng Windows Authentication (giá trị mặc định trong `config/settings.py`). Cài SQL Server và ODBC Driver 17 for SQL Server, bảo đảm dịch vụ SQL Server của instance đó đang chạy.

Nếu máy dùng instance khác (ví dụ `.\SQLEXPRESS`), **không cần sửa code**: tạo file `.env` và đặt `DB_HOST`.

```powershell
copy student-service\.env.example       student-service\.env
copy thesis-service\.env.example        thesis-service\.env
copy registration-service\.env.example  registration-service\.env
copy identity-service\.env.example      identity-service\.env
copy web-portal\.env.example            web-portal\.env
```

Các biến dùng được: `DB_NAME`, `DB_HOST`, `DB_PORT`, `DB_DRIVER`, `SECRET_KEY`, `DEBUG`, `JWT_PUBLIC_KEY_PATH` và các URL service. Không có file `.env` thì mọi service vẫn chạy với giá trị mặc định như trước.

## 6. Tạo database SQL Server

Tạo 4 database riêng. Mở **SQL Server Management Studio (SSMS)**, kết nối tới `.\MSSQLSERVER01` bằng **Windows Authentication**, chọn **New Query** rồi chạy (3 database đầu đã có thì bỏ qua):

```sql
CREATE DATABASE student_db;
CREATE DATABASE thesis_db;
CREATE DATABASE registration_db;
CREATE DATABASE auth_db;   -- mới: cho Identity Service
```

## 7. Cài requirements

Dùng một virtualenv chung ở thư mục gốc (mỗi service vẫn có `requirements.txt` riêng):

```powershell
# Thực hiện các lệnh sau tại thư mục gốc SOA_GK
python -m venv .venv
.venv\Scripts\activate
pip install -r student-service\requirements.txt -r thesis-service\requirements.txt -r registration-service\requirements.txt -r identity-service\requirements.txt -r web-portal\requirements.txt
```

> `.venv` hiện tại đã có đủ thư viện (kể cả PyJWT và cryptography), lệnh trên chỉ cần khi cài trên máy mới.
> Nếu PowerShell chặn `activate`: chạy `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` một lần.

Tạo bảng (migrate) cho từng service:

```powershell
cd student-service;      python manage.py migrate; cd ..
cd thesis-service;       python manage.py migrate; cd ..
cd registration-service; python manage.py migrate; cd ..
cd identity-service;     python manage.py migrate; cd ..
```

### Tạo khóa JWT và tài khoản mẫu (chỉ làm 1 lần)

```powershell
cd identity-service
python manage.py generate_jwt_keys      # tạo keys\jwt_private.pem + keys\jwt_public.pem
python manage.py seed_users             # tạo tài khoản mẫu (bảng bên dưới): admin=1, gv.tuan=2, gv.ha=3
python manage.py issue_service_token registration-service
cd ..
```

Lệnh cuối in ra một token cho `seed_data` của Registration Service (lệnh này chạy khi không có ai đăng nhập). Token phải nằm trong file **`registration-service\.env`** — nếu chưa có file này thì tạo mới (có thể copy từ `.env.example`). Cách nhanh, ghi thẳng token vào `.env` (chạy trong `identity-service`):

```powershell
python manage.py issue_service_token registration-service 2>$null | ForEach-Object { "SERVICE_TOKEN=$_" } | Add-Content ..\registration-service\.env
```

> Token có hạn 30 ngày. Nếu chạy lại `generate_jwt_keys` (đổi khóa) thì phải cấp token mới. `seed_data` báo `Student Service rejected the credentials` nghĩa là token thiếu / sai / hết hạn.

| Tài khoản | Mật khẩu (demo) | Vai trò | Ghi chú |
| --------- | --------------- | ------- | ------- |
| `admin` | `Admin@2026` | ADMIN | Quản trị |
| `gv.tuan`, `gv.ha` | `GiangVien@2026` | LECTURER | Giảng viên |
| `sv001`, `sv002`, `sv003` | `SinhVien@2026` | STUDENT | Gắn với sinh viên id 1, 2, 3 |

> Có thể đăng nhập bằng username **hoặc email**. Đổi mật khẩu sau khi demo.
>
> `seed_data` của Thesis Service gán GVHD theo id tài khoản: TS. Phạm Minh Tuấn → 2 (`gv.tuan`), ThS. Hoàng Thu Hà → 3 (`gv.ha`). Nếu id khác (xem ở trang **Tài khoản** của Admin), chạy lại: `python manage.py seed_data --supervisor "TS. Phạm Minh Tuấn=<id>" --supervisor "ThS. Hoàng Thu Hà=<id>"`.

## 8. Chạy từng service

**Cách nhanh:** bấm đúp file `run_all.bat`. File này mở 5 cửa sổ, mỗi cửa sổ chạy một service. Sau đó mở http://127.0.0.1:8000/ và đăng nhập.

**Cách thủ công:** mở 5 cửa sổ terminal (đã `activate` venv ở mỗi cửa sổ):

```powershell
# Terminal 1
cd student-service
python manage.py runserver 8001

# Terminal 2
cd thesis-service
python manage.py runserver 8002

# Terminal 3
cd registration-service
python manage.py runserver 8003

# Terminal 4 - đăng nhập / cấp JWT
cd identity-service
python manage.py runserver 8004

# Terminal 5 - giao diện web
cd web-portal
python manage.py runserver 8000
```

Tạo dữ liệu mẫu (mở thêm một terminal, **sau khi các service đang chạy**):

```powershell
cd student-service;      python manage.py seed_data; cd ..
cd thesis-service;       python manage.py seed_data; cd ..
cd registration-service; python manage.py seed_data; cd ..
```

> `seed_data` của Registration Service cũng **lấy id sinh viên/đề tài qua REST API** (kèm `SERVICE_TOKEN`), nên phải chạy 2 service kia trước. Chạy `seed_data` nhiều lần không bị trùng dữ liệu.

Dữ liệu mẫu:

| Sinh viên                     | Đề tài                                                       |
| ----------------------------- | ------------------------------------------------------------ |
| id=1 SV001 - Nguyễn Văn An    | id=1 DT001 - Hệ thống quản lý thư viện (OPEN, tối đa 3)      |
| id=2 SV002 - Trần Văn Bình    | id=2 DT002 - Hệ thống đặt sân thể thao (OPEN, tối đa 1)      |
| id=3 SV003 - Lê Văn Cường     | id=3 DT003 - Hệ thống quản lý đồ án tốt nghiệp (**CLOSED**)  |
| id=4 SV004 - Phạm Thị Dung (chưa đăng ký đề tài nào) |                                    |

| Đăng ký | Sinh viên | Đề tài | Trạng thái |
| ------- | --------- | ------ | ---------- |
| 1       | SV001     | DT001  | APPROVED   |
| 2       | SV002     | DT001  | PENDING    |
| 3       | SV003     | DT002  | APPROVED   |

Đợt đăng ký mẫu: **"Đợt 1 - HK1 2026-2027"**, mở từ lúc chạy `seed_data` của Registration Service, kéo dài 60 ngày, mỗi sinh viên tối đa **1** đăng ký còn hiệu lực. Hết hạn thì Admin tạo đợt mới ở trang **Đợt đăng ký**.

Chạy test (không cần chạy service — HTTP được mock, token được ký bằng khóa tạm sinh ra khi test; Django tự tạo database test tạm):

```powershell
cd student-service;      python manage.py test; cd ..
cd thesis-service;       python manage.py test; cd ..
cd registration-service; python manage.py test; cd ..
cd identity-service;     python manage.py test; cd ..
cd web-portal;           python manage.py test; cd ..
```

### Giao diện web (Web Portal — http://127.0.0.1:8000/)

| Menu       | Chức năng                                                                 |
| ---------- | ------------------------------------------------------------------------- |
| Đăng nhập  | `/dang-nhap/` — username hoặc email + mật khẩu; sai 5 lần bị khóa 15 phút   |
| Thanh trên | Tên + vai trò người đăng nhập, **Đổi mật khẩu**, **Đăng xuất**            |
| Dashboard  | Tổng số sinh viên, đề tài, đề tài đang mở, đăng ký; bảng "Đề tài gần đây" |
| Sinh viên  | Danh sách, tìm kiếm, thêm, sửa, xóa                                       |
| Đề tài     | Danh sách (kèm số đã đăng ký / tối đa), tìm kiếm, thêm, sửa, xóa          |
| Đăng ký    | Danh sách, lọc theo sinh viên/đề tài/trạng thái, đăng ký mới, duyệt, từ chối (kèm lý do), hủy, xóa; trang **Chi tiết** có nhận xét / tiến độ |
| Đợt đăng ký | (Admin) `/dot-dang-ky/` — thêm, sửa, bật/tắt, xóa đợt đăng ký            |
| API Docs   | Trạng thái 4 service (hoạt động / không) và link Swagger của từng service |

Web Portal **không có database**. Mọi trang đều gọi REST API của các service (`portal/api_client.py`), kèm access token của người đang đăng nhập. Token nằm trong session cookie **đã ký, HttpOnly**; khi access token hết hạn (15 phút) portal tự xin token mới bằng refresh token, hết hạn refresh (24 giờ) thì chuyển về trang đăng nhập. Ví dụ bảng Đăng ký: lấy danh sách đăng ký từ Registration Service, sau đó lấy tên sinh viên từ Student Service và tên đề tài từ Thesis Service rồi ghép lại để hiển thị. Nếu một service bị tắt, trang vẫn mở được và hiện thông báo "... Service không hoạt động".

## 9. Danh sách API

> Tất cả API bên dưới (trừ đăng nhập / làm mới token) đều cần header `Authorization: Bearer <access token>`.
> Thiếu token, token sai hoặc hết hạn → `401` với `{"detail": "...", "code": "not_authenticated | token_invalid | token_expired"}`.

### Identity Service — `http://127.0.0.1:8004`

| Method | URL                            | Mô tả                                              |
| ------ | ------------------------------ | -------------------------------------------------- |
| POST   | `/api/auth/login/`             | Đăng nhập `{"username": "admin", "password": "..."}` (username hoặc email) |
| POST   | `/api/auth/refresh/`           | Đổi refresh token lấy cặp token mới (token cũ bị thu hồi) |
| POST   | `/api/auth/logout/`            | Thu hồi refresh token (`{"refresh": "..."}` hoặc `{"all_devices": true}`) |
| POST   | `/api/auth/change-password/`   | Đổi mật khẩu, thu hồi mọi phiên cũ, trả cặp token mới |
| GET/PATCH | `/api/auth/me/`             | Hồ sơ của mình (chỉ sửa `email`, `full_name`; **không** sửa được `role`) |
| GET/POST | `/api/users/`                | Danh sách / tạo tài khoản — **chỉ ADMIN** (`?role=`, `?search=`) |
| GET/PUT/PATCH/DELETE | `/api/users/{id}/` | Quản lý tài khoản — **chỉ ADMIN**              |
| POST   | `/api/users/{id}/unlock/`      | Mở khóa tài khoản bị khóa tạm — **chỉ ADMIN**      |
| GET    | `/api/audit-logs/`             | Nhật ký đăng nhập / quản trị — **chỉ ADMIN**       |

Lỗi đăng nhập: `401 invalid_credentials` (sai username/mật khẩu), `403 account_locked` (sai quá 5 lần, khóa 15 phút), `403 account_disabled`, `429` (gọi quá 10 lần/phút).

### Student Service — `http://127.0.0.1:8001`

| Method | URL                           | Mô tả                    |
| ------ | ----------------------------- | ------------------------ |
| GET    | `/api/students/`              | Danh sách sinh viên      |
| GET    | `/api/students/?search=Nguyen`| Tìm kiếm (có/không dấu)  |
| POST   | `/api/students/`              | Tạo sinh viên            |
| GET    | `/api/students/{id}/`         | Chi tiết                 |
| PUT    | `/api/students/{id}/`         | Cập nhật toàn bộ         |
| PATCH  | `/api/students/{id}/`         | Cập nhật một phần        |
| DELETE | `/api/students/{id}/`         | Xóa (★ hỏi Registration Service trước) |

Validation: `student_code` bắt buộc + unique, `full_name` bắt buộc, `email` hợp lệ.
Xóa sinh viên còn đăng ký PENDING/APPROVED → `409 {"error": "Student has active registrations"}`; Registration Service tắt → `503 {"error": "Registration Service unavailable"}` (không xóa).

### Thesis Service — `http://127.0.0.1:8002`

| Method | URL                         | Mô tả                    |
| ------ | --------------------------- | ------------------------ |
| GET    | `/api/theses/`              | Danh sách đề tài         |
| GET    | `/api/theses/?search=web`   | Tìm kiếm                 |
| GET    | `/api/theses/?supervisor_id=2` | Đề tài do giảng viên id=2 hướng dẫn (Registration Service dùng để phân quyền) |
| POST   | `/api/theses/`              | Tạo đề tài               |
| GET    | `/api/theses/{id}/`         | Chi tiết                 |
| PUT    | `/api/theses/{id}/`         | Cập nhật toàn bộ         |
| PATCH  | `/api/theses/{id}/`         | Cập nhật một phần        |
| DELETE | `/api/theses/{id}/`         | Xóa (★ hỏi Registration Service trước) |

Validation: `thesis_code` unique, `title` bắt buộc, `max_students > 0`. `status` là `OPEN` (mặc định) hoặc `CLOSED`.
Giảm `max_students` xuống dưới số đăng ký còn hiệu lực → `400 {"max_students": ["Cannot be lower than the number of active registrations (N)."]}`; xóa đề tài còn đăng ký → `409 {"error": "Thesis has active registrations"}`.
`supervisor_id`: id tài khoản giảng viên bên Identity Service (không phải ForeignKey). Giảng viên tạo đề tài thì tự động là GVHD; chỉ ADMIN đổi được GVHD.

### Registration Service — `http://127.0.0.1:8003`

| Method | URL                                   | Mô tả                                         |
| ------ | ------------------------------------- | --------------------------------------------- |
| GET    | `/api/registrations/`                 | Danh sách đăng ký                             |
| GET    | `/api/registrations/?student_id=1`    | Lọc theo sinh viên                            |
| GET    | `/api/registrations/?thesis_id=1`     | Lọc theo đề tài                               |
| GET    | `/api/registrations/?status=APPROVED` | Lọc theo trạng thái                           |
| GET    | `/api/registrations/?active=true`     | Chỉ đăng ký còn hiệu lực (PENDING + APPROVED) |
| GET    | `/api/registrations/?period_id=1`     | Lọc theo đợt                                  |
| POST   | `/api/registrations/`                 | Đăng ký (★ gọi Student + Thesis Service)      |
| GET    | `/api/registrations/{id}/`            | Chi tiết                                      |
| PUT    | `/api/registrations/{id}/`            | Đổi trạng thái `{"status": "APPROVED"}`       |
| PATCH  | `/api/registrations/{id}/`            | Từ chối `{"status": "REJECTED", "reject_reason": "..."}` |
| POST   | `/api/registrations/{id}/cancel/`     | **Hủy** đăng ký (giữ lịch sử, `CANCELLED`)    |
| DELETE | `/api/registrations/{id}/`            | Xóa hẳn bản ghi — **chỉ ADMIN**               |
| GET    | `/api/registrations/{id}/notes/`      | Nhận xét / tiến độ                            |
| POST   | `/api/registrations/{id}/notes/`      | Ghi tiến độ `{"content": "...", "progress": 40}` (GVHD / ADMIN, đăng ký đã duyệt) |
| GET    | `/api/periods/`                       | Danh sách đợt đăng ký                         |
| GET    | `/api/periods/current/`               | Đợt đang mở (`404` nếu không có)              |
| POST/PATCH/DELETE | `/api/periods/` , `/api/periods/{id}/` | Quản lý đợt — **chỉ ADMIN**    |

`status`: `PENDING` (mặc định khi tạo), `APPROVED`, `REJECTED`, `CANCELLED`. Sau khi tạo, chỉ được đổi `status`; muốn đổi đề tài thì hủy rồi đăng ký lại. Chi tiết quy trình ở mục 13a.
Kết quả của GET luôn **giới hạn theo người gọi**: sinh viên chỉ thấy đăng ký của mình, giảng viên chỉ thấy đăng ký vào đề tài mình hướng dẫn (xem mục 13).

## 10. Swagger URL

| Service              | Swagger UI                         |
| -------------------- | ---------------------------------- |
| Student Service      | http://127.0.0.1:8001/api/docs/    |
| Thesis Service       | http://127.0.0.1:8002/api/docs/    |
| Registration Service | http://127.0.0.1:8003/api/docs/    |
| Identity Service     | http://127.0.0.1:8004/api/docs/    |

(File OpenAPI dạng YAML: `/api/schema/`.)

Cách dùng:
1. Mở Swagger 8004 → `POST /api/auth/login/` → **Try it out** → `{"username": "admin", "password": "Admin@2026"}` → **Execute** → copy giá trị `access`.
2. Ở Swagger của service cần gọi (8001/8002/8003) bấm **Authorize** (góc phải) → dán access token → **Authorize**.
3. Mở API → **Try it out** → nhập body → **Execute**. Access token hết hạn sau 15 phút: đăng nhập lại hoặc gọi `/api/auth/refresh/`.

## 11. Demo CRUD

> Trước khi demo: đăng nhập lấy token và **Authorize** trong Swagger (mục 10). Thử gọi một API khi chưa Authorize để thấy `401`.

**1. Tạo sinh viên** — Swagger 8001 → `POST /api/students/`:

```json
{
  "student_code": "SV005",
  "full_name": "Hoàng Văn Em",
  "email": "em.hoang@student.edu.vn",
  "class_name": "CNTT2",
  "major": "Công nghệ thông tin"
}
```
→ `201 Created`, ghi lại `id` (ví dụ `5`).

Thử lỗi validation (trùng mã, email sai):
```json
{ "student_code": "SV001", "full_name": "Test", "email": "abc" }
```
→ `400` `{"student_code": ["student with this student code already exists."], "email": ["Enter a valid email address."]}`

**2. Tìm kiếm** — `GET /api/students/?search=Nguyen` → tìm sinh viên theo từ khóa.

**3. Sửa / xóa** — `PATCH /api/students/5/` với `{"class_name": "CNTT3"}`; `DELETE /api/students/5/` → `204`.
Thử xóa sinh viên đang có đăng ký: `DELETE /api/students/1/` → `409 {"error": "Student has active registrations"}` (Student Service đã hỏi Registration Service).

**4. Tạo đề tài** — Swagger 8002 → `POST /api/theses/`:

```json
{
  "thesis_code": "DT004",
  "title": "Ứng dụng web bán hàng",
  "description": "Website thương mại điện tử",
  "supervisor": "TS. Phạm Minh Tuấn",
  "max_students": 2
}
```
→ `201`, `status` mặc định `OPEN`. Thử `"max_students": 0` → `400`.

## 12. Demo Registration Service gọi Student/Thesis Service

Mở Swagger 8003 (đã **Authorize**) → `POST /api/registrations/`. Registration Service **chuyển tiếp chính access token của người dùng** khi gọi Student/Thesis Service. Đặt 3 cửa sổ terminal cạnh nhau để giảng viên thấy **log request xuất hiện ở terminal 8001 và 8002** mỗi lần gọi API đăng ký.

Luồng xử lý khi gọi `POST /api/registrations/` với `{"student_id": 4, "thesis_id": 1}`:

```
Client ── POST /api/registrations/ ──► Registration Service (8003)
                                            │
     Có đợt đang mở? Đăng ký trùng?         │
                                            │ Bước 1: GET http://127.0.0.1:8001/api/students/4/
                                            ├──────────────────────────────► Student Service
                                            │ ◄────────── 200 {...} / 404
                                            │ Bước 2: GET http://127.0.0.1:8002/api/theses/1/
                                            ├──────────────────────────────► Thesis Service
                                            │ ◄────────── 200 {"status": "OPEN", "max_students": 3, ...}
                                            │ Bước 3: thesis.status == "OPEN" ?
                                            │ ── transaction + khóa dòng (chống đăng ký đồng thời) ──
                                            │ Bước 4: số đăng ký PENDING+APPROVED của thesis < max_students ?
                                            │         số đăng ký còn hiệu lực của sinh viên < giới hạn của đợt ?
                                            │ Bước 5: lưu vào registration_db (kèm đợt đăng ký)
Client ◄── 201 Created ─────────────────────┘
```

Kịch bản demo với dữ liệu mẫu:

| # | Body                                   | Kết quả mong đợi                                                       |
| - | -------------------------------------- | ---------------------------------------------------------------------- |
| 1 | `{"student_id": 3, "thesis_id": 1}`    | `400` `{"error": "Student already has an active registration"}` (SV003 đã có đăng ký DT002, mỗi SV tối đa 1) |
| 2 | `{"student_id": 4, "thesis_id": 1}`    | `201` — đăng ký thành công, `status: PENDING` (DT001 giờ đủ 3/3)       |
| 3 | `{"student_id": 1, "thesis_id": 1}`    | `400` `{"error": "Student has already registered for this thesis"}`    |
| 4 | `{"student_id": 999, "thesis_id": 1}`  | `400` `{"error": "Student does not exist"}`                            |
| 5 | `{"student_id": 1, "thesis_id": 999}`  | `400` `{"error": "Thesis does not exist"}`                             |
| 6 | `{"student_id": 1, "thesis_id": 3}`    | `400` `{"error": "Thesis is closed"}`                                  |
| 7 | `{"student_id": 1, "thesis_id": 2}`    | `400` `{"error": "Thesis has reached maximum students"}` (DT002 tối đa 1) |
| 8 | Tắt Student Service (Ctrl+C ở terminal 8001), gửi `{"student_id": 2, "thesis_id": 2}` | `503` `{"error": "Student Service unavailable"}` (bật lại 8001 sau khi demo) |
| 9 | Admin tắt đợt đăng ký (trang **Đợt đăng ký** → Tắt), gửi `{"student_id": 2, "thesis_id": 2}` | `400` `{"error": "Registration period is closed"}` (bật lại sau khi demo) |

Sau đó:
- Duyệt đăng ký: `PATCH /api/registrations/2/` với `{"status": "APPROVED"}`.
- Lọc: `GET /api/registrations/?thesis_id=1`, `?student_id=1`, `?status=APPROVED`.

**Demo "đổi bên trong, giữ API":** đóng đề tài ở Thesis Service bằng `PATCH http://127.0.0.1:8002/api/theses/1/` `{"status": "CLOSED"}` → đăng ký mới vào đề tài 1 lập tức bị từ chối `Thesis is closed`, mà Registration Service không hề đọc `thesis_db`.

## 13. Phân quyền Admin – Giảng viên – Sinh viên

Vai trò (`role`) nằm trong JWT do Identity Service ký → người dùng **không tự đổi được** (sửa token là hỏng chữ ký). Mỗi service **tự kiểm tra quyền ở backend** (`config/permissions.py` + `get_queryset` của từng view); giao diện chỉ ẩn nút cho dễ dùng.

| Chức năng | Admin | Giảng viên | Sinh viên | Service token |
| --- | --- | --- | --- | --- |
| Sinh viên: xem | Tất cả | Tất cả (chỉ đọc) | **Chỉ chính mình** (người khác → 404) | Xem |
| Sinh viên: thêm / sửa / xóa | ✅ | ❌ 403 | ❌ 403 | ❌ |
| Đề tài: xem | Tất cả | Tất cả | Danh sách chỉ **OPEN** | Xem |
| Đề tài: thêm | ✅ (chọn GVHD) | ✅ (tự là GVHD) | ❌ | ❌ |
| Đề tài: sửa / xóa | ✅ | **Chỉ đề tài mình hướng dẫn** | ❌ | ❌ |
| Đăng ký: xem | Tất cả | **Đăng ký vào đề tài mình** | **Của mình** | Xem |
| Đăng ký: tạo | ✅ (đăng ký hộ) | ❌ | **Chỉ cho chính mình** | ❌ |
| Đăng ký: duyệt / từ chối | ✅ | **Chỉ đề tài mình** (khác → 404) | ❌ | ❌ |
| Đăng ký: hủy (`/cancel/`) | PENDING / APPROVED | ❌ | Của mình, **khi còn PENDING** và đợt đang mở | ❌ |
| Đăng ký: xóa hẳn | ✅ | ❌ | ❌ | ❌ |
| Nhận xét / tiến độ | Xem + ghi | Xem + ghi (đề tài mình, đã duyệt) | Xem của mình | Xem |
| Đợt đăng ký | Thêm / sửa / tắt / xóa | Xem | Xem | Xem |
| Tài khoản (Identity) | ✅ tạo, khóa, mở khóa | ❌ | ❌ | ❌ |
| Hồ sơ đăng nhập `/api/auth/me/` | Sửa email, họ tên (không sửa role) | như Admin | như Admin | ❌ |

**SOA khi phân quyền giảng viên:** Registration Service không biết đề tài nào của ai. Khi giảng viên xem/duyệt đăng ký, nó gọi `GET /api/theses/?supervisor_id=<id>` sang Thesis Service (kèm token của giảng viên) rồi chỉ trả các đăng ký thuộc những đề tài đó. Thesis Service tắt → `503`.

**Kịch bản demo phân quyền** (đăng nhập ở http://127.0.0.1:8000 bằng từng tài khoản):

| # | Tài khoản | Thao tác | Kết quả |
| - | --------- | -------- | ------- |
| 1 | `sv003` | Menu chỉ có *Hồ sơ của tôi / Đề tài đang mở / Đăng ký của tôi*; bấm **Đăng ký** ở DT001 | Đăng ký cho chính mình, form không cho chọn sinh viên khác |
| 2 | `sv003` | Swagger 8003: `POST {"student_id": 2, "thesis_id": 1}` | `403 Students can only register for themselves` |
| 3 | `sv003` | Swagger 8001: `GET /api/students/1/` | `404` (không xem được sinh viên khác) |
| 4 | `gv.tuan` | Mục *Duyệt đăng ký* | Chỉ thấy đăng ký vào DT001, DT003; duyệt được |
| 5 | `gv.tuan` | Swagger 8003: `PATCH /api/registrations/3/` (đăng ký vào DT002 của GV Hà) | `404` |
| 6 | `gv.tuan` | Swagger 8002: `PATCH /api/theses/2/` | `403 You can only modify theses you supervise.` |
| 7 | `sv001` | Hủy đăng ký đã được duyệt (`POST /api/registrations/1/cancel/`) | `400 Only pending registrations can be cancelled` |
| 8 | `admin` | Mục *Tài khoản* → **Khóa tài khoản** `sv003`, rồi đăng nhập `sv003` | "Tài khoản đã bị vô hiệu hóa" |

## 13a. Quy trình đăng ký đề tài (đợt, hủy, từ chối, tiến độ)

Quy định nghiệp vụ (đã thống nhất với nhóm, đổi được trong đợt đăng ký):

| Quy định | Giá trị | Ở đâu |
| -------- | ------- | ----- |
| Chỉ đăng ký / sinh viên tự hủy khi có **đợt đang mở** | đợt `is_active` và trong khoảng `start_at` – `end_at` | bảng `dotdangky` |
| Số đăng ký **còn hiệu lực** (PENDING + APPROVED) tối đa / sinh viên | **1** | `max_active_per_student` của đợt |
| Chỉ tiêu đề tài tính cả PENDING lẫn APPROVED | REJECTED, CANCELLED không chiếm chỗ | `check_local_limits()` |
| Sinh viên tự hủy | chỉ khi còn **PENDING** | `RegistrationCancelView` |
| Từ chối | bắt buộc nhập **lý do** | `RegistrationUpdateSerializer` |

Vòng đời một đăng ký:

```
            duyệt                       hủy (Admin)
 PENDING ──────────► APPROVED ──────────────────────► CANCELLED
    │  ▲                │                                 ▲
    │  │ duyệt lại      │ từ chối (kèm lý do)             │
    │  └──── REJECTED ◄─┘                                 │
    └──── hủy (sinh viên khi còn PENDING / Admin) ────────┘
 Đăng ký lại sau khi CANCELLED / REJECTED: dùng lại đúng dòng cũ, trạng thái về PENDING.
```

- **Hủy** (`POST /cancel/`) không xóa dữ liệu: lưu `cancelled_by`, `cancelled_at` để còn lịch sử. Chỉ Admin mới **xóa hẳn** (dùng khi nhập nhầm).
- **Duyệt / từ chối** lưu `processed_by`, `processed_at`, `reject_reason`. Duyệt lại một đăng ký đã bị từ chối sẽ kiểm tra lại chỉ tiêu và giới hạn.
- **Tiến độ:** GVHD (hoặc Admin) ghi nhận xét + % hoàn thành cho đăng ký đã duyệt ở trang **Chi tiết** đăng ký (`/dang-ky/<id>/`); sinh viên xem được nhận xét của mình.

**Chống đăng ký đồng thời (vượt chỉ tiêu):** nếu 2 sinh viên bấm đăng ký vào chỗ cuối cùng cùng một lúc, cả hai có thể cùng đếm thấy "còn 1 chỗ". Registration Service đếm và lưu **trong một transaction**, sau khi khóa dòng `thesis:<id>` và `student:<id>` ở bảng `khoa_dangky` (`select_for_update()` → SQL Server `WITH (UPDLOCK, ROWLOCK)`), nên request thứ hai phải chờ request thứ nhất lưu xong rồi mới đếm. Các lời gọi HTTP sang Student/Thesis Service làm **trước** khi khóa để không giữ khóa lâu. Kiểm tra trên SQL Server thật (cần chạy 4 service):

```powershell
python registration-service\scripts\concurrency_test.py --students 10
```
→ đúng 1 request `201`, 9 request `400 Thesis has reached maximum students`, rồi script tự dọn dữ liệu tạm.

Dòng khóa được **tạo sẵn và commit trước** khi mở transaction, rồi mới khóa theo khóa chính (`RegistrationLock.ensure()` / `acquire()`); nếu tạo dòng khóa ngay trong transaction, các request song song chặn lẫn nhau và SQL Server báo **deadlock**. Nếu SQL Server vẫn báo deadlock, service tự thử lại 3 lần, sau đó trả `503 {"error": "Registration Service is busy, please try again"}` — không trả `500`.

**Đồng bộ giữa các service:** Student Service và Thesis Service không đọc `registration_db`; trước khi **xóa sinh viên / xóa đề tài / giảm `max_students`** chúng gọi `GET /api/registrations/?student_id=..&active=true` (hoặc `thesis_id`) sang Registration Service, kèm token của người đang thao tác (`config/registration_api.py`). Còn đăng ký hiệu lực → `409`; Registration Service tắt → `503`, **không xóa** (an toàn hơn để lại đăng ký trỏ tới dữ liệu đã mất).

**Nâng cấp database đang có** (không mất dữ liệu): dừng Registration Service rồi chạy

```powershell
cd registration-service
python manage.py migrate        # thêm bảng dotdangky, khoa_dangky, tiendo và các cột mới của dangky
python manage.py seed_data      # tạo đợt đăng ký mẫu nếu chưa có đợt nào (cần 8001, 8002 đang chạy)
cd ..\student-service
python manage.py seed_data      # thêm SV004
cd ..
pip install -r student-service\requirements.txt -r thesis-service\requirements.txt   # requests (đã có trong .venv)
```
Đăng ký cũ giữ nguyên trạng thái, cột `period` để trống. Thêm dòng `REGISTRATION_SERVICE_URL=http://127.0.0.1:8003` vào `.env` của student-service và thesis-service nếu đã đổi địa chỉ (mặc định đã đúng).

## 14. Giải thích: Tại sao đây là SOA?

1. **Mỗi service một trách nhiệm (độc lập về nghiệp vụ)**
   - Student Service chịu trách nhiệm quản lý sinh viên.
   - Thesis Service chịu trách nhiệm quản lý đề tài.
   - Registration Service chịu trách nhiệm quản lý đăng ký.

2. **Độc lập về triển khai và dữ liệu**
   - 3 Django project riêng, 3 process riêng, 3 port riêng (8001/8002/8003).
   - 3 database riêng. Registration Service **không** kết nối `student_db` hay `thesis_db` (xem `DATABASES` trong `registration-service/config/settings.py`).
   - `student_id`, `thesis_id` trong bảng `dangky` **không phải ForeignKey** — vì dữ liệu nằm ở database khác (`registrations/models.py`).

3. **Giao tiếp qua giao thức chuẩn HTTP/REST + JSON**
   - Registration Service chỉ biết **URL** của service khác (cấu hình trong `.env`), gọi bằng `requests.get(...)` trong `registrations/services/external_api.py`.
   - Mọi HTTP call đều có **timeout**; nếu service kia chết → trả `503 Service Unavailable` thay vì treo hoặc lỗi 500.

4. **Loose coupling — điểm quan trọng nhất**
   - Registration Service chỉ phụ thuộc vào **API contract** (`GET /api/students/{id}/` trả JSON có `id`; `GET /api/theses/{id}/` trả JSON có `status`, `max_students`).
   - Nếu thay đổi implementation bên trong Student Service (đổi tên bảng, đổi cách lưu, thêm cột, thậm chí viết lại bằng ngôn ngữ khác) **nhưng giữ nguyên API**, thì Registration Service **không cần sửa một dòng code nào**.
   - Nếu đổi địa chỉ server, chỉ cần sửa `STUDENT_SERVICE_URL` trong `.env`.

5. **Khả năng tái sử dụng**
   - `GET /api/students/{id}/` không được viết riêng cho Registration Service: bất kỳ hệ thống nào khác (chấm điểm, học phí, thư viện...) cũng dùng lại được Student Service qua cùng API.
   - Trong Registration Service, các hàm `get_student()`, `get_thesis()` trong `external_api.py` được tái sử dụng ở API tạo đăng ký, API cập nhật trạng thái và lệnh `seed_data`.
   - **Web Portal** là ví dụ thực tế cho việc tái sử dụng: giao diện web được thêm vào sau mà **không phải sửa một dòng code nào** của 3 service. Nó dùng lại đúng các API đã có, giống như Swagger hay Registration Service đang dùng.

6. **Bảo mật thống nhất giữa các service**
   - Chỉ Identity Service giữ mật khẩu (hash PBKDF2) và **khóa bí mật** để ký JWT.
   - Student / Thesis / Registration xác minh chữ ký bằng **khóa công khai**. Chế độ **offline** không gọi Identity nên token còn hạn vẫn dùng được khi Identity tắt. Chế độ **online** gọi thêm Identity để kiểm tra trạng thái tài khoản; Identity tắt thì API trả 503.
   - Đăng nhập ở một nơi, dùng được ở mọi service; nhưng **mỗi service tự kiểm tra token**, không mặc định tin nhau.

## Câu hỏi giảng viên hay hỏi — trả lời nhanh

| Câu hỏi | Trả lời / chỉ vào file |
| ------- | ---------------------- |
| Code gọi service khác nằm ở đâu? | `registration-service/registrations/services/external_api.py` |
| Luồng kiểm tra 5 bước ở đâu? | `check_remote_rules()` (gọi Student/Thesis Service) và `check_local_limits()` (đếm chỉ tiêu, giới hạn) trong `registrations/views.py` |
| Sao không dùng ForeignKey? | Student/Thesis ở database khác; DB không thể ràng buộc khóa ngoại xuyên database → kiểm tra bằng REST API |
| Chống đăng ký trùng thế nào? | Kiểm tra trong view + `UniqueConstraint(student_id, thesis_id)` ở database |
| Hai người đăng ký chỗ cuối cùng cùng lúc? | Transaction + khóa dòng ở bảng `khoa_dangky` (`RegistrationLock.acquire`); thử bằng `scripts/concurrency_test.py` |
| Xóa sinh viên đang có đăng ký thì sao? | Student Service hỏi Registration Service qua REST → `409`; không có ForeignKey nên phải kiểm tra bằng API |
| Service khác chết thì sao? | `requests` có timeout, bắt `RequestException` → `503 {"error": "... unavailable"}` |
| Test không cần chạy service khác? | Đúng — `tests.py` mock `requests.get` bằng `unittest.mock.patch` |
| Mật khẩu DB để đâu? | File `.env` (không commit), code đọc qua `os.getenv` |
| Đăng nhập ở đâu, token kiểm tra thế nào? | Identity Service (`identity-service/accounts/views.py`) ký JWT RS256; 3 service kiểm tra bằng khóa công khai trong `config/jwt_auth.py` |
| Mật khẩu lưu thế nào? | Hash PBKDF2 của Django (`set_password`), API không bao giờ trả trường `password` |
| Đăng xuất thì token có mất hiệu lực không? | Identity thu hồi access token hiện tại và refresh token được gửi kèm. Ba service nghiệp vụ chặn ngay khi chạy online; offline có thể tiếp tục chấp nhận access token tới khi hết hạn (mặc định 15 phút) |
| Đăng nhập sai nhiều lần? | Sai 5 lần → khóa 15 phút (`403 account_locked`); Admin mở khóa bằng `POST /api/users/{id}/unlock/` |
| Service gọi service khi không có người dùng? | Dùng token kỹ thuật role `SERVICE` (`issue_service_token`), đặt trong `.env` |
| Kiểm tra quyền ở đâu? | Backend: `config/permissions.py` (vai trò) + `get_queryset` (từng đối tượng) ở mỗi service; Portal chỉ ẩn nút |
| Sinh viên có tự nâng quyền thành Admin được không? | Không: role nằm trong JWT đã ký; API `/api/auth/me/` không cho sửa role; chỉ Admin sửa role qua `/api/users/` |
| Sao giảng viên xem đăng ký người khác lại ra 404 chứ không 403? | Đối tượng ngoài phạm vi bị lọc khỏi queryset → không lộ việc nó có tồn tại |


## Nâng cấp chấm điểm và bảo mật (27/10/2026)

Đã thêm module chấm điểm trong Registration Service, giao diện chấm điểm/hồ sơ/nhật ký, thu hồi access token và cấu hình production. Xem [UPGRADE_PHASE5_8.md](UPGRADE_PHASE5_8.md) để biết migration, API, ma trận quyền, cách chạy test và giới hạn chưa xác nhận trên SQL Server. Chạy `python scripts/migrate_all.py` bằng môi trường `.venv` trước khi dùng chức năng mới.


## Bản demo học SOA: cách chạy được khuyến nghị

Xem [DEMO_GUIDE.md](DEMO_GUIDE.md) cho bộ dữ liệu riêng, hai chế độ xác thực và sáu kịch bản bảo vệ.

- `python scripts/migrate_all.py`: kiểm tra đủ bốn kết nối SQL Server trước khi áp dụng migration; không đổi cấu hình database.
- `run_demo.bat offline`: xác minh JWT tại từng service; không gọi Identity ở mỗi request.
- `run_demo.bat online`: kiểm tra thêm trạng thái tài khoản; Identity ngừng hoạt động thì backend trả 503.
- `python scripts/prepare_demo.py`: tạo dữ liệu có tiền tố DEMO qua REST, không xóa dữ liệu hoặc đặt lại mật khẩu cũ.
- Trang API Docs chỉ hiển thị khả năng phản hồi HTTP của schema; dùng `python scripts/check_sql_server.py` để kiểm tra database.

Các lỗi hợp đồng JSON liên service được xử lý có kiểm soát, không cho phép xóa/giảm chỉ tiêu dựa trên phản hồi sai. Registration chỉ retry lỗi khóa tạm thời được nhận diện; lỗi database khác trả 500 có hướng dẫn kiểm tra migration/log, không bị đổi thành “service bận”.


## Tự sinh mã sinh viên và mã đề tài

Giao diện thêm mới không yêu cầu nhập mã: Student Service tự cấp SV001/SV002… và Thesis Service tự cấp DT001/DT002… Mã cũ được giữ nguyên, trang sửa hiển thị mã chỉ đọc. API vẫn nhận mã cung cấp rõ ràng để tương thích các công cụ seed; bỏ trường mã khi POST để dùng tự động.

Cần chạy `python scripts/migrate_all.py` bằng môi trường `.venv` và khởi động lại service sau cập nhật. Xem [AUTO_CODES.md](AUTO_CODES.md) để biết migration, quy tắc cấp mã và kiểm thử.
