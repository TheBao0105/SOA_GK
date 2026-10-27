from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.utils import timezone


class GradingPeriod(models.Model):
    name = models.CharField(max_length=100)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    criteria = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dot_chamdiem"
        ordering = ["-id"]

    def is_open(self):
        return self.is_active and self.start_at <= timezone.now() <= self.end_at


class Assessment(models.Model):
    class Status(models.TextChoices):
        UNGRADED = "UNGRADED", "Chưa chấm"
        IN_PROGRESS = "IN_PROGRESS", "Đang chấm"
        GRADED = "GRADED", "Đã chấm"
        PUBLISHED = "PUBLISHED", "Đã công bố"

    registration = models.ForeignKey("registrations.Registration", on_delete=models.PROTECT, related_name="assessments")
    period = models.ForeignKey(GradingPeriod, on_delete=models.PROTECT, related_name="assessments")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UNGRADED)
    final_score = models.DecimalField(max_digits=4, decimal_places=2, null=True)
    published_by = models.PositiveIntegerField(null=True)
    published_at = models.DateTimeField(null=True)
    created_by = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ketqua_chamdiem"
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["registration", "period"], name="unique_registration_grading_period")]

    def recalculate(self):
        marks = list(self.assignments.all())
        submitted = [m for m in marks if m.submitted_at is not None]
        if marks and len(submitted) == len(marks):
            self.status = self.Status.GRADED
            self.final_score = (sum(m.total(self.period.criteria) for m in marks) / len(marks)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            self.status = self.Status.IN_PROGRESS if any(m.scores for m in marks) else self.Status.UNGRADED
            self.final_score = None
        self.save(update_fields=["status", "final_score"])


class GradingAssignment(models.Model):
    assessment = models.ForeignKey(Assessment, on_delete=models.PROTECT, related_name="assignments")
    lecturer_id = models.PositiveIntegerField()
    lecturer_name = models.CharField(max_length=150)
    scores = models.JSONField(default=dict)
    comment = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "phancong_chamdiem"
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["assessment", "lecturer_id"], name="unique_assessment_examiner")]

    def total(self, criteria):
        return sum((Decimal(self.scores[c["code"]]) * Decimal(str(c["weight"])) / 100 for c in criteria), Decimal(0))


class GradeEvent(models.Model):
    assessment = models.ForeignKey(Assessment, on_delete=models.PROTECT, related_name="events")
    actor_id = models.PositiveIntegerField()
    action = models.CharField(max_length=30)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "lichsu_chamdiem"
        ordering = ["-id"]
