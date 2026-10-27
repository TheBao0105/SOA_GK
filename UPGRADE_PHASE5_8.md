> Bản học SOA đã được thu gọn theo yêu cầu. Xem DEMO_GUIDE.md cho cách chạy hiện tại; các khuyến nghị production bên dưới không phải danh sách bắt buộc để demo.

# Nâng cấp giai đoạn 5–8: chấm điểm, giao diện, bảo mật và kiểm thử

Ngày kiểm tra: 27/10/2026. Mã nguồn được sửa trực tiếp trong `C:\Users\Admin\SOA_GK`.
Không đổi database SQL Server, cổng, tên service hoặc endpoint cũ. Không ghi đè `.env`, không đổi khóa JWT thật, không xóa dữ liệu hiện có.

## 1. Kiến trúc và phạm vi

```text
Trình duyệt -> Web Portal :8000
                 |-> Identity :8004 / auth_db
                 |-> Student :8001 / student_db
                 |-> Thesis :8002 / thesis_db
                 |-> Registration :8003 / registration_db
                       |-> registrations: đăng ký, đợt đăng ký, tiến độ
                       |-> grading: đợt chấm, phân công, điểm và lịch sử
```

Chọn module `grading` trong Registration Service vì hồ sơ chấm phụ thuộc trực tiếp đăng ký đã duyệt. Dùng ForeignKey nội bộ tới Registration; không truy cập database của Student/Thesis/Identity. Phân công giảng viên được xác minh qua REST của Identity. Chưa cần Notification Service vì đây là phần tùy chọn trong tài liệu.

## 2. Phần đã triển khai

- Đợt chấm có thời gian bắt đầu/kết thúc, bật/tắt, bộ tiêu chí và trọng số cấu hình được, tổng bằng 100%.
- Mẫu gợi ý trên giao diện là 40/30/20/10; Admin có thể thay đổi trước khi tạo hồ sơ chấm. Từ 1–30 tiêu chí; mã duy nhất; trọng số dương, tối đa hai chữ số thập phân.
- Chỉ đăng ký APPROVED được tạo hồ sơ; mỗi đăng ký có tối đa một hồ sơ trong cùng một đợt.
- Admin phân công một hoặc nhiều giảng viên; tài khoản phải tồn tại, đang hoạt động và có vai trò LECTURER.
- Giảng viên chỉ chấm hồ sơ được phân công, mỗi tiêu chí từ 0–10; lưu nháp hoặc nộp. Nộp phải đủ tiêu chí. Đã nộp không tự sửa được.
- Tính bằng Decimal: điểm mỗi giảng viên = tổng(điểm tiêu chí × trọng số / 100). Điểm cuối = trung bình các tổng chưa làm tròn, rồi làm tròn HALF_UP đến hai chữ số thập phân.
- Trạng thái: UNGRADED -> IN_PROGRESS -> GRADED -> PUBLISHED. Chỉ Admin công bố khi tất cả người được phân công đã nộp; thao tác công bố chính là xác nhận điểm cuối.
- Admin mở lại bằng lý do bắt buộc: thu hồi công bố, giữ điểm cũ và lịch sử, yêu cầu mọi giảng viên nộp lại. Nếu đã hết đợt, Admin phải gia hạn/mở đợt để giảng viên sửa.
- Sinh viên chỉ xem hồ sơ của mình sau công bố. Hồ sơ chưa công bố hoặc ngoài phạm vi trả 404. Không có API sửa/xóa lịch sử.
- Không cho hủy/xóa/chuyển khỏi APPROVED đối với đăng ký đã có hồ sơ chấm.
- Sửa lỗi đăng ký lại đồng thời: kiểm tra lại trạng thái của dòng cũ bên trong khóa, tránh hai yêu cầu cùng kích hoạt lại một đăng ký đã hủy.
- Portal thêm trang chấm điểm, đợt chấm, chi tiết/nhập điểm/phân công/công bố/mở lại, hồ sơ cá nhân, sửa tài khoản hiện có và nhật ký tài khoản.

## 3. Ma trận quyền chấm điểm

| Chức năng | Admin | Giảng viên | Sinh viên |
|---|---|---|---|
| Tạo/sửa đợt, cấu hình tiêu chí | Có | Xem | Không |
| Tạo hồ sơ, phân công | Có | Không | Không |
| Lưu nháp/nộp điểm | Không mạo danh giảng viên | Chỉ hồ sơ được phân công | Không |
| Công bố, mở lại | Có | Không | Không |
| Xem điểm chưa công bố | Toàn bộ | Phạm vi được phân công | Không |
| Xem điểm đã công bố | Toàn bộ | Phạm vi được phân công | Chỉ bản thân |
| Xem lịch sử sửa điểm | Toàn bộ | Phạm vi được phân công | Không |

## 4. Migration và chạy ứng dụng

Migration mới:

- `registration-service/grading/migrations/0001_initial.py`: bảng `dot_chamdiem`, `ketqua_chamdiem`, `phancong_chamdiem`, `lichsu_chamdiem`.
- `identity-service/accounts/migrations/0002_user_token_version.py`: phiên bản xác thực của tài khoản.
- `identity-service/accounts/migrations/0003_revokedaccesstoken.py`: mã định danh access token đã thu hồi khi đăng xuất.

Sau khi SQL Server theo `.env` đang hoạt động, chạy tại thư mục gốc:

```powershell
cd C:\Users\Admin\SOA_GK
.\.venv\Scripts\python.exe -B scripts\migrate_all.py
.\run_all.bat
```

`migrate_all.py` giữ nguyên cấu hình của từng service, áp dụng migration còn thiếu, dừng khi có lỗi; không chạy flush/reset/seed và không tạo lại database. Portal vẫn không có database.

Trình tự thao tác: Admin tạo đợt chấm -> tạo hồ sơ từ đăng ký đã duyệt -> chọn giảng viên -> từng giảng viên lưu/nộp -> Admin xem lại và công bố -> sinh viên xem Điểm của tôi.

## 5. API mới và request mẫu

Tất cả API ở Registration Service `http://127.0.0.1:8003`, yêu cầu `Authorization: Bearer <access>`.

| Method | Endpoint | Mục đích |
|---|---|---|
| GET/POST | `/api/grading/periods/` | Danh sách/tạo đợt |
| GET/PUT/PATCH | `/api/grading/periods/{id}/` | Xem/sửa đợt |
| GET/POST | `/api/grading/assessments/` | Danh sách/tạo hồ sơ |
| GET | `/api/grading/assessments/{id}/` | Chi tiết |
| POST | `/api/grading/assessments/{id}/assign/` | Thay danh sách người chấm |
| POST | `/api/grading/assessments/{id}/scores/` | Lưu nháp hoặc nộp phiếu của người gọi |
| POST | `/api/grading/assessments/{id}/publish/` | Admin xác nhận/công bố |
| POST | `/api/grading/assessments/{id}/reopen/` | Admin mở lại, thu hồi công bố |
| GET | `/api/grading/assessments/{id}/history/` | Lịch sử |

Tạo đợt (Admin, thay thời gian cho phù hợp):

```json
{"name":"Đợt chấm HK1","start_at":"2026-10-27T00:00:00+07:00","end_at":"2026-12-31T23:59:00+07:00","is_active":true,"criteria":[{"code":"work","name":"Hoàn thành","weight":40},{"code":"design","name":"Kỹ thuật","weight":30},{"code":"report","name":"Tài liệu","weight":20},{"code":"defense","name":"Bảo vệ","weight":10}]}
```

Tạo hồ sơ: `POST /api/grading/assessments/` với `{"registration":1,"period":1}` -> 201.
Phân công: `POST .../1/assign/` với `{"lecturer_ids":[2,3]}` -> 200.
Giảng viên nộp:

```json
{"scores":{"work":"8","design":"7","report":"9","defense":"10"},"comment":"Đáp ứng yêu cầu","submit":true}
```

Điểm người này là 8.10. Nếu giảng viên còn lại có tổng 9.00, điểm cuối là 8.55. Gửi `submit:false` để lưu nháp.
Admin gửi `{}` tới `.../publish/` -> 200 khi đã đủ điểm, 400 khi chưa đủ.
Mở lại: `{"reason":"Phúc khảo theo biên bản"}` tới `.../reopen/` -> 200; sinh viên sau đó không còn thấy kết quả đến khi công bố lại.
Ngoài phạm vi -> 404; sai vai trò -> 403; thiếu/hết hạn token -> 401; service phụ thuộc không hoạt động -> 503 (hoặc 502 khi service từ chối token chuyển tiếp).

## 6. Bảo mật đã bổ sung

- `ALLOWED_HOSTS` đọc từ môi trường, mặc định chỉ localhost/127.0.0.1/[::1].
- `DEBUG=False` bắt buộc SECRET_KEY riêng ít nhất 50 ký tự; không chấp nhận khóa development mặc định.
- Production mặc định bật chuyển HTTPS, Secure session/CSRF cookie và HSTS. Proxy headers chỉ được tin khi bật `TRUST_PROXY_HEADERS=True` sau reverse proxy đáng tin.
- Không mở CORS rộng. Portal dùng form cùng origin và CSRF; API dùng Bearer token.
- Thay mật khẩu/vai trò/liên kết sinh viên hoặc khóa tài khoản thu hồi refresh token và tăng token_version. Identity từ chối access token phiên bản cũ.
- Đăng xuất thu hồi access token hiện tại theo jti; all_devices tăng token_version và thu hồi mọi refresh token.
- Student/Thesis/Registration hỗ trợ `JWT_CHECK_ACCOUNT_STATE=True`: xác minh chữ ký tại chỗ, sau đó gọi `/api/auth/me/` để kiểm tra trạng thái và quyền mới nhất. Mặc định True trong production, False khi DEBUG=True để giữ chế độ demo độc lập trước đây. Có thể bật True trong `.env` của cả ba service ngay khi demo.
- Khi bật kiểm tra trạng thái, Identity ngừng hoạt động -> trả 503, không cho thao tác dựa trên trạng thái chưa xác minh. Đây là đánh đổi tính sẵn sàng để thu hồi quyền ngay. Token SERVICE vẫn xác minh tại chỗ và không có quyền chấm điểm.
- Khi tắt kiểm tra trạng thái, access token cũ ở ba service vẫn có cửa sổ hiệu lực đến khi hết hạn. Không tuyên bố thu hồi tức thời trong chế độ này.
- `certifi` hiện đã nâng từ 2026.7.22 lên 2026.10.23, thêm ràng buộc >=2026.10.19 trong requirements. Nguồn cảnh báo: https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2 .
- Lưu `constraints-tested.txt` để cài môi trường theo phiên bản đã kiểm thử. Không cài thêm package chức năng mới.

Cấu hình production trong `.env` từng service (không dùng nguyên placeholder):

```dotenv
DEBUG=False
SECRET_KEY=<chuoi-ngau-nhien-rieng-it-nhat-50-ky-tu>
ALLOWED_HOSTS=<hostname-cua-service>
# Ba service nghiệp vụ:
JWT_CHECK_ACCOUNT_STATE=True
# Đặt CSRF_TRUSTED_ORIGINS cho Portal nếu thực tế cần origin HTTPS riêng.
# TRUST_PROXY_HEADERS=True chỉ sau reverse proxy do bạn kiểm soát.
```

## 7. Kiểm thử và kết quả

Chạy test logic, database tạm trong bộ nhớ:

```powershell
.\.venv\Scripts\python.exe -B scripts\test_all.py --sqlite
```

Chạy tích hợp thật qua năm tiến trình HTTP, khóa RSA và database SQLite tạm riêng, không mock HTTP:

```powershell
.\.venv\Scripts\python.exe -B scripts\integration_smoke.py
```

Các cổng ngẫu nhiên chỉ phục vụ kiểm thử cô lập, không sửa cổng runtime. Tiến trình thử nghiệm tự dừng; database và khóa thử nghiệm tự được dọn. Báo cáo ở `work/integration-result.json`.

Chạy bộ test với SQL Server cấu hình thật (tạo database test tên ngẫu nhiên riêng, không dùng application database để chứa dữ liệu test):

```powershell
.\.venv\Scripts\python.exe -B scripts\test_all.py --sql-server
```

Kiểm tra dependency:

```powershell
.\.venv\Scripts\python.exe -B -m pip check
.\.venv\Scripts\python.exe -B scripts\audit_dependencies.py
```

Kết quả kiểm tra hiện tại được ghi ở cuối tài liệu sau vòng xác minh cuối.

## 8. Giới hạn và phần chưa xác nhận

1. Bạn đã xác nhận instance `.\MSSQLSERVER01` đang chạy. Registry cho thấy TCP/IP và Named Pipes tắt, Shared Memory bật. Môi trường thực thi của Codex bị Windows từ chối kết nối Shared Memory (lỗi 5 / ODBC 08001). Không kết luận SQL Server đang tắt và không tự đổi cấu hình giao thức. Cần chạy migration/test SQL trong terminal người dùng có quyền kết nối instance này. Chưa áp dụng migration vào database thật; chưa xác nhận migration SQL Server hoặc kiểm thử khóa đồng thời trên SQL Server.
2. Các guard hiện có của Student/Thesis là kiểm tra qua REST trước khi xóa/giảm chỉ tiêu. Chúng chưa phải transaction phân tán: thay đổi đồng thời giữa nhiều service vẫn có khoảng hở kiểm tra-rồi-ghi. Khóa nội bộ Registration và bảo vệ hồ sơ chấm không được diễn giải là đã giải quyết nguyên tử xuyên database. Cần cơ chế reservation/tombstone/orchestrator nếu yêu cầu bảo đảm chặt chẽ cho kịch bản này; không thêm một giao thức thiếu kiểm chứng vào API hiện tại.
3. Nhật ký tài khoản và lịch sử chấm điểm đã có; chưa có nhật ký sự kiện đầy đủ cho mọi thay đổi Student/Thesis. Notification Service vẫn là tùy chọn chưa triển khai.
4. OSV là kiểm tra advisory công khai tại thời điểm chạy, không bảo đảm không còn lỗ hổng chưa công bố. Production còn cần domain, chứng chỉ HTTPS và reverse proxy thực tế để kiểm chứng cấu hình triển khai.

## 9. Các nhóm file thay đổi

- `registration-service/grading/`: models, serializers, views, urls, migration và tests.
- `registration-service/registrations/views.py`, `test_races.py`: bảo vệ hồ sơ có điểm và kiểm tra lại đăng ký đồng thời.
- `identity-service/accounts/`: token_version, thu hồi access token, migrations và tests.
- `*/config/settings.py`, `*/.env.example`, `*/requirements.txt`: bảo mật production và dependency.
- `student-service/config/jwt_auth.py`, `thesis-service/config/jwt_auth.py`, `registration-service/config/jwt_auth.py`: kiểm tra trạng thái tài khoản qua REST.
- `web-portal/portal/grading_forms.py`, `grading_views.py`, `api_client.py`, `urls.py`, templates và `test_grading.py`: giao diện mới.
- `scripts/`, `constraints-tested.txt`, README và tài liệu này: công cụ xác minh, migration và hướng dẫn.

## 10. Kết quả xác minh cuối

| Thành phần | Test đạt |
|---|---:|
| Student | 37/37 |
| Thesis | 39/39 |
| Registration + Grading | 87/87 |
| Identity | 44/44 |
| Web Portal | 73/73 |
| **Tổng** | **280/280** |

- Test dùng SQLite tạm trong bộ nhớ; không kết luận khóa/migration SQL Server đã đạt.
- Luồng HTTP tích hợp thật qua năm tiến trình đã đạt, gồm hai người chấm, trung bình 8.55, công bố, quyền sinh viên, thu hồi công bố, đăng xuất/khóa tài khoản, CSRF và lỗi service Student/Identity.
- OpenAPI của bốn service được validate với fail-on-warn: đạt, không cảnh báo.
- `check --deploy` của năm thành phần đạt khi truyền cấu hình production thử nghiệm đầy đủ, gồm SECRET_KEY ngẫu nhiên, HTTPS/cookie và các cờ HSTS. Chưa kiểm chứng domain/proxy/chứng chỉ thực tế.
- `pip check`: không có dependency hỏng. OSV kiểm tra 36 package sau cập nhật certifi: không có advisory được trả về.
- `makemigrations --check --dry-run`: không có model thay đổi chưa có migration.
- `git diff --check`: đạt.

### Bước cần chạy trên terminal của bạn

Môi trường Codex bị Windows từ chối Shared Memory; thao tác dưới đây cần chạy trong PowerShell/CMD thông thường của người dùng có quyền SQL Server:

```powershell
cd C:\Users\Admin\SOA_GK
.\.venv\Scripts\python.exe -B scripts\migrate_all.py
.\.venv\Scripts\python.exe -B scripts\test_all.py --sql-server
```

Sau khi migration thành công, khởi động lại năm service bằng `run_all.bat`. Vào menu Chấm điểm; chưa có dữ liệu điểm mẫu nên Admin cần tạo đợt và hồ sơ trước. Script `Apply-SOA-Upgrade.bat` đi kèm chỉ áp dụng migration và hiển thị kết quả; không thay giao thức SQL Server, cổng, database, khóa JWT hay `.env`.
