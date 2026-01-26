import uuid
import os
import mimetypes
from rest_framework import viewsets, filters, status
from rest_framework.utils.urls import replace_query_param
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, filters as df_filters
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.conf import settings
from django.db.models import Count
from django.utils.encoding import smart_str
from django.http import FileResponse, Http404
from urllib.parse import urlparse, urlunparse
from .models.item import Item
from .models.tag import Tag
from .models.link import Link
from .models.media_url import MediaURL
from .models.file_group import FileGroup
from .models.file import File
from .serializers import (
    ItemSerializer, TagSerializer, LinkSerializer,
    FileGroupSerializer, FileSerializer, MediaURLSerializer
)
from utils.g_drive import upload_to_drive_oauth

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png'}

PREFILTER_TAGS = []

def force_port(url: str, port: int = 8000) -> str:
    parsed = urlparse(url)
    netloc = f"{parsed.hostname}:{port}"
    return urlunparse(parsed._replace(netloc=netloc))

class ItemPagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = "limit"
    max_page_size = 100

    def get_page_size(self, request):
        """
        - If ?limit is provided and > 0, use that (capped at max_page_size).
        - If ?limit=0, return None (disable pagination, return all items).
        - If no ?limit, return default page_size (5).
        """
        limit = request.query_params.get(self.page_size_query_param)
        if limit is None:
            return self.page_size  # default = 5
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            return self.page_size
        if limit == 0:
            return None  # disables pagination
        return min(limit, self.max_page_size)

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

    def get_queryset(self):
        if PREFILTER_TAGS:
            return Item.objects.filter(tags__name__in=PREFILTER_TAGS).distinct()
        return Item.objects.all()

    def perform_create(self, serializer):
        # normal users always get themselves as owner
        if not self.request.user.is_staff:
            serializer.save(owner=self.request.user)
        else:
            # admins can override owner if passed in payload
            serializer.save()

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="Number of items per page. If omitted, all items are returned.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "tag_names",
                openapi.IN_QUERY,
                description="Comma-separated list of tag names to filter items",
                type=openapi.TYPE_STRING,
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "tag_names",
                openapi.IN_QUERY,
                description="Comma-separated list of tag names to filter items",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "ordering",
                openapi.IN_QUERY,
                description="Ordering field, e.g. 'name' or '-created_at'",
                type=openapi.TYPE_STRING,
            ),
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "prev_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="Previous item ID"),
                    "next_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="Next item ID"),
                },
            )
        },
    )
    @action(detail=True, methods=["get"], url_path="neighbors")
    def neighbors(self, request, pk=None):
        """
        Return prev and next item IDs based on current filters and ordering.
        """
        # Apply filters
        queryset = self.filter_queryset(self.get_queryset())
        # Apply ordering if provided
        ordering = request.query_params.get("ordering")
        if ordering:
            queryset = queryset.order_by(ordering)

        ids = list(queryset.values_list("id", flat=True))
        try:
            idx = ids.index(int(pk))
        except ValueError:
            return Response({"prev_id": None, "next_id": None})

        prev_id = ids[idx - 1] if idx > 0 else None
        next_id = ids[idx + 1] if idx < len(ids) - 1 else None

        return Response({"prev_id": prev_id, "next_id": next_id})

class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Tag.objects.all()

        if PREFILTER_TAGS:
            # Get the IDs of all Items that match the premature tags
            premature_item_ids = Item.objects.filter(
                tags__name__in=PREFILTER_TAGS
            ).values_list('id', flat=True)

            # Filter the Tags to only those associated with those Items
            queryset = queryset.filter(
                items__id__in=premature_item_ids
            ).distinct()

        # Annotate the queryset with the count of associated items
        queryset = queryset.annotate(
            item_count=Count('items')
        )

        # Order the results by the calculated count in descending order
        return queryset.order_by('-item_count', 'name')

class LinkViewSet(viewsets.ModelViewSet):
    queryset = Link.objects.prefetch_related('media_urls').all()
    serializer_class = LinkSerializer
    permission_classes = [IsAuthenticated]

class MediaURLViewSet(viewsets.ModelViewSet):
    queryset = MediaURL.objects.all()
    serializer_class = MediaURLSerializer
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
    @action(detail=False, methods=["post"], url_path="upload-to-gdrive")
    def upload_to_gdrvive(self, request):
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
            if file_ext in IMAGE_EXTENSIONS:
                file_type = f"IMG_{idx}"
            elif total == 1:
                file_type = "VID_ORG"
            elif idx == total:
                file_type = "VID_ORG"
            else:
                file_type = f"VID_RAW_{idx}"

            file_obj = File.objects.create(
                file_group=file_group,
                file_name=serial_name,
                file_type=file_type,
                file_origin="gdrive",
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

    @swagger_auto_schema(
        responses={
            200: openapi.Response(
                description="Success",
                schema=openapi.Schema(type=openapi.TYPE_FILE),
            ),
        }
    )
    @action(detail=True, methods=["get"], url_path="serve", permission_classes=[AllowAny])
    def serve_file(self, request, pk=None):
        """
        Serves the file from the local GDrive Desktop path (or cache).
        """
        file_instance = self.get_object()

        file_path = os.path.join(settings.GDRIVE_LOCAL_PATH, file_instance.file_name)

        if not os.path.exists(file_path):
            # Fallback: If not on G: drive, you could trigger a download here
            # or return 404
            raise Http404("File not found on the synchronized Drive path.")

        # 2. Detect MIME type (video/mp4, image/jpeg, etc.)
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = 'application/octet-stream'

        # 3. Stream the file
        # 'as_attachment=False' allows browser/Angular to play video/show image directly
        response = FileResponse(open(file_path, 'rb'), content_type=content_type)

        # Optional: Force the filename in headers
        response['Content-Disposition'] = f'inline; filename="{smart_str(file_instance.file_name)}"'

        # This signals to the browser that the stream supports seeking.
        # NOTES: Without this, chromium browser doesn't allow seeking.
        response['Accept-Ranges'] = 'bytes'

        return response
