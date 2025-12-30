from rest_framework import viewsets
from rest_framework import filters
from rest_framework.utils.urls import replace_query_param
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, filters as df_filters
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .models.item import Item
from .models.tag import Tag
from .models.link import Link
from .models.file_group import FileGroup
from .models.file import File
from .serializers import (
    ItemSerializer, TagSerializer, LinkSerializer,
    FileGroupSerializer, FileSerializer
)
from django.conf import settings
from urllib.parse import urlparse, urlunparse

def force_port(url: str, port: int = 8000) -> str:
    parsed = urlparse(url)
    netloc = f"{parsed.hostname}:{port}"
    return urlunparse(parsed._replace(netloc=netloc))

class ItemPagination(PageNumberPagination):
    page_size = 5

    # Overrides the get_full_url method
    def get_next_link(self):
        if not self.page.has_next():
            return None
        url = self.request.build_absolute_uri()
        url = force_port(url, settings.DJANGO_PORT)
        return replace_query_param(url, self.page_query_param, self.page.next_page_number())

    def get_previous_link(self):
        if not self.page.has_previous():
            return None
        url = self.request.build_absolute_uri()
        url = force_port(url, settings.DJANGO_PORT)
        return replace_query_param(url, self.page_query_param, self.page.previous_page_number())

class ItemFilter(FilterSet):
    tag_names = df_filters.CharFilter(method="filter_tag_names")

    def filter_tag_names(self, queryset, name, value):
        names = [n.strip() for n in value.split(",") if n.strip()]
        for tag in names:
            queryset = queryset.filter(tags__name=tag)
        return queryset.distinct()

    class Meta:
        model = Item
        fields = []


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    pagination_class = ItemPagination
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ItemFilter
    ordering_fields = ["created_at", "name"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        # ✅ normal users always get themselves as owner
        if not self.request.user.is_staff:
            serializer.save(owner=self.request.user)
        else:
            # ✅ admins can override owner if passed in payload
            serializer.save()

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "tag_names",
                openapi.IN_QUERY,
                description="Comma-separated list of tag names to filter items",
                type=openapi.TYPE_STRING,
            ),
        ]
    )

    def list(self, request, *args, **kwargs):
        return super().list(request, *args,)

class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]

class LinkViewSet(viewsets.ModelViewSet):
    queryset = Link.objects.all()
    serializer_class = LinkSerializer
    permission_classes = [IsAuthenticated]

class FileGroupViewSet(viewsets.ModelViewSet):
    queryset = FileGroup.objects.all()
    serializer_class = FileGroupSerializer
    permission_classes = [IsAuthenticated]

class FileViewSet(viewsets.ModelViewSet):
    queryset = File.objects.all()
    serializer_class = FileSerializer
    permission_classes = [IsAuthenticated]
