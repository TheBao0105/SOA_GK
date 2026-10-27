# Tự sinh mã sinh viên và mã đề tài

Đã sửa luồng thêm mới trong SOA_GK:

- Thêm sinh viên: chỉ nhập họ tên, email, lớp, ngành; backend tự cấp mã SV001, SV002…
- Thêm đề tài: chỉ nhập tên, mô tả, giảng viên, chỉ tiêu và trạng thái; backend tự cấp mã DT001, DT002…
- Trang sửa chỉ hiển thị mã, không có ô nhập mã. Sửa thông tin khác giữ nguyên mã.
- Sau khi lưu, thông báo thành công và danh sách hiển thị mã đã cấp.

## Cập nhật trước khi sử dụng

Dừng các cửa sổ service cũ. Mở PowerShell thông thường của bạn:

```powershell
cd C:\Users\Admin\SOA_GK
.\.venv\Scripts\python.exe -B scripts\migrate_all.py
.\run_demo.bat offline
```

Có thể chọn `online` thay `offline` theo kịch bản demo hiện có. Sau khi năm service khởi động, mở http://127.0.0.1:8000/ và thử Sinh viên → Thêm, Đề tài → Thêm.

Hai migration mới là:

- Student Service: `students/migrations/0002_auto_codes.py` tạo bảng `bo_dem_ma_sinhvien`.
- Thesis Service: `theses/migrations/0003_auto_codes.py` tạo bảng `bo_dem_ma_detai`.

Migration chỉ thêm bộ đếm và khởi tạo từ mã đang có, không đổi mã, ID hay dữ liệu các bản ghi cũ. Không cần xóa database hoặc chạy lại dữ liệu mẫu.

## Quy tắc cấp mã

Nếu đã có SV001–SV004 thì mã tự động tiếp theo là SV005; nếu đã có DT001–DT003 thì tiếp theo là DT004. Khi vượt 999, mã tiếp tục thành SV1000/DT1000, không giới hạn ở ba chữ số.

Mỗi service giữ bộ đếm trong database riêng. Khi cấp mã, service khóa dòng bộ đếm và lưu bản ghi trong cùng một transaction; frontend không tự đoán mã. Mã sinh viên và mã đề tài vẫn có ràng buộc unique ở database.

Từ khi áp dụng bộ đếm, mã tự động đã cấp qua API sẽ không tự được cấp lại sau khi bản ghi bị xóa. Các mã đã bị xóa trước khi nâng cấp không thể được khôi phục lịch sử chỉ từ dữ liệu còn lại.

Bộ đếm đối chiếu thêm các mã nhập bằng công cụ cũ/seed để tránh đụng mã hiện có. Với quy mô demo, cách đối chiếu đơn giản này là đủ; không thêm service hoặc package mới.

API cũ vẫn được hỗ trợ: nếu gửi mã rõ ràng thì mã đó được kiểm tra duy nhất và giữ theo dữ liệu nhập. Nếu bỏ trường mã hoặc gửi chuỗi rỗng khi tạo mới, service tự sinh. Điều này giữ tương thích với các script seed/demo hiện có. Giao diện web luôn dùng cơ chế tự sinh.

Ví dụ tạo sinh viên:

```json
{"full_name":"Nguyễn Văn A","email":"a@example.test","class_name":"CNTT1","major":"CNTT"}
```

Ví dụ tạo đề tài:

```json
{"title":"Đề tài demo tự động","description":"","max_students":1,"status":"OPEN"}
```

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -B scripts\test_all.py --sqlite
.\.venv\Scripts\python.exe -B scripts\test_all.py --sql-server
```

Có thêm test cấp mã nối tiếp, bỏ trống mã, giữ mã nhập cũ, không dùng lại mã đã xóa, giữ mã khi sửa và migration không đổi bản ghi cũ. Bộ test SQL Server có hai trường hợp gửi đồng thời 5 request tạo sinh viên/đề tài để xác nhận mã khác nhau. Hai trường hợp này được bỏ qua trên SQLite vì SQLite không thể chứng minh cơ chế khóa SQL Server.

Luồng HTTP thử nghiệm còn kiểm tra tạo cả sinh viên và đề tài từ API và từ form Portal mà không nhập mã.


## Kết quả xác minh bản cập nhật

- Phát hiện 325 test: 323 test thực thi đạt; 2 test tạo đồng thời chỉ dành cho SQL Server được bỏ qua trên SQLite.
- Đã kiểm tra HTTP thực tế qua năm tiến trình: tạo qua API không gửi mã nhận SV001/DT001; thêm qua form Portal không có ô mã nhận SV002/DT002.
- OpenAPI của Student/Thesis được validate không cảnh báo. Model thay đổi đã có migration tương ứng.
- Đã thử migration từ Codex nhưng bước kiểm tra kết nối SQL Server bị chặn; không có migration mới nào được áp dụng vào database thật trong lần sửa này.
- Kết quả SQL Server bạn gửi trước đây xác nhận bản trước hoạt động. Hai migration và hai test đồng thời cấp mã là phần mới, cần chạy lại bằng terminal của bạn.
