# Nâng cấp demo SOA hiện tại

Theo phạm vi demo đã đơn giản hóa, chấm điểm không còn đợt, tiêu chí, phân công hay công bố. Giảng viên hướng dẫn nhập một điểm 0–10 cho đăng ký đã duyệt; sinh viên xem ngay. Hướng dẫn đầy đủ: [GRADING_GUIDE.md](GRADING_GUIDE.md).

## Kiến trúc

- Identity Service xác thực, cấp JWT và quản lý tài khoản.
- Student/Thesis/Registration có database riêng, gọi nhau qua REST.
- Module grading nằm trong Registration Service vì điểm gắn trực tiếp với đăng ký.
- Quyền chấm theo giảng viên hướng dẫn lấy qua REST từ Thesis Service.
- Portal không có database, chỉ gọi API.

## Quyền

| Chức năng | Admin | Giảng viên hướng dẫn | Sinh viên |
|---|---|---|---|
| Xem điểm | Toàn bộ | Đề tài hướng dẫn | Bản thân |
| Nhập/sửa/xóa điểm | Toàn bộ | Đăng ký APPROVED thuộc đề tài mình | Không |
| Xem lịch sử | Toàn bộ | Đề tài hướng dẫn | Không |

## Migration

Dừng các dịch vụ, chạy `.\.venv\Scripts\python.exe -B scripts\migrate_all.py`, rồi `.\run_demo.bat online`. Không reset database hoặc dùng `--fake`.

- `registrations.0003_remove_registration_period`: bỏ lịch đăng ký.
- `grading.0002_grade_gradehistory_and_more`: chuyển điểm tổng kết cũ sang một điểm/đăng ký, lưu đầy đủ dữ liệu chấm cũ vào lịch sử rồi bỏ các bảng phức tạp. Đây là chuyển đổi một chiều.
- Các migration Identity về token version/thu hồi token vẫn giữ.

## Xác thực và kiểm thử

JWT RS256 và phân quyền vẫn được kiểm tra ở backend; không lấy quyền từ form. Chế độ online kiểm tra thêm trạng thái tài khoản ở Identity; offline xác minh chữ ký và hạn token tại chỗ. CSRF bảo vệ POST Portal. Điểm bắt buộc trong khoảng 0–10, hai chữ số thập phân; thao tác chấm khóa đăng ký và lưu lịch sử cùng transaction.

Chạy `scripts/test_all.py --sqlite` và `scripts/integration_smoke.py --auth-mode online` hoặc `offline` bằng Python của `.venv`. Integration dùng database/khóa tạm, không sửa `.env` và database đang demo. Kiểm thử SQLite không thay thế kiểm thử SQL Server thật.
