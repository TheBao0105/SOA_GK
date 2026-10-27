# Hướng dẫn demo SOA — phạm vi học tập

Dự án: `C:\Users\Admin\SOA_GK`. Giữ nguyên bốn service nghiệp vụ/xác thực và Portal trên cổng 8000–8004. Không cần thêm Gateway, Redis, message broker hay service mới.

## 1. Chuẩn bị database

Mở PowerShell thông thường trên máy bạn, bằng tài khoản có quyền kết nối `.\MSSQLSERVER01`:

```powershell
cd C:\Users\Admin\SOA_GK
.\.venv\Scripts\python.exe -B scripts\check_sql_server.py
.\.venv\Scripts\python.exe -B scripts\migrate_all.py
```

Chỉ chuyển bước khi kết nối và migration thành công. Công cụ kiểm tra chỉ đọc; không đổi server/instance/port, không sửa `.env`. `migrate_all.py` kiểm tra cả bốn database trước khi bắt đầu migration và dừng nếu một database không truy cập được.

Trong môi trường Codex đã có lỗi truy cập SQL Server. Điều này không có nghĩa SQL Server trên máy bạn đang tắt. Kết quả chi tiết nằm ở `work/sql-server-check.json`. Nếu SSMS hoạt động mà script trong Codex không kết nối được, hãy chạy các lệnh bằng terminal thông thường của bạn.

## 2. Chọn chế độ xác thực

Dừng năm cửa sổ service cũ bằng Ctrl+C trước khi đổi chế độ. Sau đó chọn một lệnh:

```powershell
.\run_demo.bat offline
# HOẶC
.\run_demo.bat online
```

Launcher đặt biến môi trường cho các tiến trình con, không sửa `.env`. Các service vẫn ở cổng cũ, chỉ bind localhost theo lệnh runserver hiện có. Cấu hình chạy demo là DEBUG=True, HTTP cục bộ, ALLOWED_HOSTS chỉ localhost/127.0.0.1/[::1].

| Nội dung | offline | online |
|---|---|---|
| Kiểm tra chữ ký, issuer, loại và thời hạn JWT | Có | Có |
| Gọi thêm Identity để kiểm tra trạng thái/quyền | Không | Có |
| Identity tắt, access token còn hạn | API vẫn dùng được | API phụ thuộc trả 503 |
| Khóa tài khoản/đăng xuất ở các service nghiệp vụ | Token cũ có thể dùng đến khi hết hạn | Chặn token đã thu hồi sau khi xác minh với Identity |
| Mục đích demo | Tính độc lập của service xác minh JWT | Thu hồi quyền và sự phụ thuộc Identity |

Không thể vừa tuyên bố thu hồi tức thời vừa tuyên bố không cần kiểm tra trạng thái Identity trong cùng chế độ. `run_all.bat` vẫn dùng cấu hình `.env` như trước; dùng `run_demo.bat` để ba service có cùng chế độ rõ ràng.

## 3. Tạo bộ dữ liệu demo riêng

Chạy sau khi bốn service API đã sẵn sàng:

```powershell
.\.venv\Scripts\python.exe -B scripts\prepare_demo.py
```

Nếu database Identity mới hoàn toàn và chưa có Admin, tạo một tài khoản bằng `.\.venv\Scripts\python.exe identity-service\manage.py createsuperuser` sau migration. Nếu chưa có khóa JWT, chỉ khi đó chạy `.\.venv\Scripts\python.exe identity-service\manage.py generate_jwt_keys`; không dùng --force với khóa đang có.

Nhập mật khẩu Admin hiện tại khi được hỏi. Nếu chưa đổi tài khoản mẫu: username `admin`, mật khẩu `Admin@2026`. Script không hiển thị mật khẩu Admin và không sửa khóa JWT.

Bộ mặc định có:

| Loại | Tài khoản/mã | Mục đích |
|---|---|---|
| Giảng viên 1 | `demo.soa.gv1` | Hướng dẫn đề tài 1 và 3 |
| Giảng viên 2 | `demo.soa.gv2` | Hướng dẫn đề tài 2; có thể được phân công chấm cùng GV1 |
| Sinh viên | `demo.soa.sv1`, `demo.soa.sv2`, `demo.soa.sv3` | Kiểm tra tự đăng ký và giới hạn |
| Sinh viên | `DEMO_SOA_SV1`, `DEMO_SOA_SV2`, `DEMO_SOA_SV3` | Mỗi tài khoản được gắn với ID thật, không giả định ID 1/2/3 |
| Đề tài mở 1 | `DEMO_SOA_DT1` | Tối đa 1 sinh viên, GV1 phụ trách |
| Đề tài mở 2 | `DEMO_SOA_DT2` | Tối đa 1 sinh viên, GV2 phụ trách |
| Đề tài đóng | `DEMO_SOA_DT3` | Kiểm tra từ chối đăng ký đề tài đóng |
| Đợt đăng ký | `Đợt đăng ký demo SOA [soa]` | Mở 30 ngày khi được tạo |
| Đợt chấm | `Đợt chấm demo SOA [soa]` | Mở 30 ngày, tiêu chí 40/30/20/10 |

Mật khẩu của các tài khoản demo mới: `Demo@2026_SOA!`. Chỉ dùng dữ liệu giả.

Script gọi REST API; không truy cập database service khác. Chạy lại không tạo trùng, không đổi mật khẩu tài khoản đã có, không xóa/đặt lại đăng ký hoặc điểm. Nếu dữ liệu đã được thay đổi trong lần demo trước, script báo cảnh báo và giữ nguyên.

Để có một bộ mới cho lần trình bày khác, dùng tag 1–6 chữ thường/số:

```powershell
.\.venv\Scripts\python.exe -B scripts\prepare_demo.py --tag buoi2
```

Khi đó dùng `demo.buoi2.gv1`, `demo.buoi2.sv1`, `DEMO_BUOI2_DT1`… Thông tin ID nằm trong `work/demo-data-buoi2.json`. Không cần xóa database để demo lại.

## 4. Sáu tình huống trình bày

### A. Đăng nhập và bảo vệ API

Mở http://127.0.0.1:8000/ . Trình bày truy cập khi chưa đăng nhập bị chuyển về trang đăng nhập; gọi API nghiệp vụ không có Bearer token trả 401.

### B. Phối hợp giữa các service

Đăng nhập `demo.soa.sv1`, chọn `DEMO_SOA_DT1`, đăng ký. Registration kiểm tra sinh viên qua Student, đề tài qua Thesis, sau đó lưu đăng ký trong database của chính nó. Trạng thái PENDING.

Đăng nhập `demo.soa.gv1`, duyệt đăng ký. Sinh viên xem được trạng thái APPROVED. Portal chỉ tổng hợp kết quả qua REST.

### C. Chỉ tiêu và đề tài đóng

Đăng nhập `demo.soa.sv2`, đăng ký `DEMO_SOA_DT1`: nhận thông báo đủ chỉ tiêu, không có đăng ký mới. PENDING và APPROVED đều chiếm chỗ.

Danh sách sinh viên chỉ hiện đề tài OPEN. Có thể dùng Swagger và ID đề tài `DEMO_SOA_DT3` trong báo cáo dữ liệu để minh họa API từ chối đề tài CLOSED.

### D. Phân quyền thật ở backend

Giảng viên `demo.soa.gv2` không được sửa/duyệt đề tài của GV1. Sinh viên không được xem hồ sơ sinh viên khác hoặc quản lý tài khoản. Nên minh họa bằng gọi API trực tiếp ngoài việc nhìn các nút bị ẩn.

Ví dụ PowerShell lấy token sinh viên, rồi thử API Admin:

```powershell
$demoBody = @{ username='demo.soa.sv1'; password='Demo@2026_SOA!' } | ConvertTo-Json
$demoLogin = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8004/api/auth/login/' -ContentType 'application/json' -Body $demoBody
$demoHeaders = @{ Authorization = "Bearer $($demoLogin.access)" }
Invoke-RestMethod -Uri 'http://127.0.0.1:8004/api/users/' -Headers $demoHeaders
```

Kết quả mong đợi ở lệnh cuối: HTTP 403. Không in token ra màn hình khi trình bày.

### E. Service phụ thuộc ngừng hoạt động

Trước khi dừng Student, ghi lại ID của DEMO_SOA_SV3 và DEMO_SOA_DT2 từ báo cáo dữ liệu, rồi lấy token Admin. Sau đó dừng Student và dùng Swagger của Registration để POST /api/registrations/ với hai ID này: API trả 503 và không lưu đăng ký dở dang. Form Portal cần tải danh sách sinh viên nên không phù hợp để gửi yêu cầu này khi Student đã tắt. Khởi động lại Student sau khi trình bày.

Nếu tắt Identity: phải đăng nhập trước, giữ access token còn hạn. Trong offline, thử Dashboard/Sinh viên hoặc API nghiệp vụ; tránh thao tác đăng nhập/đổi mật khẩu vì chính chúng cần Identity. Trong online, backend trả 503 và Portal hiển thị thông báo lỗi. Trang API Docs chỉ kiểm tra /api/schema/ phản hồi HTTP 200; không chứng minh SQL Server hoạt động.

### F. Chấm điểm có kiểm soát

1. Admin vào Chấm điểm, tạo hồ sơ cho đăng ký của `demo.soa.sv1` đã APPROVED, chọn đợt chấm demo.
2. Phân công cả `demo.soa.gv1` và `demo.soa.gv2`.
3. GV1 nhập 8/7/9/10 theo các trọng số 40/30/20/10, lưu nháp rồi nộp: tổng 8.10.
4. GV2 nhập 9 cho bốn tiêu chí rồi nộp: điểm cuối 8.55.
5. Trước công bố, sinh viên chưa thấy hồ sơ; Admin công bố xong thì sinh viên thấy điểm.
6. Admin mở lại kèm lý do: kết quả ẩn khỏi sinh viên, giảng viên nộp lại, lịch sử cũ vẫn giữ.

## 5. Kiểm thử trước buổi demo

```powershell
# Logic và phân quyền, database trong bộ nhớ
.\.venv\Scripts\python.exe -B scripts\test_all.py --sqlite

# Tích hợp qua 5 tiến trình HTTP thật, database thử riêng
.\.venv\Scripts\python.exe -B scripts\integration_smoke.py --auth-mode offline
.\.venv\Scripts\python.exe -B scripts\integration_smoke.py --auth-mode online

# Kiểm thử đúng backend SQL Server, database test tên ngẫu nhiên riêng
.\.venv\Scripts\python.exe -B scripts\test_all.py --sql-server

# Tranh chỗ cuối cùng: cần 4 API thật đang chạy và một đợt đăng ký mở
.\.venv\Scripts\python.exe -B registration-service\scripts\concurrency_test.py --students 10
```

Test HTTP tạo bộ dữ liệu/khóa/database thử riêng; test bộ chuẩn bị dữ liệu hai lần và kiểm tra không đổi mật khẩu đã có. Không chạy prepare_demo trên database thật trong smoke test. Test tranh chỗ cuối tạo dữ liệu tạm có mã ngẫu nhiên, yêu cầu đúng 1 request 201 và N−1 request 400 đủ chỉ tiêu; không coi 503 là một lần từ chối chỉ tiêu thành công.

## 6. Phần giới hạn cần nói rõ

Khóa transaction bảo vệ chỉ tiêu bên trong Registration. Kiểm tra trước khi xóa/giảm chỉ tiêu qua REST chưa tạo transaction nguyên tử xuyên Student/Thesis/Registration. Bản demo ghi nhận giới hạn này; chưa bổ sung Saga, broker hoặc cơ chế điều phối phân tán.

Không sử dụng mật khẩu demo/dữ liệu thật và không công khai cấu hình demo lên Internet. Các yêu cầu MFA, CI/CD, Kubernetes, giám sát tập trung và tối ưu tải lớn nằm ngoài phạm vi bản học tập này.


## 7. Kết quả sửa và xác minh ngày 27/10/2026

| Nội dung đã lọc | Kết quả |
|---|---|
| Trạng thái API | Chỉ HTTP 200 của schema mới được báo phản hồi; không theo redirect và không đánh đồng với database sẵn sàng |
| JSON liên service | Kiểm tra loại dữ liệu, ID, trạng thái và chỉ tiêu theo nhu cầu bên gọi; dữ liệu sai không cho phép ghi/xóa/giảm chỉ tiêu |
| Retry database | Chỉ retry OperationalError được nhận diện là deadlock/serialization/lock timeout; lỗi khác có log và trả 500 rõ ràng |
| Xác thực demo | Launcher offline/online thống nhất biến môi trường, không ghi đè .env |
| Dữ liệu demo | Script REST tạo bộ riêng theo tag, dùng ID thực tế; chạy lại giữ mật khẩu và dữ liệu đã có |
| SQL Server | Đã thử kiểm tra nhưng môi trường Codex vẫn không kết nối được; chưa áp dụng migration và chưa xác nhận khóa SQL Server thật |

Bộ test sau cập nhật tự sinh mã: **325 test, 323 thực thi đạt và 2 test đồng thời SQL Server được bỏ qua trên SQLite**. Gồm Student 50, Thesis 53, Registration/Grading 94, Identity 44, Portal 84. Hai test SQL bổ sung cần chạy trên SQL Server thật.

Hai lượt tích hợp HTTP qua năm tiến trình đã đạt:

- Offline: Identity tắt nhưng token còn hạn vẫn gọi API nghiệp vụ được; đăng xuất/khóa ở Identity không được diễn giải là thu hồi tức thời tại các service offline.
- Online: token bị thu hồi bị chặn; Identity tắt thì backend phụ thuộc trả 503.
- Cả hai: đăng ký/duyệt/chấm/công bố/phúc khảo, CSRF, lỗi Student và tạo dữ liệu demo lặp lại đều được kiểm tra.
- Bộ chuẩn bị dữ liệu được chạy hai lần trên database thử riêng; mật khẩu demo đã đổi vẫn được giữ và tài khoản sinh viên gắn với ID thật.

OpenAPI Registration được validate không cảnh báo; không có migration mới bị thiếu; `git diff --check` đạt. Đã kiểm tra cú pháp Python và nhánh từ chối tham số sai của launcher; không khởi động các service thật của người dùng trong lần sửa này.

Các phản hồi lỗi cố tình tạo trong test là dữ liệu giả, không phải kết luận database ứng dụng đang hỏng. Kết quả SQL được ghi là bị chặn kết nối, không ghi thành “đã đạt”.


## Cập nhật tự sinh mã

Form thêm sinh viên/đề tài đã bỏ ô nhập mã; backend tự cấp SV001… / DT001… theo dãy đang có. Trang sửa chỉ hiển thị mã. Xem AUTO_CODES.md và chạy lại migration trước khi dùng tính năng mới.

Bản trước đã được bạn xác minh qua 297 test với các service dùng SQL Server và phép thử 10 yêu cầu tranh một chỗ. Các bảng bộ đếm mã là cập nhật mới, không được suy diễn là đã được xác minh bởi kết quả cũ.
