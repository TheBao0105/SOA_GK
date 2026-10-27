from django import forms
from django.forms import formset_factory
from .forms import AccountForm, BootstrapForm, PeriodForm

DEFAULT_CRITERIA = [
    {"code":"completion", "name":"Mức độ hoàn thành và chức năng", "weight":40},
    {"code":"engineering", "name":"Kiến trúc và chất lượng kỹ thuật", "weight":30},
    {"code":"documentation", "name":"Báo cáo, tài liệu và kiểm thử", "weight":20},
    {"code":"presentation", "name":"Trình bày và trả lời câu hỏi", "weight":10},
]


class GradingPeriodForm(PeriodForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields["max_active_per_student"]


class CriterionForm(BootstrapForm):
    code = forms.RegexField(r"^[a-z][a-z0-9_]{0,29}$", label="Mã tiêu chí", max_length=30)
    name = forms.CharField(label="Tiêu chí", max_length=150)
    weight = forms.DecimalField(label="Trọng số (%)", min_value=0.01, max_value=100, decimal_places=2, max_digits=5)


CriterionFormSet = formset_factory(CriterionForm, extra=1, can_delete=True, max_num=30, validate_max=True)


class AssessmentForm(BootstrapForm):
    registration = forms.TypedChoiceField(label="Đăng ký đã duyệt", coerce=int)
    period = forms.TypedChoiceField(label="Đợt chấm", coerce=int)

    def __init__(self, *args, registrations=(), periods=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["registration"].choices = [(r["id"], f"Đăng ký #{r['id']} — SV #{r['student_id']} / đề tài #{r['thesis_id']}") for r in registrations if r["status"] == "APPROVED"]
        self.fields["period"].choices = [(p["id"], p["name"]) for p in periods]


class AssignmentForm(BootstrapForm):
    lecturer_ids = forms.TypedMultipleChoiceField(label="Giảng viên chấm (chọn một hoặc nhiều)", coerce=int, widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, lecturers=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lecturer_ids"].choices = [(u["id"], u.get("full_name") or u["username"]) for u in lecturers if u.get("is_active")]


class ScoreForm(BootstrapForm):
    comment = forms.CharField(label="Nhận xét", required=False, max_length=5000, widget=forms.Textarea(attrs={"rows":3}))

    def __init__(self, *args, criteria=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.criteria = criteria
        for c in criteria:
            self.fields["score_"+c["code"]] = forms.DecimalField(label=f"{c['name']} ({c['weight']}%)", min_value=0, max_value=10, max_digits=4, decimal_places=2, required=False, widget=forms.NumberInput(attrs={"class":"form-control", "step":"0.01"}))

    def to_api(self, submit):
        scores = {c["code"]:str(self.cleaned_data["score_"+c["code"]]) for c in self.criteria if self.cleaned_data.get("score_"+c["code"]) is not None}
        return {"scores":scores,"comment":self.cleaned_data["comment"],"submit":submit}


class ReopenForm(BootstrapForm):
    reason = forms.CharField(label="Lý do mở lại / thu hồi công bố", max_length=500)


class ProfileForm(BootstrapForm):
    full_name = forms.CharField(label="Họ tên", max_length=100, required=False)
    email = forms.EmailField(label="Email")


class AccountEditForm(AccountForm):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields["username"].disabled=True
        self.fields["password"].required=False
        self.fields["password"].label="Mật khẩu mới (để trống để giữ nguyên)"
