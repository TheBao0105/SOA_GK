# Giải thích luồng đăng ký đề tài (ôn bảo vệ)

Tài liệu này giải thích phần **đăng ký đề tài** trong Registration Service: code chạy theo thứ tự nào, vì sao viết như vậy, và các câu hội đồng hay hỏi. Code nằm ở `registration-service/registrations/views.py` (hàm `RegistrationListCreateView.create`) và `registrations/models.py` (`RegistrationLock`).

## 1. Toàn cảnh một request đăng ký

Sinh viên bấm "Đăng ký" trên Portal → Portal gửi `POST http://127.0.0.1:8003/api/registrations/` với body `{"student_id": 1, "thesis_id": 2}` và header `Authorization: Bearer <access token>`.

```
Portal ──POST──► Registration Service
                   │ 0. Xác thực JWT + kiểm tra vai trò
                   │ 1. check_remote_rules  ──GET──► Student Service  (sinh viên có tồn tại?)
                   │                         ──GET──► Thesis Service   (đề tài có tồn tại? còn OPEN?)
                   │ 2. run_locked  ── mở transaction, khóa "thesis:2" và "student:1"
                   │ 3.   check_local_limits  (đề tài còn chỗ? sinh viên chưa có đăng ký hiệu lực?)
                   │ 4.   lưu Registration (PENDING)  → commit, nhả khóa
                   ▼
                 201 Created
```

## 2. Từng bước

### Bước 0: xác thực và phân quyền

- `JWTAuthentication` (trong `config/jwt_auth.py`) kiểm tra chữ ký RS256 của token bằng **khóa công khai**. Registration Service không có bảng tài khoản và không giữ khóa bí mật.
- `RolePermission`: chỉ `ADMIN` và `STUDENT` được `POST`.
- Sinh viên chỉ được đăng ký cho chính mình: `student_id` trong body phải bằng `student_id` ghi trong token. Nếu khác thì trả 403. Sinh viên không sửa được token vì sửa sẽ làm hỏng chữ ký.

### Bước 1: `check_remote_rules`, kiểm tra qua service khác

Registration Service **không được đọc** `student_db` hay `thesis_db` (mỗi service sở hữu database riêng). Muốn biết sinh viên và đề tài có tồn tại không thì phải gọi REST:

| Gọi | Kết quả | Xử lý |
| --- | --- | --- |
| `GET /api/students/{id}/` | 404 | 400 "Student does not exist" |
| `GET /api/theses/{id}/` | 404 | 400 "Thesis does not exist" |
| Đề tài có `status != OPEN` | | 400 "Thesis is closed" |
| Service tắt hoặc timeout (5 giây) | | **503**, không lưu gì |
| Service trả 401/403 | | **502**, lỗi ở phía service được gọi |

Token của người dùng được **chuyển tiếp** sang service kia, nên quyền vẫn được kiểm tra ở đó.

### Bước 2: `run_locked`, khóa dữ liệu

**Vấn đề:** đề tài chỉ còn 1 chỗ mà có 2 sinh viên bấm cùng lúc. Nếu cả hai request cùng đếm thì cả hai đều thấy "còn 1 chỗ", cùng lưu, và đề tài bị **vượt chỉ tiêu**.

**Cách giải quyết:** trước khi đếm, request phải giành được "khóa" của đề tài và của sinh viên. Bảng `khoa_dangky` (model `RegistrationLock`) có mỗi đề tài một dòng `thesis:<id>` và mỗi sinh viên một dòng `student:<id>`. Request khóa các dòng này bằng `SELECT ... FOR UPDATE` (trên SQL Server là `WITH (UPDLOCK, ROWLOCK)`). Request thứ hai phải **chờ** request thứ nhất commit xong mới được đếm, và lúc đó nó thấy đề tài đã hết chỗ.

**Vì sao tách `ensure()` và `acquire()`?**

- `ensure()` tạo sẵn dòng khóa nếu chưa có, và **mỗi dòng tự commit ngay**, ngoài transaction chính.
- `acquire()` chạy **trong** transaction và chỉ khóa các dòng đã tồn tại.

Nếu tạo dòng khóa ngay trong transaction, hai request song song sẽ giữ khóa trên dòng mới (chưa commit) của nhau, và SQL Server phải hủy một request (lỗi deadlock 1205, người dùng thấy HTTP 500). Tách hai bước thì dòng khóa luôn có sẵn và đã commit trước khi tranh chấp.

**Vì sao khóa theo thứ tự cố định?** `acquire()` sắp xếp các key (`sorted`) rồi mới khóa. Hai request luôn khóa theo cùng thứ tự nên không bao giờ xảy ra cảnh A giữ khóa 1 chờ khóa 2 trong khi B giữ khóa 2 chờ khóa 1 (deadlock).

**Nếu SQL Server vẫn báo deadlock?** `run_locked` thử lại tối đa 3 lần (`LOCK_RETRIES`), mỗi lần chờ ngẫu nhiên một chút (`random.uniform`) để hai request không đụng nhau lần nữa. Hết 3 lần thì trả **503 "Registration Service is busy"** thay vì 500. Các lỗi database khác **không** thử lại (`is_retryable_lock_error`).

**Vì sao gọi HTTP (Bước 1) TRƯỚC khi khóa?** Gọi mạng có thể mất tới 5 giây. Nếu vừa giữ khóa vừa chờ mạng thì mọi sinh viên khác đăng ký cùng đề tài đều phải chờ theo. Vì vậy phải kiểm tra bên ngoài xong mới khóa, và giữ khóa càng ngắn càng tốt.

### Bước 3: `check_local_limits`, đếm lại sau khi đã khóa

Chỉ đếm đăng ký **còn hiệu lực** (`PENDING`, `APPROVED`); `REJECTED` và `CANCELLED` không chiếm chỗ.

- Số đăng ký hiệu lực của đề tài `>= max_students` → "Thesis has reached maximum students"
- Sinh viên đã có 1 đăng ký hiệu lực → "Student already has an active registration"

### Bước 4: lưu

- Chưa từng đăng ký cặp (sinh viên, đề tài) này: tạo dòng mới, trạng thái `PENDING`.
- Đã từng đăng ký rồi bị hủy hoặc từ chối: **dùng lại dòng cũ**, đặt lại thành `PENDING`, vì bảng có ràng buộc `unique_student_thesis`.
- Nếu hai request trùng nhau vẫn lọt qua, database báo `IntegrityError` và view trả 400 "already registered". Đây là lớp bảo vệ cuối cùng.

## 3. Online và offline khác nhau thế nào?

| | Offline (`run_demo.bat offline`) | Online (`run_demo.bat online`) |
| --- | --- | --- |
| Cách xác minh token | Chỉ kiểm chữ ký và hạn dùng bằng khóa công khai | Kiểm chữ ký, **rồi gọi** `GET /api/auth/me/` ở Identity |
| Khóa tài khoản hoặc đăng xuất | Token cũ vẫn dùng được đến khi hết hạn (tối đa 15 phút) | Bị chặn ngay lập tức |
| Identity tắt | Các service khác vẫn chạy | Trả **503** (từ chối cho an toàn) |
| Đánh đổi | Nhanh, ít phụ thuộc | An toàn hơn nhưng phụ thuộc Identity |

Cấu hình bằng biến `JWT_CHECK_ACCOUNT_STATE` (True là online).

## 4. Câu hỏi hội đồng hay hỏi

**Vì sao không dùng ForeignKey từ `Registration` sang `Student`?**
Vì `Student` nằm ở database khác (`student_db`) do service khác sở hữu, mà FK không thể trỏ xuyên database. Theo SOA, mỗi service chỉ giữ ID tham chiếu và kiểm tra qua REST API.

**Student Service đang tắt thì đăng ký thế nào?**
Bước 1 bắt lỗi kết nối và trả 503, không lưu gì. Đã có test integration cho đúng tình huống này.

**Xóa đề tài khi còn sinh viên đăng ký thì sao?**
Trước khi xóa, Thesis Service gọi ngược `GET /api/registrations/?thesis_id=..&active=true`. Còn đăng ký hiệu lực thì trả 409. Registration Service tắt thì không cho xóa.

**Như vậy là transaction phân tán chưa?**
**Chưa**, và nên nói thẳng điều này. Khóa và transaction chỉ bảo vệ dữ liệu **trong** Registration Service. Giữa lúc kiểm tra đề tài OPEN (Bước 1) và lúc lưu (Bước 4), giảng viên vẫn có thể đóng đề tài ở Thesis Service. Hệ thống thật sẽ dùng **Saga** hoặc cơ chế giữ chỗ (reservation). Với quy mô demo, nhóm chấp nhận khoảng hở rất ngắn này và đã ghi rõ trong `SYSTEM_REVIEW.md`.

**Làm sao chứng minh không vượt chỉ tiêu?**
Chạy `registration-service/scripts/concurrency_test.py`: script tạo đề tài `max_students=1` rồi gửi N request song song. Kết quả đúng là chỉ **1** request nhận 201, còn lại đều nhận 400 "Thesis has reached maximum students".

**Vì sao dùng RS256 mà không dùng HS256?**
HS256 dùng **một** khóa chung cho cả ký và xác minh, nên service nào có khóa cũng tự tạo được token giả. RS256 dùng khóa **bí mật** để ký (chỉ Identity giữ) và khóa **công khai** để xác minh (phát cho các service khác). Lộ khóa công khai thì cũng không ai ký được token.

**Sinh viên sửa `student_id` trong request để đăng ký hộ người khác được không?**
Không. View so sánh với `student_id` trong token và trả 403. Token có chữ ký nên không sửa được.

## 5. Mã lỗi trả về

| HTTP | Khi nào |
| --- | --- |
| 201 | Đăng ký thành công (PENDING) |
| 400 | Vi phạm quy tắc: không tồn tại, đề tài đóng, hết chỗ, đã có đăng ký |
| 401 | Không có token, token sai hoặc hết hạn |
| 403 | Sai vai trò hoặc đăng ký hộ người khác |
| 502 | Service khác từ chối token |
| 503 | Service khác tắt hoặc timeout; deadlock sau 3 lần thử; Identity tắt (chế độ online) |
