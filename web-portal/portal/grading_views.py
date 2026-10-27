from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods
from . import api_client as api
from .api_client import ApiError, NotFound, ServiceUnavailable
from .auth import SESSION_USER, current_role, current_user, role_required
from .grading_forms import (AccountEditForm, AssessmentForm, AssignmentForm, CriterionFormSet, DEFAULT_CRITERIA,
                           GradingPeriodForm, ProfileForm, ReopenForm, ScoreForm)


def load(request, fn, *args, default=None):
    try:
        return fn(*args)
    except NotFound:
        raise Http404
    except ServiceUnavailable as exc:
        messages.error(request, str(exc))
        return default


@require_http_methods(["GET"])
def assessment_list(request):
    rows = load(request, api.assessments.list, default=[])
    students = {s["id"]: s for s in load(request, api.students.list, default=[])}
    theses = {t["id"]: t for t in load(request, api.theses.list, default=[])}
    for row in rows:
        row["student_name"] = students.get(row["student_id"], {}).get("full_name", f"Sinh viên #{row['student_id']}")
        row["thesis_title"] = theses.get(row["thesis_id"], {}).get("title", f"Đề tài #{row['thesis_id']}")
    return render(request,"portal/grading_list.html",{"menu":"grading","assessments":rows})


@role_required("ADMIN")
@require_http_methods(["GET","POST"])
def assessment_create(request):
    regs=load(request,api.registrations.list,default=[])
    periods=load(request,api.grading_periods.list,default=[])
    form=AssessmentForm(request.POST or None, registrations=regs, periods=periods)
    if request.method=="POST" and form.is_valid():
        try:
            obj=api.assessments.create(form.cleaned_data)
            return redirect("assessment_detail",pk=obj["id"])
        except ApiError as exc:
            form.add_api_errors(exc.data)
        except ServiceUnavailable as exc:
            form.add_error(None,str(exc))
    return render(request,"portal/grading_form.html",{"menu":"grading","form":form,"title":"Tạo hồ sơ chấm điểm"})


@role_required("ADMIN","LECTURER")
@require_http_methods(["GET"])
def grading_period_list(request):
    return render(request,"portal/grading_period_list.html",{"menu":"grading","periods":load(request,api.grading_periods.list,default=[])})


@role_required("ADMIN")
@require_http_methods(["GET","POST"])
def grading_period_form(request,pk=None):
    initial=load(request,api.grading_periods.get,pk) if pk else {}
    if initial is None:
        return redirect("grading_period_list")
    initial=dict(initial)
    for key in ("start_at","end_at"):
        if initial.get(key):
            initial[key]=parse_datetime(initial[key])
    form=GradingPeriodForm(request.POST or None,initial=initial)
    formset=CriterionFormSet(request.POST or None,initial=initial.get("criteria",DEFAULT_CRITERIA),prefix="criteria")
    if request.method=="POST" and form.is_valid() and formset.is_valid():
        data=form.to_api()
        data["criteria"]=[{"code":f.cleaned_data["code"],"name":f.cleaned_data["name"],"weight":str(f.cleaned_data["weight"])} for f in formset if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        try:
            if pk:
                api.grading_periods.update(pk,data)
            else:
                api.grading_periods.create(data)
            messages.success(request,"Đã lưu đợt chấm điểm.")
            return redirect("grading_period_list")
        except ApiError as exc:
            form.add_api_errors(exc.data)
        except ServiceUnavailable as exc:
            form.add_error(None,str(exc))
    return render(request,"portal/grading_form.html",{"menu":"grading","form":form,"formset":formset,"title":"Sửa đợt chấm" if pk else "Tạo đợt chấm"})


@require_http_methods(["GET","POST"])
def assessment_detail(request,pk):
    obj=load(request,api.assessments.get,pk)
    if obj is None:
        return redirect("assessment_list")
    role=current_role(request)
    user=current_user(request)
    students=load(request,api.students.list,default=[])
    theses=load(request,api.theses.list,default=[])
    obj["student_name"]=next((s["full_name"] for s in students if s["id"]==obj["student_id"]),f"Sinh viên #{obj['student_id']}")
    obj["thesis_title"]=next((t["title"] for t in theses if t["id"]==obj["thesis_id"]),f"Đề tài #{obj['thesis_id']}")
    history=load(request,api.grading_history,pk,default=[]) if role in ("ADMIN","LECTURER") else []
    lecturers=load(request,api.users.list,{"role":"LECTURER"},default=[]) if role=="ADMIN" else []
    mine=next((m for m in obj["assignments"] if m["lecturer_id"]==user["id"]),None)
    action=request.POST.get("action") if request.method=="POST" else None
    initial={"comment":(mine or {}).get("comment","")}
    initial.update({"score_"+k:v for k,v in (mine or {}).get("scores",{}).items()})
    score_form=ScoreForm(request.POST if action=="scores" else None,criteria=obj["criteria"],initial=initial)
    assign_form=AssignmentForm(request.POST if action=="assign" else None,lecturers=lecturers,initial={"lecturer_ids":[m["lecturer_id"] for m in obj["assignments"]]})
    reopen_form=ReopenForm(request.POST if action=="reopen" else None)
    if action:
        form=None
        if action=="scores" and role=="LECTURER" and mine:
            form=score_form
        elif action=="assign" and role=="ADMIN":
            form=assign_form
        elif action=="reopen" and role=="ADMIN":
            form=reopen_form
        elif action=="publish" and role=="ADMIN":
            pass
        else:
            messages.error(request,"Thao tác không hợp lệ hoặc không đủ quyền.")
            return redirect("assessment_detail",pk=pk)
        if form is None or form.is_valid():
            payload=score_form.to_api(request.POST.get("submit")=="true") if action=="scores" else (form.cleaned_data if form else {})
            try:
                api.grading_action(pk,action,payload)
                messages.success(request,"Đã cập nhật hồ sơ chấm điểm.")
                return redirect("assessment_detail",pk=pk)
            except ApiError as exc:
                if form:
                    form.add_api_errors(exc.data)
                else:
                    messages.error(request,str(exc))
            except ServiceUnavailable as exc:
                messages.error(request,str(exc))
    return render(request,"portal/grading_detail.html",{"menu":"grading","assessment":obj,"history":history,"mine":mine,"score_form":score_form,"assign_form":assign_form,"reopen_form":reopen_form})


@require_http_methods(["GET","POST"])
def profile(request):
    data=load(request,api.my_profile)
    if data is None:
        return redirect("dashboard")
    form=ProfileForm(request.POST or None,initial=data)
    if request.method=="POST" and form.is_valid():
        try:
            updated=api.my_profile(form.cleaned_data)
            session_user=dict(request.session[SESSION_USER])
            session_user["full_name"]=updated.get("full_name") or updated["username"]
            request.session[SESSION_USER]=session_user
            messages.success(request,"Đã cập nhật hồ sơ.")
            return redirect("profile")
        except ApiError as exc:
            form.add_api_errors(exc.data)
        except ServiceUnavailable as exc:
            form.add_error(None,str(exc))
    return render(request,"portal/grading_form.html",{"form":form,"title":"Hồ sơ tài khoản","menu":"profile"})


@role_required("ADMIN")
@require_http_methods(["GET"])
def audit_log_list(request):
    return render(request,"portal/audit_log_list.html",{"menu":"audit","logs":load(request,api.audit_logs,default=[])})


@role_required("ADMIN")
@require_http_methods(["GET","POST"])
def account_edit(request,pk):
    account=load(request,api.users.get,pk)
    if account is None:
        return redirect("account_list")
    students=load(request,api.students.list,default=[])
    form=AccountEditForm(request.POST or None,initial=account,students=students)
    if request.method=="POST" and form.is_valid():
        data=dict(form.cleaned_data)
        if not data.get("password"):
            data.pop("password",None)
        try:
            api.users.update(pk,data)
            messages.success(request,"Đã cập nhật tài khoản.")
            return redirect("account_list")
        except ApiError as exc:
            form.add_api_errors(exc.data)
        except ServiceUnavailable as exc:
            form.add_error(None,str(exc))
    return render(request,"portal/grading_form.html",{"menu":"accounts","form":form,"title":"Sửa tài khoản"})
