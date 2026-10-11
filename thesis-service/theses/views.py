from rest_framework import filters, generics

from .models import Thesis
from .serializers import ThesisSerializer


class ThesisListCreateView(generics.ListCreateAPIView):
    queryset = Thesis.objects.all()
    serializer_class = ThesisSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = [
        "thesis_code",
        "title",
        "description",
        "supervisor",
    ]


class ThesisDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Thesis.objects.all()
    serializer_class = ThesisSerializer
