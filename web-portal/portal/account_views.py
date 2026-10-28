"""Màn hình tài khoản/hồ sơ của Portal; toàn bộ dữ liệu tài khoản thuộc Identity Service."""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from . import api_client as api
from .api_client import ApiError, ServiceUnavailable
from .auth import SESSION_USER, role_required
from .account_forms import AccountEditForm, ProfileForm
from .view_helpers import load


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
    return render(request,"portal/account_edit_form.html",{"form":form,"title":"Hồ sơ tài khoản","menu":"profile"})


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
    return render(request,"portal/account_edit_form.html",{"menu":"accounts","form":form,"title":"Sửa tài khoản"})
