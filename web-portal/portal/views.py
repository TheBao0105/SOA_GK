"""
Các trang của Web Portal.

Mỗi view chỉ gọi api_client (HTTP/REST) rồi đưa dữ liệu ra template.
Không có model, không có truy vấn database.
"""
import logging

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.roles import QUAN_TRI, GIANG_VIEN, SINH_VIEN

from . import api_client as api
from .api_client import ApiError, NotFound, ServiceUnavailable
from .auth import (
    SESSION_ACCESS,
    SESSION_REFRESH,
    current_role,
    current_user,
    has_valid_session,
    login_session,
    role_required,
    save_tokens,
)
from .forms import (
    LOGIN_ERRORS,
    AccountForm,
    ChangePasswordForm,
    LoginForm,
    ProgressNoteForm,
    RegistrationForm,
    StudentForm,
    ThesisForm,
    api_error_message,
    translate_error,
)


# ---------------------------------------------------------------- Đăng nhập
def login_view(request):
    """Đăng nhập: Portal gửi username/mật khẩu sang Identity Service để lấy JWT."""
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = ""  # chống chuyển hướng sang trang lạ (open redirect)

    if request.method == "GET" and has_valid_session(request.session):
        return redirect(next_url or "dashboard")

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            data = api.login(form.cleaned_data["username"], form.cleaned_data["password"])
            login_session(request, data)
            messages.success(request, f"Xin chào {request.session['user']['full_name']}!")
            return redirect(next_url or "dashboard")
        except ApiError as exc:
            form.add_error(None, LOGIN_ERRORS.get(exc.code, "Đăng nhập không thành công."))
        except ServiceUnavailable as exc:
            form.add_error(None, translate_error(str(exc)))

    return render(request, "portal/login.html", {"form": form, "next": next_url})


@require_POST
def logout_view(request):
    refresh = request.session.get(SESSION_REFRESH)
    if refresh:
        try:
            api.logout(refresh)  # thu hồi refresh token ở Identity Service
        except Exception:  # noqa: BLE001 - đăng xuất ở Portal vẫn phải thành công
            pass
    request.session.flush()
    messages.success(request, "Bạn đã đăng xuất.")
    return redirect("login")


def change_password_view(request):
    form = ChangePasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            data = api.change_password(form.cleaned_data["old_password"], form.cleaned_data["new_password"])
            save_tokens(request.session, data)  # phiên cũ bị thu hồi, dùng cặp token mới
            messages.success(request, "Đổi mật khẩu thành công.")
            return redirect("dashboard")
        except ApiError as exc:
            form.add_api_errors(exc.data)
        except ServiceUnavailable as exc:
            form.add_error(None, translate_error(str(exc)))
    return render(request, "portal/change_password.html", {"menu": "account", "form": form})


# request chứa thông tin yêu cầu HTTP từ trình duyệt của người dùng
# Chỉ ADMIN (đăng ký hộ) và STUDENT (tự đăng ký) dùng được trang này
@role_required(QUAN_TRI, SINH_VIEN)
def registration_create(request):

    # Sinh viên chỉ được đăng ký cho chính mình: student_id lấy từ tài khoản đăng nhập
    fixed_student_id = None
    if current_role(request) == "STUDENT":
        fixed_student_id = current_user(request).get("student_id")
        if fixed_student_id is None:
            messages.error(request, translate_error("Your account is not linked to a student record"))
            return redirect("registration_list")

    # Gọi Student Service thông qua REST API để lấy danh sách sinh viên
    # api.students.list là hàm thực hiện yêu cầu đến API của Student Service
    # default=[]: nếu không lấy được dữ liệu theo cơ chế của fetch(),
    # sử dụng danh sách rỗng làm giá trị mặc định
    # (sinh viên tự đăng ký thì không cần chọn sinh viên)
    students = [] if fixed_student_id else fetch(request, api.students.list, default=[])

    # Gọi Thesis Service thông qua REST API để lấy danh sách đề tài
    # Kết quả được dùng để hiển thị các đề tài cho người dùng lựa chọn
    theses = fetch(request, api.theses.list, default=[])

    # Tạo biểu mẫu đăng ký đề tài
    # request.POST or None:
    # - Nếu người dùng gửi dữ liệu POST, truyền dữ liệu đó vào biểu mẫu
    # - Nếu chưa gửi dữ liệu, truyền None để hiển thị biểu mẫu trống
    # students và theses được truyền vào để biểu mẫu có dữ liệu lựa chọn
    form = RegistrationForm(
        request.POST or None,
        students=students,
        theses=theses,
        fixed_student_id=fixed_student_id,
        # Bấm "Đăng ký" ở trang Đề tài -> chọn sẵn đề tài đó
        initial={"thesis_id": request.GET.get("thesis_id")},
    )

    # Kiểm tra người dùng có gửi biểu mẫu bằng phương thức POST hay không
    # Đồng thời kiểm tra dữ liệu gửi lên có hợp lệ hay không
    if request.method == "POST" and form.is_valid():

        try:
            # Gửi dữ liệu đăng ký đã được kiểm tra hợp lệ đến Registration Service
            # form.cleaned_data chứa dữ liệu đã được Django xác thực
            #
            # Registration Service chịu trách nhiệm kiểm tra nghiệp vụ,
            # chẳng hạn gọi Student Service và Thesis Service để xác minh
            # sinh viên, đề tài có tồn tại hay không
            # Sau đó, service xử lý việc tạo đăng ký trong cơ sở dữ liệu của nó
            api.registrations.create(form.cleaned_data)

            # Nếu yêu cầu tạo đăng ký thành công,
            # thêm thông báo thành công để hiển thị trên giao diện
            messages.success(request, "Đăng ký đề tài thành công.")

            # Chuyển hướng người dùng đến trang danh sách đăng ký
            return redirect("registration_list")

        # Bắt lỗi API khi Registration Service trả về lỗi nghiệp vụ hoặc dữ liệu
        # exc.data chứa thông tin lỗi do API trả về
        except ApiError as exc:

            # Đưa các lỗi từ API vào biểu mẫu để người dùng biết
            # dữ liệu nào cần được kiểm tra hoặc chỉnh sửa
            form.add_api_errors(exc.data)

        # Bắt lỗi khi service không thể truy cập hoặc không phản hồi
        except ServiceUnavailable as exc:

            # Chuyển thông tin lỗi thành thông báo dễ hiểu
            # rồi hiển thị lỗi chung trên biểu mẫu
            form.add_error(None, translate_error(str(exc)))

    # Nếu người dùng mới mở trang, dữ liệu chưa hợp lệ,
    # hoặc xảy ra lỗi khi gọi API, hiển thị lại biểu mẫu đăng ký
    return render(
        request,
        "portal/registration_form.html",
        {
            # Đánh dấu mục Đăng ký trên menu giao diện
            "menu": "registrations",

            # Truyền biểu mẫu sang template để hiển thị
            # cả dữ liệu nhập và thông báo lỗi nếu có
            "form": form,

        }
    )


def fetch(request, func, *args, default=None):
    """Gọi API; nếu service đang tắt thì báo lỗi lên giao diện và trả về default."""
    try:
        return func(*args)
    except ServiceUnavailable as exc:
        messages.error(request, translate_error(str(exc)))
        return default


ACTIVE_STATUSES = ("PENDING", "APPROVED")
STATUS_LABELS = [
    ("PENDING", "Chờ duyệt"), ("APPROVED", "Đã duyệt"), ("REJECTED", "Từ chối"), ("CANCELLED", "Đã hủy"),
]


def count_active_registrations(registrations):
    """Đếm số đăng ký còn hiệu lực (PENDING / APPROVED) theo từng đề tài."""
    counts = {}
    for r in registrations:
        if r["status"] in ACTIVE_STATUSES:
            counts[r["thesis_id"]] = counts.get(r["thesis_id"], 0) + 1
    return counts


# ---------------------------------------------------------------- Trang tổng quan
@role_required(QUAN_TRI, GIANG_VIEN, SINH_VIEN)
def dashboard(request):
    def section(func, default=None):
        try:
            return func()
        except ServiceUnavailable as exc:
            messages.error(request, translate_error(str(exc)))
            return default
        except api.Forbidden as exc:
            service = exc.service_name or "API"
            logging.getLogger(__name__).warning(
                "Dashboard HTTP 403 from %s; Portal session preserved", service)
            messages.error(request, f"{service} từ chối truy cập (HTTP 403). Phiên đăng nhập vẫn được giữ. Kiểm tra quyền tài khoản và cấu hình dịch vụ.")
            return default

    students = section(lambda: fetch(request, api.students.list))
    theses = section(lambda: fetch(request, api.theses.list))
    registrations = section(lambda: fetch(request, api.registrations.list))

    counts = count_active_registrations(registrations or [])
    recent_theses = sorted(theses or [], key=lambda t: t["id"], reverse=True)[:5]
    for t in recent_theses:
        t["registered"] = counts.get(t["id"], 0) if registrations is not None else None

    return render(request, "portal/dashboard.html", {
        "menu": "dashboard",
        "total_students": len(students) if students is not None else None,
        "total_theses": len(theses) if theses is not None else None,
        "open_theses": (
            len([t for t in theses if t["status"] == "OPEN"]) if theses is not None else None
        ),
        "total_registrations": len(registrations) if registrations is not None else None,
        "recent_theses": recent_theses,
        "theses_available": theses is not None,
    })


# ---------------------------------------------------------------- Sinh viên
@role_required(QUAN_TRI, GIANG_VIEN, SINH_VIEN)
def student_list(request):
    q = request.GET.get("q", "").strip()
    students = fetch(request, api.students.list, {"search": q} if q else None, default=[])
    return render(request, "portal/student_list.html", {
        "menu": "students", "students": students, "q": q,
    })


@role_required(QUAN_TRI)
def student_form(request, pk=None):
    initial = None
    if pk:
        try:
            initial = api.students.get(pk)
        except (NotFound, ServiceUnavailable):
            messages.error(request, "Không tải được thông tin sinh viên.")
            return redirect("student_list")
    form = StudentForm(request.POST if request.method == "POST" else None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            if pk:
                api.students.update(pk, form.cleaned_data)
                messages.success(request, "Cập nhật sinh viên thành công.")
            else:
                created = api.students.create(form.cleaned_data)
                code = created.get("student_code", "") if isinstance(created, dict) else ""
                messages.success(request, "Thêm sinh viên thành công." + (f" Mã: {code}" if code else ""))
            return redirect("student_list")
        except ApiError as exc:
            form.add_api_errors(exc.data)
        except ServiceUnavailable as exc:
            form.add_error(None, translate_error(str(exc)))
    return render(request, "portal/student_form.html", {
        "menu": "students", "form": form, "is_edit": bool(pk), "record": initial,
    })


@require_POST
@role_required(QUAN_TRI)
def student_delete(request, pk):
    try:
        api.students.delete(pk)
        messages.success(request, "Đã xóa sinh viên.")
    except ApiError as exc:
        # 409: sinh viên còn đăng ký hiệu lực bên Registration Service
        messages.error(request, api_error_message(exc.data))
    except NotFound:
        messages.error(request, "Sinh viên không tồn tại.")
    except ServiceUnavailable as exc:
        messages.error(request, translate_error(str(exc)))
    return redirect("student_list")


# ---------------------------------------------------------------- Đề tài
@role_required(QUAN_TRI, GIANG_VIEN, SINH_VIEN)
def thesis_list(request):
    q = request.GET.get("q", "").strip()
    theses = fetch(request, api.theses.list, {"search": q} if q else None, default=[])
    registrations = fetch(request, api.registrations.list, default=[])
    counts = count_active_registrations(registrations)
    for t in theses:
        t["registered"] = counts.get(t["id"], 0)
    return render(request, "portal/thesis_list.html", {
        "menu": "theses", "theses": theses, "q": q,
    })


@role_required(QUAN_TRI, GIANG_VIEN)
def thesis_form(request, pk=None):
    role = current_role(request)
    # Chỉ ADMIN chọn giảng viên hướng dẫn (danh sách lấy từ Identity Service);
    # giảng viên tạo đề tài thì Thesis Service tự gán chính họ làm GVHD.
    lecturers = None
    if role == "ADMIN":
        lecturers = fetch(request, api.users.list, {"role": "LECTURER"}, default=[])

    initial = None
    if pk:
        try:
            initial = api.theses.get(pk)
        except (NotFound, ServiceUnavailable):
            messages.error(request, "Không tải được thông tin đề tài.")
            return redirect("thesis_list")
        if role == "LECTURER" and initial.get("supervisor_id") != current_user(request)["id"]:
            messages.error(request, "Bạn chỉ được sửa đề tài do mình hướng dẫn.")
            return redirect("thesis_list")

    if request.method == "POST":
        form = ThesisForm(request.POST, lecturers=lecturers)
        if form.is_valid():
            if role == "LECTURER":
                user = current_user(request)
                form.cleaned_data["supervisor"] = user.get("full_name") or user["username"]
            try:
                if pk:
                    api.theses.update(pk, form.cleaned_data)
                    messages.success(request, "Cập nhật đề tài thành công.")
                else:
                    created = api.theses.create(form.cleaned_data)
                    code = created.get("thesis_code", "") if isinstance(created, dict) else ""
                    messages.success(request, "Thêm đề tài thành công." + (f" Mã: {code}" if code else ""))
                return redirect("thesis_list")
            except ApiError as exc:
                form.add_api_errors(exc.data)
            except ServiceUnavailable as exc:
                form.add_error(None, translate_error(str(exc)))
    else:
        form = ThesisForm(initial=initial, lecturers=lecturers)

    return render(request, "portal/thesis_form.html", {
        "menu": "theses", "form": form, "is_edit": bool(pk), "record": initial,
    })


@require_POST
@role_required(QUAN_TRI, GIANG_VIEN)
def thesis_delete(request, pk):
    try:
        api.theses.delete(pk)
        messages.success(request, "Đã xóa đề tài.")
    except ApiError as exc:
        # 409: đề tài còn đăng ký hiệu lực bên Registration Service
        messages.error(request, api_error_message(exc.data))
    except NotFound:
        messages.error(request, "Đề tài không tồn tại.")
    except ServiceUnavailable as exc:
        messages.error(request, translate_error(str(exc)))
    return redirect("thesis_list")


# ---------------------------------------------------------------- Đăng ký
def attach_names(registrations, students, theses):
    """Ghép tên sinh viên / đề tài theo id (dữ liệu nằm ở 2 service khác)."""
    student_map = {s["id"]: s for s in students}
    thesis_map = {t["id"]: t for t in theses}
    # Sinh viên chỉ thấy đề tài OPEN trong danh sách -> lấy riêng đề tài đã đóng mà mình đã đăng ký
    for thesis_id in {r["thesis_id"] for r in registrations} - set(thesis_map):
        try:
            thesis_map[thesis_id] = api.theses.get(thesis_id)
        except (NotFound, ServiceUnavailable):
            pass
    for r in registrations:
        r["student"] = student_map.get(r["student_id"])
        r["thesis"] = thesis_map.get(r["thesis_id"])
        for key in ("registered_at", "processed_at", "cancelled_at"):
            if r.get(key):
                r[key] = parse_datetime(r[key])


def allowed_actions(registration, role):
    """
    Nút nào được hiện cho đăng ký này (Registration Service vẫn kiểm tra lại mọi thao tác).
      - Duyệt   : ADMIN / GVHD, đăng ký đang chờ hoặc đã bị từ chối
      - Từ chối : ADMIN / GVHD, đăng ký đang chờ hoặc đã duyệt (bắt buộc nhập lý do)
      - Hủy     : sinh viên khi còn CHỜ DUYỆT; ADMIN khi chờ duyệt / đã duyệt
      - Xóa hẳn : chỉ ADMIN
    """
    status = registration["status"]
    reviewer = role in ("ADMIN", "LECTURER")
    if role == "STUDENT":
        can_cancel = status == "PENDING"
    else:
        can_cancel = role == "ADMIN" and status in ACTIVE_STATUSES
    return {
        "can_approve": reviewer and status in ("PENDING", "REJECTED"),
        "can_reject": reviewer and status in ("PENDING", "APPROVED"),
        "can_cancel": can_cancel,
        "can_delete": role == "ADMIN",
    }


@role_required(QUAN_TRI, GIANG_VIEN, SINH_VIEN)
def registration_list(request):
    # Bộ lọc gửi thẳng sang Registration Service: ?student_id=&thesis_id=&status=
    filters = {
        key: request.GET[key]
        for key in ("student_id", "thesis_id", "status")
        if request.GET.get(key)
    }
    registrations = fetch(request, api.registrations.list, filters, default=[])
    students = fetch(request, api.students.list, default=[])
    theses = fetch(request, api.theses.list, default=[])

    attach_names(registrations, students, theses)
    role = current_role(request)
    for r in registrations:
        r.update(allowed_actions(r, role))

    return render(request, "portal/registration_list.html", {
        "menu": "registrations",
        "registrations": registrations,
        "students": students,
        "theses": theses,
        "filters": filters,
        "statuses": STATUS_LABELS,
    })


def registration_detail(request, pk):
    """Chi tiết một đăng ký + nhận xét / tiến độ của giảng viên hướng dẫn."""
    try:
        registration = api.registrations.get(pk)
    except NotFound:
        messages.error(request, "Đăng ký không tồn tại hoặc bạn không có quyền xem.")
        return redirect("registration_list")
    except ServiceUnavailable as exc:
        messages.error(request, translate_error(str(exc)))
        return redirect("registration_list")

    students = []
    if registration["student_id"] is not None:
        try:
            students = [api.students.get(registration["student_id"])]
        except (NotFound, ServiceUnavailable):
            pass
    attach_names([registration], students, [])
    role = current_role(request)
    registration.update(allowed_actions(registration, role))

    notes = fetch(request, api.list_notes, pk, default=[])
    for n in notes:
        n["created_at"] = parse_datetime(n["created_at"])

    can_add_note = role in ("ADMIN", "LECTURER") and registration["status"] == "APPROVED"
    form = ProgressNoteForm(request.POST or None) if can_add_note else None
    if request.method == "POST" and form is not None and form.is_valid():
        try:
            api.add_note(pk, form.cleaned_data)
            messages.success(request, "Đã ghi nhận xét / tiến độ.")
            return redirect("registration_detail", pk=pk)
        except ApiError as exc:
            form.add_api_errors(exc.data)
        except ServiceUnavailable as exc:
            form.add_error(None, translate_error(str(exc)))

    return render(request, "portal/registration_detail.html", {
        "menu": "registrations",
        "r": registration,
        "notes": notes,
        "form": form,
        "latest_progress": next((n["progress"] for n in notes if n["progress"] is not None), None),
    })


def back_to(request, pk):
    """Quay lại trang chi tiết nếu thao tác được bấm từ đó, ngược lại về danh sách."""
    if request.POST.get("next") == "detail":
        return redirect("registration_detail", pk=pk)
    return redirect("registration_list")


@require_POST
@role_required(QUAN_TRI, GIANG_VIEN)
def registration_status(request, pk):
    new_status = request.POST.get("status")
    data = {"status": new_status}
    if new_status == "REJECTED":
        data["reject_reason"] = request.POST.get("reject_reason", "").strip()
        if not data["reject_reason"]:
            messages.error(request, translate_error("A reason is required when rejecting."))
            return back_to(request, pk)
    try:
        api.registrations.update(pk, data)
        messages.success(request, "Đã cập nhật trạng thái đăng ký.")
    except ApiError as exc:
        messages.error(request, api_error_message(exc.data))
    except NotFound:
        messages.error(request, "Đăng ký không tồn tại.")
    except ServiceUnavailable as exc:
        messages.error(request, translate_error(str(exc)))
    return back_to(request, pk)


@require_POST
@role_required(QUAN_TRI, SINH_VIEN)
def registration_cancel(request, pk):
    """Hủy đăng ký: bản ghi vẫn còn (trạng thái CANCELLED) để giữ lịch sử."""
    try:
        api.cancel_registration(pk)
        messages.success(request, "Đã hủy đăng ký.")
    except ApiError as exc:
        messages.error(request, api_error_message(exc.data))
    except NotFound:
        messages.error(request, "Đăng ký không tồn tại.")
    except ServiceUnavailable as exc:
        messages.error(request, translate_error(str(exc)))
    return back_to(request, pk)


@require_POST
@role_required(QUAN_TRI)
def registration_delete(request, pk):
    """Xóa hẳn bản ghi (chỉ ADMIN, dùng khi nhập nhầm). Thao tác thường ngày là Hủy."""
    try:
        api.registrations.delete(pk)
        messages.success(request, "Đã xóa đăng ký.")
    except ApiError as exc:
        messages.error(request, api_error_message(exc.data))
    except NotFound:
        messages.error(request, "Đăng ký không tồn tại.")
    except ServiceUnavailable as exc:
        messages.error(request, translate_error(str(exc)))
    return redirect("registration_list")


# ---------------------------------------------------------------- Tài liệu API
@role_required(QUAN_TRI, GIANG_VIEN, SINH_VIEN)
def api_docs(request):
    services = [
        ("Student Service", "Quản lý sinh viên", settings.STUDENT_SERVICE_URL, "student_db"),
        ("Thesis Service", "Quản lý đề tài", settings.THESIS_SERVICE_URL, "thesis_db"),
        ("Registration Service", "Quản lý đăng ký", settings.REGISTRATION_SERVICE_URL, "registration_db"),
        ("Identity Service", "Đăng nhập, tài khoản, cấp JWT", settings.IDENTITY_SERVICE_URL, "auth_db"),
    ]
    rows = [
        {"name": name, "desc": desc, "url": url, "db": db, "online": api.is_online(url)}
        for name, desc, url, db in services
    ]
    return render(request, "portal/api_docs.html", {"menu": "api_docs", "services": rows})


# ---------------------------------------------------------------- Tài khoản (chỉ ADMIN)
@role_required(QUAN_TRI)
def account_list(request):
    params = {k: request.GET[k] for k in ("role", "search") if request.GET.get(k)}
    accounts = fetch(request, api.users.list, params or None, default=[])
    students = fetch(request, api.students.list, default=[])
    student_map = {s["id"]: s for s in students}
    for a in accounts:
        a["student"] = student_map.get(a["student_id"])
        a["locked"] = bool(a.get("locked_until") and parse_datetime(a["locked_until"]) > timezone.now())
    return render(request, "portal/account_list.html", {
        "menu": "accounts", "accounts": accounts, "filters": params,
        "roles": [("ADMIN", "Quản trị"), ("LECTURER", "Giảng viên"), ("STUDENT", "Sinh viên")],
    })


@role_required(QUAN_TRI)
def account_create(request):
    students = fetch(request, api.students.list, default=[])
    form = AccountForm(request.POST or None, students=students)
    if request.method == "POST" and form.is_valid():
        try:
            api.users.create(form.cleaned_data)
            messages.success(request, f"Đã tạo tài khoản {form.cleaned_data['username']}.")
            return redirect("account_list")
        except ApiError as exc:
            form.add_api_errors(exc.data)
        except ServiceUnavailable as exc:
            form.add_error(None, translate_error(str(exc)))
    return render(request, "portal/account_form.html", {"menu": "accounts", "form": form})


@require_POST
@role_required(QUAN_TRI)
def account_toggle_active(request, pk):
    activate = request.POST.get("is_active") == "true"
    try:
        api.users.update(pk, {"is_active": activate})
        messages.success(request, "Đã mở lại tài khoản." if activate else "Đã khóa tài khoản (đăng xuất mọi phiên).")
    except ApiError as exc:
        errors = [str(m) for v in exc.data.values() for m in (v if isinstance(v, list) else [v])]
        messages.error(request, translate_error(errors[0]) if errors else "Không cập nhật được tài khoản.")
    except NotFound:
        messages.error(request, "Tài khoản không tồn tại.")
    except ServiceUnavailable as exc:
        messages.error(request, translate_error(str(exc)))
    return redirect("account_list")


@require_POST
@role_required(QUAN_TRI)
def account_unlock(request, pk):
    try:
        api.unlock_user(pk)
        messages.success(request, "Đã mở khóa đăng nhập.")
    except NotFound:
        messages.error(request, "Tài khoản không tồn tại.")
    except ServiceUnavailable as exc:
        messages.error(request, translate_error(str(exc)))
    return redirect("account_list")
