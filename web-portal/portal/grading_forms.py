from django import forms
from .forms import BootstrapForm


class GradeForm(BootstrapForm):
    score = forms.DecimalField(label="Điểm (0–10)", min_value=0, max_value=10, max_digits=4, decimal_places=2,
                               widget=forms.NumberInput(attrs={"step":"0.01"}))
    comment = forms.CharField(label="Nhận xét", required=False, max_length=5000, widget=forms.Textarea(attrs={"rows":3}))
