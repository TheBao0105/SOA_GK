from rest_framework.routers import DefaultRouter
from .views import AssessmentViewSet, GradingPeriodViewSet

router = DefaultRouter()
router.register("periods", GradingPeriodViewSet, basename="grading-period")
router.register("assessments", AssessmentViewSet, basename="assessment")
urlpatterns = router.urls
