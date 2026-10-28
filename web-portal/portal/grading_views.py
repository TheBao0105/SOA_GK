from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from . import api_client as api
from .api_client import ApiError, NotFound, ServiceUnavailable
from .auth import current_role, role_required
from .grading_forms import GradeForm
from .view_helpers import load


def attach_grade_names(request, rows):
    students = {s["id"]: s for s in load(request, api.students.list, default=[])}
    theses = {t["id"]: t for t in load(request, api.theses.list, default=[])}
    for row in rows:
        row["student_name"] = students.get(row["student_id"], {}).get("full_name", f"Sinh viên #{row['student_id']}")
        row["thesis_title"] = theses.get(row["thesis_id"], {}).get("title", f"Đề tài #{row['thesis_id']}")


@require_http_methods(["GET"])
def grade_list(request):
    registrations = load(request, api.registrations.list, {"status":"APPROVED"}, default=[])
    grades = load(request, api.grades.list, default=[])
    by_registration = {g["registration"]: g for g in grades}
    rows = [{**r, "grade":by_registration.get(r["id"])} for r in registrations]
    attach_grade_names(request, rows)
    return render(request, "portal/grading_list.html", {"menu":"grading", "rows":rows})


@role_required("ADMIN", "LECTURER")
@require_http_methods(["GET","POST"])
def grade_edit(request, pk):
    registration = load(request, api.registrations.get, pk)
    if registration is None:
        return redirect("grade_list")
    if registration["status"] != "APPROVED":
        messages.error(request, "Chỉ chấm đăng ký đã được duyệt.")
        return redirect("grade_list")
    grades = load(request, api.grades.list)
    if grades is None:
        return redirect("grade_list")
    grade = next((g for g in grades if g["registration"] == pk), None)
    form = GradeForm(request.POST if request.method == "POST" else None, initial=grade or {})
    if request.method == "POST" and form.is_valid():
        try:
            api.grades.create({"registration":pk, "score":str(form.cleaned_data["score"]), "comment":form.cleaned_data["comment"]})
            messages.success(request, "Đã lưu điểm. Sinh viên có thể xem kết quả ngay.")
            return redirect("grade_list")
        except ApiError as exc:
            form.add_api_errors(exc.data)
        except ServiceUnavailable as exc:
            form.add_error(None, str(exc))
    attach_grade_names(request, [registration])
    return render(request, "portal/grade_edit.html", {"menu":"grading", "registration":registration, "form":form})


@role_required("ADMIN", "LECTURER", "STUDENT")
@require_http_methods(["GET"])
def grade_detail(request, pk):
    registration = load(request, api.registrations.get, pk)
    if registration is None:
        return redirect("grade_list")
    grades = load(request, api.grades.list)
    if grades is None:
        return redirect("grade_list")
    grade = next((g for g in grades if g["registration"] == pk), None)
    history = load(request, api.grade_history, grade["id"], default=[]) if grade and current_role(request) in ("ADMIN", "LECTURER") else []
    attach_grade_names(request, [registration])
    return render(request, "portal/grade_detail.html", {"menu":"grading", "registration":registration, "grade":grade, "history":history})


@role_required("ADMIN", "LECTURER")
@require_http_methods(["GET","POST"])
def grade_delete(request, pk):
    registration = load(request, api.registrations.get, pk)
    if registration is None:
        return redirect("grade_list")
    grades = load(request, api.grades.list)
    if grades is None:
        return redirect("grade_list")
    grade = next((g for g in grades if g["registration"] == pk), None)
    if grade is None:
        messages.warning(request, "Đăng ký này chưa có điểm hoặc điểm đã được xóa.")
        return redirect("grade_list")
    if request.method == "POST":
        try:
            api.grades.delete(grade["id"])
            messages.success(request, "Đã xóa điểm. Có thể chấm lại; lịch sử thay đổi vẫn được giữ.")
            return redirect("grade_list")
        except NotFound:
            messages.warning(request, "Điểm đã được xóa.")
            return redirect("grade_list")
        except ApiError as exc:
            messages.error(request, str(exc))
        except ServiceUnavailable as exc:
            messages.error(request, str(exc))
    attach_grade_names(request, [registration])
    return render(request, "portal/grade_delete.html", {"menu":"grading", "registration":registration, "grade":grade})
