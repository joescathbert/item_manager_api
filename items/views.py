import uuid
import os
from rest_framework import viewsets, filters, status
from rest_framework.utils.urls import replace_query_param
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, filters as df_filters
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.conf import settings
from urllib.parse import urlparse, urlunparse
from .models.item import Item
from .models.tag import Tag
from .models.link import Link
from .models.file_group import FileGroup
from .models.file import File
from .serializers import (
    ItemSerializer, TagSerializer, LinkSerializer,
    FileGroupSerializer, FileSerializer
)
from utils.g_drive import upload_to_drive_oauth

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

    # def get_queryset(self): # ✅ Only return items with tag "content" by default
    #     return Item.objects.filter(tags__name__in=["content-p", "content-m"]).distinct()

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

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "files",
                openapi.IN_FORM,
                description="Multiple files to upload",
                type=openapi.TYPE_ARRAY,
                items=openapi.Items(type=openapi.TYPE_FILE),
                required=True,
            ),
            openapi.Parameter(
                "description",
                openapi.IN_FORM,
                description="Description of the FileGroup",
                type=openapi.TYPE_STRING,
            ),
        ],
        consumes=["multipart/form-data"],
        responses={201: FileGroupSerializer},
    )
    @action(detail=False, methods=["post"], url_path="upload-multiple")
    def upload_multiple(self, request):
        """
        Upload multiple files, attach them to an existing Item of type 'file_group'.
        """
        # Step 1: Get item_id from request
        item_id = request.data.get("item")
        if not item_id:
            return Response({"error": "item_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item = Item.objects.get(id=item_id)
        except Item.DoesNotExist:
            return Response({"error": "Item not found"}, status=status.HTTP_404_NOT_FOUND)

        # Step 2: Validate item type
        if item.type != "file_group":
            return Response({"error": "Item type must be 'file_group'"}, status=status.HTTP_400_BAD_REQUEST)

        # Step 3: Create FileGroup (or reuse if already exists)
        file_group, created = FileGroup.objects.get_or_create(
            item=item,
            defaults={"description": request.data.get("description", "")}
        )

        # Step 4: Handle files
        uploaded_files = request.FILES.getlist("files")
        total = len(uploaded_files)
        created_files = []

        for idx, f in enumerate(uploaded_files, start=1):
            # Generate serial-like filename
            _, file_ext = os.path.splitext(f.name)
            serial_name = f"{uuid.uuid4().hex}{file_ext}"

            # Upload to Google Drive (placeholder)
            drive_url = upload_to_drive_oauth(f, serial_name)

            # File type logic
            if total == 1:
                file_type = "ORG"
            elif idx == total:
                file_type = "ORG"
            else:
                file_type = f"RAW_{idx}"

            file_obj = File.objects.create(
                file_group=file_group,
                file_name=serial_name,
                file_type=file_type,
                file_origin="upload",
                file_url=drive_url
            )
            created_files.append(file_obj)

        return Response(
            FileGroupSerializer(file_group).data,
            status=status.HTTP_201_CREATED
        )

class FileViewSet(viewsets.ModelViewSet):
    queryset = File.objects.all()
    serializer_class = FileSerializer
    permission_classes = [IsAuthenticated]
