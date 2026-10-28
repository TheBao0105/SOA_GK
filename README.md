# Hệ thống đăng ký đề tài sinh viên — Demo SOA

Django + Django REST Framework + SQL Server. Phạm vi: quản lý sinh viên, đề tài, đăng ký, duyệt/từ chối/hủy, tiến độ và điểm trực tiếp 0–10.

## Kiến trúc

| Thành phần | Port | Dữ liệu sở hữu | Trách nhiệm |
| --- | --- | --- | --- |
| Identity Service | 8004 | `auth_db` | Tài khoản, mật khẩu, JWT, thu hồi token, nhật ký |
| Student Service | 8001 | `student_db` | Sinh viên và mã SV tự động |
| Thesis Service | 8002 | `thesis_db` | Đề tài, GVHD, chỉ tiêu, mã DT tự động |
| Registration Service | 8003 | `registration_db` | Đăng ký, tiến độ, điểm và lịch sử điểm |
| Web Portal | 8000 | Không có database | Django Forms/Templates, gọi REST để hiển thị và thao tác |

Trình duyệt → Portal → REST API của bốn dịch vụ. Registration gọi Student/Thesis qua HTTP để kiểm tra nghiệp vụ. Student/Thesis gọi Registration để kiểm tra đăng ký hiệu lực trước khi xóa hoặc giảm chỉ tiêu. Chế độ online gọi Identity để kiểm tra trạng thái tài khoản.

- Mỗi service là một Django project, một process và chỉ kết nối database của mình.
- `student_id`, `thesis_id`, `supervisor_id` liên dịch vụ là ID tham chiếu; không import model hoặc JOIN database của dịch vụ khác.
- Khóa ngoại giữa đăng ký, tiến độ, điểm trong cùng Registration Service là hợp lệ.
- Identity giữ khóa bí mật RS256; ba dịch vụ nghiệp vụ chỉ xác minh bằng khóa công khai.
- Quyền vai trò và quyền trên từng đối tượng được kiểm tra tại API. Portal ẩn nút theo quyền để dễ sử dụng.
- Chấm điểm nằm cùng miền đăng ký; demo không cần tách thành service thứ năm hay thêm ESB/message broker.

## Thành phần Django

| Thành phần | Vai trò |
| --- | --- |
| Django ORM + migrations | Model, ràng buộc, nâng cấp schema, transaction và khóa dữ liệu |
| DRF | Serializer, API view, authentication, permission, HTTP response |
| drf-spectacular | OpenAPI và Swagger UI |
| Django Forms/Templates | Kiểm tra form, CSRF, giao diện Portal |
| Middleware | Bảo vệ phiên Portal, xử lý đăng nhập và lỗi quyền |
| requests | Gọi HTTP giữa các dịch vụ, có timeout |
| PyJWT + cryptography | Ký/xác minh JWT RS256 |
| mssql-django + pyodbc | Backend SQL Server và ODBC |
| python-dotenv | Cấu hình riêng từng service qua `.env` |

Giữ nguyên các file khung Django (`manage.py`, `apps.py`, `admin.py`, `models.py`, `tests.py`, `asgi.py`, `wsgi.py`, `__init__.py`) và lịch sử migrations hiện có. Django Admin chỉ mở tại Identity; ba dịch vụ nghiệp vụ thao tác qua REST để áp dụng đầy đủ quy tắc. Không tạo tài khoản đăng nhập riêng tại từng database nghiệp vụ.

## Cài trên máy mới

Chạy tại thư mục gốc dự án, đã cài Python phù hợp requirements, SQL Server và ODBC Driver 17 for SQL Server. Môi trường đã kiểm thử được ghi trong [constraints-tested.txt](constraints-tested.txt); `.venv` không được đưa lên Git.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r student-service\requirements.txt -r thesis-service\requirements.txt -r registration-service\requirements.txt -r identity-service\requirements.txt -r web-portal\requirements.txt
```

Chỉ copy `.env.example` khi chưa có `.env`, tránh ghi đè cấu hình đang dùng:

```powershell
Copy-Item student-service\.env.example student-service\.env
Copy-Item thesis-service\.env.example thesis-service\.env
Copy-Item registration-service\.env.example registration-service\.env
Copy-Item identity-service\.env.example identity-service\.env
Copy-Item web-portal\.env.example web-portal\.env
```

Sửa `DB_HOST` theo tên Server/Instance của máy nhận trong SSMS, ví dụ `.\MSSQLSERVER01` hoặc `.\SQLEXPRESS`. Dự án dùng Windows Authentication. Mỗi service có `DB_NAME` riêng. Với máy mới, tạo database trong SSMS:

```sql
CREATE DATABASE student_db;
CREATE DATABASE thesis_db;
CREATE DATABASE registration_db;
CREATE DATABASE auth_db;
```

Áp dụng migrations bằng cấu hình của chính máy đang chạy:

```powershell
.\.venv\Scripts\python.exe -B scripts\migrate_all.py
.\.venv\Scripts\python.exe -B identity-service\manage.py generate_jwt_keys
.\.venv\Scripts\python.exe -B identity-service\manage.py seed_users
.\run_demo.bat online
```

`generate_jwt_keys` dành cho lần cài đầu; không tạo lại khóa tùy tiện khi đã có hệ thống. Đường dẫn khóa tương đối tính từ từng service. Khi triển khai tách máy, phân phối khóa công khai cho các dịch vụ nghiệp vụ; chỉ Identity giữ khóa bí mật. `git pull` không sao chép `.env`, khóa, database hay tài khoản của máy gửi.

Sau khi năm service đã chạy, tạo bộ dữ liệu demo qua REST:

```powershell
.\.venv\Scripts\python.exe -B scripts\prepare_demo.py
```

Công cụ hỏi đăng nhập quản trị, tạo dữ liệu DEMO với ID thực tế, chạy lại không đặt lại mật khẩu tài khoản cũ. Xem [DEMO_GUIDE.md](DEMO_GUIDE.md) cho tài khoản/bộ dữ liệu và kịch bản chi tiết. Các lệnh `seed_data` cũ vẫn giữ để tương thích; seed Registration cần `SERVICE_TOKEN`, còn demo qua REST không cần cấu hình token kỹ thuật.

Tài khoản bootstrap do `seed_users` tạo trên database mới:

| Username | Mật khẩu demo | Vai trò |
| --- | --- | --- |
| `admin` | `Admin@2026` | ADMIN |
| `gv.tuan`, `gv.ha` | `GiangVien@2026` | LECTURER |
| `sv001`, `sv002`, `sv003` | `SinhVien@2026` | STUDENT |

Dữ liệu seed cũ giả định ID; để demo trên database đã có dữ liệu, ưu tiên `prepare_demo.py` vì nó liên kết ID thực tế. Mật khẩu trên chỉ dành cho dữ liệu demo mới; tài khoản đã đổi mật khẩu giữ mật khẩu đang có.

## Chạy và truy cập

- Portal: `http://127.0.0.1:8000/`.
- Swagger của mỗi API: `http://127.0.0.1:<port>/api/docs/`; schema: `/api/schema/`.
- `run_demo.bat online`: kiểm tra trạng thái tài khoản qua Identity; Identity tắt → 503.
- `run_demo.bat offline`: xác minh JWT tại chỗ; token còn hạn có thể tiếp tục dùng sau khi khóa tài khoản/đăng xuất.
- `run_all.bat`: chạy theo cấu hình `.env`; không tự áp dụng migration hay seed.

Đăng nhập tại Portal hoặc `POST http://127.0.0.1:8004/api/auth/login/`. Trong Swagger bấm Authorize và nhập access token. Các API nghiệp vụ yêu cầu `Authorization: Bearer <access>`.

| API chính | Chức năng |
| --- | --- |
| `/api/students/` | Danh sách/tạo; `/{id}/` chi tiết/sửa/xóa |
| `/api/theses/` | Danh sách/tạo; `/{id}/` chi tiết/sửa/xóa |
| `/api/registrations/` | Danh sách/tạo; `/{id}/` chi tiết/duyệt/từ chối/xóa |
| `/api/registrations/{id}/cancel/` | POST hủy |
| `/api/registrations/{id}/notes/` | GET/POST tiến độ |
| `/api/grading/grades/` | GET điểm; POST nhập hoặc sửa theo registration |
| `/api/grading/grades/{id}/` | GET chi tiết; DELETE xóa điểm hiện tại |
| `/api/grading/grades/{id}/history/` | GET lịch sử của đăng ký có điểm hiện tại, Admin/GVHD |
| `/api/auth/me/`, `/api/auth/refresh/`, `/api/auth/logout/` | Hồ sơ, làm mới token, đăng xuất tại Identity |
| `/api/users/`, `/api/audit-logs/` | Quản trị tài khoản/nhật ký tại Identity |

## Quy tắc và quyền

- Một sinh viên có tối đa một đăng ký PENDING/APPROVED. Hai trạng thái này chiếm chỉ tiêu; REJECTED/CANCELLED không chiếm chỗ.
- Sinh viên chỉ đăng ký/xem dữ liệu của mình, tự hủy khi PENDING. Giảng viên duyệt/từ chối, ghi tiến độ và chấm đề tài mình hướng dẫn. Admin quản lý toàn bộ.
- Từ chối cần lý do; đăng ký lại dùng lại cặp sinh viên–đề tài cũ. Có lịch sử chấm điểm thì không hủy/xóa đăng ký đó.
- Khóa đề tài và sinh viên trong Registration Service bảo vệ đếm/lưu đồng thời. HTTP kiểm tra liên dịch vụ diễn ra trước khi lấy khóa.
- Điểm 0–10, tối đa hai chữ số thập phân; lưu là sinh viên thấy ngay. Chi tiết/sửa/xóa có phân quyền; xóa điểm giữ lịch sử.
- Không còn đợt đăng ký, đợt chấm, tiêu chí, trọng số, phân công hội đồng hay công bố điểm. Giữ migration cũ để nâng cấp database đã có.
- Mã SV/DT tự sinh khi tạo; Portal không bắt nhập tay. Xem [AUTO_CODES.md](AUTO_CODES.md) và [GRADING_GUIDE.md](GRADING_GUIDE.md).

## Kiểm tra và xử lý lỗi

```powershell
.\.venv\Scripts\python.exe -B scripts\test_all.py --sqlite
.\.venv\Scripts\python.exe -B scripts\integration_smoke.py --auth-mode online
.\.venv\Scripts\python.exe -B scripts\integration_smoke.py --auth-mode offline
.\.venv\Scripts\python.exe -B scripts\check_sql_server.py
.\.venv\Scripts\python.exe -B scripts\test_all.py --sql-server
.\.venv\Scripts\python.exe -B registration-service\scripts\concurrency_test.py --students 10
```

SQLite kiểm tra logic và migration, không chứng minh cơ chế khóa SQL Server. Integration chạy năm process HTTP với database/khóa tạm, không dùng dữ liệu đang demo. Báo cáo ở `work/` và không commit. Chạy SQL Server test tạo database test tạm, cần quyền tạo/xóa database.

Lỗi đăng nhập trên máy khác: khởi động lại đủ năm service từ cùng bản code rồi chạy `scripts/check_login.py`. Công cụ hỏi mật khẩu ẩn, không in token. Kiểm tra issuer, khóa công khai, URL service và database đúng máy.

- 401: token/phiên hết hiệu lực; Portal thử refresh một lần rồi yêu cầu đăng nhập lại.
- 403: thiếu quyền; giữ phiên, không tự nâng quyền.
- 503/timeout: phụ thuộc tạm không dùng được; không thực hiện thao tác cần kiểm tra phụ thuộc đó. Refresh gặp 5xx/429 giữ phiên để thử lại.

Các giới hạn và nội dung rà soát: [SYSTEM_REVIEW.md](SYSTEM_REVIEW.md). Giải thích chi tiết luồng đăng ký đề tài và câu hỏi bảo vệ: [GIAI_THICH_DANG_KY.md](GIAI_THICH_DANG_KY.md). Cấu hình hiện tại dành cho demo local; HTTPS, secret riêng và quy trình vận hành cần được chuẩn bị khi triển khai thực tế.

## Đóng gói nộp bài

Không nén trực tiếp cả thư mục: `.gitignore` chỉ có tác dụng với Git, nên file nén tay sẽ kèm khóa bí mật JWT, `.env`, bản sao lưu và database tạm. Dùng script sau để tạo file zip sạch ở thư mục cha của dự án:

```powershell
.\.venv\Scripts\python.exe -B scripts\dong_goi_nop_bai.py
```
