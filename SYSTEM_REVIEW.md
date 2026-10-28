# Rà soát hệ thống đăng ký đề tài — 28/10/2026

## Kết luận trong phạm vi đồ án

Cấu trúc hiện tại phù hợp demo SOA bằng Django: bốn dịch vụ nghiệp vụ/xác thực độc lập và một Portal; database theo service, giao tiếp REST, xác thực thống nhất và quyền được kiểm tra tại backend. Các kiểm thử đạt bên dưới không đồng nghĩa đã chứng minh khả năng vận hành production hoặc giao dịch phân tán tuyệt đối.

## Phạm vi đã kiểm tra

- Cấu hình, URL, model, serializer, quyền, xác thực, HTTP client và các luồng chính: đăng nhập, quản lý sinh viên/đề tài, đăng ký, duyệt/hủy, tiến độ, chấm/sửa/xóa điểm.
- Phân tích cú pháp toàn bộ 165 file Python trong năm project tại thời điểm rà soát; kiểm tra import miền dữ liệu giữa các service và timeout của các lời gọi requests trực tiếp.
- Chạy toàn bộ test suite, migration consistency, OpenAPI validation và integration bằng năm process HTTP thực tế.
- Kiểm tra dependencies đã cài bằng pip check. Đây là kiểm tra tương thích requirements, không phải kết luận không có lỗ hổng bảo mật.

## Những chỉnh sửa trong lần rà soát này

| Vấn đề | Cách xử lý |
| --- | --- |
| Hồ sơ/tài khoản/nhật ký đặt lẫn trong module chấm điểm | Chuyển sang `portal/account_views.py`, `account_forms.py`; chấm điểm chỉ giữ chức năng điểm |
| Template tài khoản mang tên grading | Đổi thành `account_edit_form.html` và cập nhật nơi sử dụng |
| Helper đọc REST gắn với chấm điểm | Tách `portal/view_helpers.py` dùng chung cho các màn hình liên quan |
| Template login cũ không được sử dụng | Gỡ bản tự viết `accounts/templates/accounts/login.html`; giữ login Portal và URL tương thích `/accounts/login/` |
| Refresh gặp 5xx/429 bị coi như phiên hết hiệu lực | Giữ phiên, thông báo Identity tạm không làm mới được; chỉ lỗi 400/401/403 mới coi refresh bị từ chối |
| Ghi tiến độ dựa vào trạng thái đọc trước đó | Sau kiểm tra quyền qua REST, khóa đăng ký và đọc lại trạng thái trong transaction rồi mới ghi |
| Django Admin tại ba dịch vụ nghiệp vụ có thể bỏ qua quy tắc REST | Gỡ route `/admin/` tại Student/Thesis/Registration; giữ Admin của Identity |
| Portal thiếu chặn SECRET_KEY yếu khi DEBUG=False | Đồng bộ chặn secret yếu, cấu hình HTTPS/cookie/HSTS với các API service |
| Script nâng cấp ghi cứng đường dẫn máy gửi | Dùng thư mục của chính file batch; chạy được khi chuyển thư mục/máy |
| run_all không kiểm tra môi trường ảo | Thêm kiểm tra `.venv`, đặt dấu nháy đường dẫn thư mục gốc |
| Hàm validate_account không có nơi gọi | Gỡ helper tự viết không sử dụng khỏi HTTP client Registration |
| README nhiều đoạn lặp và mô tả phiên bản cũ | Viết lại theo kiến trúc, chức năng, quyền và quy trình cài hiện tại |

Các thay đổi bỏ đợt đăng ký và đơn giản hóa chấm điểm đã làm trước đó được giữ. Hệ thống hiện nhập trực tiếp 0–10, không có đợt chấm/tiêu chí/trọng số/hội đồng/công bố.

## Thành phần giữ lại và lý do

- Giữ file khung Django: `manage.py`, `apps.py`, `admin.py`, `models.py`, `tests.py`, `asgi.py`, `wsgi.py`, `__init__.py`. Không có file Python bị xóa trong diff hiện tại.
- Giữ migrations cũ để database đã sử dụng nâng cấp đúng thứ tự; không sửa lịch sử để giả lập dự án mới.
- Giữ các Django contrib app đang dùng và các bảng framework đã có để tránh phá dependency migration. Chúng không trở thành nguồn đăng nhập nghiệp vụ của ba service.
- Giữ `accounts` Portal để các URL đăng nhập cũ đi vào cùng luồng Identity/JWT; không có hệ xác thực/database Portal thứ hai.
- Giữ ba bản JWT/permission helper độc lập theo project. Đã kiểm tra chúng đồng nhất; không thêm đường dẫn import xuyên project chỉ để giảm số dòng mã.
- Giữ DRF, Swagger, requests, JWT và SQL Server adapter vì có vai trò thực tế. Không thêm Celery/Redis/ESB/Kubernetes cho quy mô demo này.
- Giữ seed, công cụ chẩn đoán và tests; `.venv`, `.env`, khóa, `work/`, `.backup_*` đã được ignore. Không xóa các bản sao lưu cá nhân.

## Kết quả xác minh

| Kiểm tra | Kết quả |
| --- | --- |
| Toàn bộ tests SQLite | 330 được phát hiện, 328 thực thi đạt; 2 test đồng thời SQL Server bỏ qua có chủ đích |
| Student / Thesis / Registration / Identity / Portal | 50 / 53 / 83 / 44 / 100 tests (bao gồm hai test bị bỏ qua) |
| Migrations khớp model | Đạt trong runner test (`makemigrations --check --dry-run`) |
| OpenAPI bốn service | Validate và fail-on-warn đều đạt |
| Integration online | Đạt, năm process HTTP với database và khóa tạm |
| Integration offline | Đạt, năm process HTTP với database và khóa tạm |
| Import model miền dữ liệu xuyên service | Không phát hiện bằng kiểm tra AST |
| Timeout các lời gọi requests trực tiếp trong project | Có |
| Route Admin | Ba service nghiệp vụ không expose; Identity còn expose |
| JWT/permission helper trùng giữa service | Đồng nhất nội dung |
| pip check | Không có dependency bị thiếu hoặc xung đột theo metadata đã cài |

Các test mới kiểm tra phục hồi phiên khi refresh gặp lỗi dịch vụ, và chặn ghi tiến độ nếu đăng ký đã đổi trạng thái sau bước kiểm tra quyền. Integration bao gồm đăng nhập ba vai trò, sinh mã, đăng ký/duyệt, quyền giảng viên/sinh viên, điểm tức thời, chi tiết/xóa/chấm lại, CSRF, lịch sử và phụ thuộc ngừng hoạt động.

Báo cáo máy đọc nằm trong `work/sqlite-test-result.json`, `work/integration-result-online.json`, `work/integration-result-offline.json`, `work/architecture-static-review.json`; schema đã validate nằm trong `work/*-schema.yaml`. Đây là đầu ra local, không cần commit.

## Giới hạn cần hiểu khi bảo vệ đồ án

1. Transaction/khóa chỉ bảo vệ dữ liệu trong một service. Kiểm tra REST rồi ghi dữ liệu không phải distributed transaction: việc sửa/xóa đề tài và đăng ký trên các service diễn ra đồng thời vẫn có cửa sổ thay đổi dữ liệu. Demo chưa có cơ chế reservation/saga để cam kết nguyên tử xuyên service.
2. Kiểm tra xóa sinh viên/đề tài hiện chặn đăng ký còn hiệu lực; lịch sử đăng ký không còn hiệu lực vẫn tham chiếu ID, có thể mất tên khi bản ghi gốc bị xóa. Giao diện có tên dự phòng theo ID.
3. ID giảng viên/tài khoản là tham chiếu giữa service, không có FK xuyên database. Seed qua REST liên kết ID thực tế; chưa có đối soát toàn bộ tham chiếu do client API nhập tùy ý.
4. Danh sách API chưa phân trang, Portal ghép tên bằng danh sách REST; phù hợp dữ liệu demo nhỏ. Không khẳng định hiệu năng ở quy mô lớn.
5. Offline không thu hồi access token ngay lập tức; online kiểm tra lại Identity và phụ thuộc tính sẵn sàng của nó.
6. Cookie Portal được ký và HttpOnly, không phải mã hóa. Cấu hình HTTP local, mật khẩu seed và Django runserver phục vụ demo; triển khai thực cần HTTPS, secret riêng, máy chủ WSGI/ASGI và quy trình backup.
7. Lịch sử điểm bị xóa vẫn nằm trong database; màn hình hiện chỉ tải lịch sử qua bản ghi điểm hiện tại, nên có thể xem lại sau khi chấm lại.
8. CSS/JS Bootstrap dùng CDN; máy demo cần Internet để tải giao diện đầy đủ.
9. SQL Server thật chưa được kiểm thử lại trong lần rà soát này. SQLite không xác nhận SQL Server locking/ODBC. Kết quả đồng thời người dùng đã chạy trước đây là bằng chứng của lần chạy đó, không thay thế kiểm thử phiên bản mới.

## Chạy bản đã chỉnh

Nếu đã áp dụng migration bỏ đợt và chấm điểm đơn giản từ lần trước, các chỉnh sửa lần rà soát này không thêm migration mới. Nếu chưa áp dụng, dừng dịch vụ và chạy:

```powershell
.\.venv\Scripts\python.exe -B scripts\migrate_all.py
```

Sau đó khởi động lại đủ năm dịch vụ:

```powershell
.\run_demo.bat online
```

Kiểm chứng riêng trên SQL Server trong terminal của máy có instance đúng cấu hình:

```powershell
.\.venv\Scripts\python.exe -B scripts\test_all.py --sql-server
.\.venv\Scripts\python.exe -B registration-service\scripts\concurrency_test.py --students 10
```

Lần rà soát này không thay `.env`, dữ liệu SQL Server hay khóa đang sử dụng. Các chỉnh sửa đang nằm local; chưa commit/push.
