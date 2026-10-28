from django import forms
from .forms import AccountForm, BootstrapForm


class ProfileForm(BootstrapForm):
    full_name = forms.CharField(label="Họ tên", max_length=100, required=False)
    email = forms.EmailField(label="Email")


class AccountEditForm(AccountForm):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields["username"].disabled=True
        self.fields["password"].required=False
        self.fields["password"].label="Mật khẩu mới (để trống để giữ nguyên)"
