# Chấm điểm trực tiếp cho demo SOA

## Sử dụng

1. Sinh viên đăng ký đề tài; Admin hoặc giảng viên hướng dẫn duyệt đăng ký.
2. Giảng viên hướng dẫn đăng nhập, mở **Chấm điểm**. Đăng ký đã duyệt tự xuất hiện, không cần tạo hồ sơ.
3. Bấm **Chấm điểm**, nhập một điểm từ 0 đến 10 và nhận xét tùy chọn, rồi **Lưu điểm**.
4. Sinh viên mở **Điểm của tôi** để xem ngay. Admin xem toàn bộ tại **Chấm điểm**.
5. Bấm **Chi tiết** để xem đầy đủ điểm/nhận xét; Admin và giảng viên có thể **Sửa** hoặc **Xóa** điểm (có xác nhận). Sau xóa trở về chưa chấm, lịch sử vẫn giữ và có thể chấm lại.

Không có đợt chấm, tiêu chí/trọng số, phân công giám khảo hay bước công bố. Mỗi đăng ký có một điểm duy nhất. Giảng viên chỉ chấm đề tài mình hướng dẫn; Admin được xem, nhập, sửa và xóa toàn bộ điểm. Sinh viên chỉ đọc điểm của mình.

## API

Registration Service quản lý điểm cùng database với đăng ký; quyền hướng dẫn được hỏi Thesis Service qua REST. Không truy vấn database của service khác.

- `GET /api/grading/grades/`: danh sách điểm trong phạm vi người gọi.
- `POST /api/grading/grades/`: Admin hoặc giảng viên nhập/sửa điểm theo `registration`; lần đầu 201, lần sửa 200.
- `GET /api/grading/grades/{id}/`: xem điểm.
- `DELETE /api/grading/grades/{id}/`: Admin hoặc giảng viên hướng dẫn xóa điểm hiện tại; lịch sử được giữ.
- `GET /api/grading/grades/{id}/history/`: Admin hoặc giảng viên hướng dẫn xem lịch sử.

```json
{"registration": 1, "score": "8.50", "comment": "Đạt yêu cầu"}
```

Điểm bắt buộc, thang 0–10, tối đa hai chữ số thập phân; không nhận NaN, Infinity hay số ngoài khoảng. Giảng viên phải hướng dẫn đúng đề tài (Admin được quản lý toàn bộ) và đăng ký phải APPROVED. Điểm và lịch sử được lưu cùng transaction dưới khóa đăng ký. Đăng ký đã có điểm/lịch sử cũ được bảo vệ khỏi xóa/hủy/đổi trạng thái làm sai dữ liệu điểm.

## Cập nhật máy đang có dữ liệu

Dừng năm dịch vụ và chạy tại thư mục gốc dự án:

```powershell
.\.venv\Scripts\python.exe -B scripts\migrate_all.py
.\run_demo.bat online
```

Migration `grading.0002_grade_gradehistory_and_more` chuyển điểm tổng kết cũ sang bảng `diem_detai`. Nếu một đăng ký có nhiều hồ sơ cũ, lấy điểm tổng kết của hồ sơ có ID mới nhất trong các hồ sơ GRADED/PUBLISHED có điểm. Các hồ sơ nháp không tự biến thành điểm chính thức. Toàn bộ tiêu chí, phân công, nhận xét, phiếu chấm và sự kiện cũ được sao lưu trong `lichsu_diem` với action `LEGACY_IMPORTED` trước khi xóa các bảng chấm cũ. Điểm đã chuyển hiển thị ngay, không còn bước công bố. Người chấm hiển thị “Kết quả trước nâng cấp” để tránh gán điểm tổng hợp cũ cho một giảng viên cụ thể.

Migration chuyển đổi một chiều; không dùng `--fake` hoặc tự xóa migration đã áp dụng. Các migration cũ vẫn giữ trong Git để máy đã cài hoặc máy mới nâng cấp theo cùng lịch sử. Nếu kết nối SQL Server lỗi, sửa cấu hình instance/driver/quyền của máy đang chạy rồi áp dụng lại trước khi khởi động.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -B scripts\test_all.py --sqlite
.\.venv\Scripts\python.exe -B scripts\integration_smoke.py --auth-mode online
.\.venv\Scripts\python.exe -B scripts\integration_smoke.py --auth-mode offline
```

Kiểm thử migration chạy database thử riêng, xác minh điểm cũ, nhận xét, tiêu chí, nháp và lịch sử không bị mất; chỉ có một điểm hiện hành mỗi đăng ký. Kiểm thử HTTP chạy năm process với SQLite/khóa tạm, kiểm tra giảng viên nhập/sửa trực tiếp, sinh viên thấy ngay, chặn chấm trái quyền và CSRF. SQL Server cần chạy kiểm thử riêng trên máy có kết nối thật.
