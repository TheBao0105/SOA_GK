from rest_framework import filters, generics

from .models import Thesis
from .serializers import ThesisSerializer


class ThesisListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/theses/            -> danh sách đề tài
    GET  /api/theses/?search=... -> tìm kiếm (mã, tên, mô tả, GVHD)
    POST /api/theses/            -> tạo đề tài
    """

    queryset = Thesis.objects.all()
    serializer_class = ThesisSerializer
    filter_backends = [filters.SearchFilter]
    # "__unaccent": tìm "quan ly" vẫn ra "quản lý" (hàm unaccent của PostgreSQL)
    search_fields = [
        "thesis_code",
        "title",
        "title__unaccent",
        "description",
        "description__unaccent",
        "supervisor",
        "supervisor__unaccent",
    ]


class ThesisDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/theses/{id}/ -> chi tiết (Registration Service gọi API này)
    PUT    /api/theses/{id}/ -> cập nhật toàn bộ
    PATCH  /api/theses/{id}/ -> cập nhật một phần (vd: đóng đề tài)
    DELETE /api/theses/{id}/ -> xóa
    """

    queryset = Thesis.objects.all()
    serializer_class = ThesisSerializer
