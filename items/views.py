import uuid
import os
import mimetypes
from rest_framework import viewsets, filters, status
from rest_framework.utils.urls import replace_query_param
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, filters as df_filters
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.conf import settings
from django.db.models import Count, Value, Q
from django.db.models.functions import Substr, StrIndex
from django.utils.encoding import smart_str
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from urllib.parse import urlparse, urlunparse
from .models.item import Item
from .models.tag import Tag
from .models.link import Link
from .models.media_url import MediaURL
from .models.file_group import FileGroup
from .models.file import File
from .serializers import (
    ItemSerializer, TagSerializer, LinkSerializer,
    FileGroupSerializer, FileSerializer, MediaURLSerializer, ItemDetailResponseSerializer
)
from utils.g_drive import upload_to_drive_oauth
from utils.g_drive_authentication import create_oauth_flow, save_credentials
from utils.tag_service import auto_tag_item_from_src

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png'}

PREFILTER_TAGS = []


def force_port(url: str, port: int = 8000) -> str:
    parsed = urlparse(url)
    netloc = f"{parsed.hostname}:{port}"
    return urlunparse(parsed._replace(netloc=netloc))


@api_view(['GET'])
@permission_classes([AllowAny])
def gdrive_auth_url(request):
    redirect_uri = request.build_absolute_uri(reverse('gdrive-oauth-callback'))
    flow = create_oauth_flow(redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return redirect(auth_url)


@api_view(['GET'])
@permission_classes([AllowAny])
def gdrive_oauth_callback(request):
    redirect_uri = request.build_absolute_uri(reverse('gdrive-oauth-callback'))
    flow = create_oauth_flow(redirect_uri)
    flow.fetch_token(authorization_response=request.build_absolute_uri())
    creds = flow.credentials
    save_credentials(creds)
    return HttpResponse(
        '<html><body><h1>Google Drive connected</h1><p>You may close this window.</p>'
        '<script>window.close();</script></body></html>'
    )


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
            qs = Item.objects.filter(tags__name__in=PREFILTER_TAGS).distinct()
        else:
            qs = Item.objects.all()

        return qs.select_related('owner').prefetch_related(
            'tags',
            'link__media_urls',
            'file_group__files'
        )

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "tag_names",
                openapi.IN_QUERY,
                description="Comma-separated list of tag names to calculate neighbors correctly",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "ordering",
                openapi.IN_QUERY,
                description="Ordering field (e.g. '-created_at') to determine neighbor sequence",
                type=openapi.TYPE_STRING,
            ),
        ],
        responses={
            200: ItemDetailResponseSerializer()
        }
    )
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        # filter_queryset automatically looks at request.query_params
        queryset = self.filter_queryset(self.get_queryset())

        # IDs for the neighbor calculation
        ids = list(queryset.values_list("id", flat=True))

        try:
            idx = ids.index(instance.id)
            prev_id = ids[idx - 1] if idx > 0 else None
            next_id = ids[idx + 1] if idx < len(ids) - 1 else None
        except ValueError:
            prev_id = None
            next_id = None

        serializer = self.get_serializer(instance)
        data = serializer.data
        data['prev_id'] = prev_id
        data['next_id'] = next_id

        return Response(data)

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
            # Get the IDs of all Items that match the prefilter tags
            prefilter_item_ids = Item.objects.filter(
                tags__name__in=PREFILTER_TAGS
            ).values_list('id', flat=True)

            # Filter the Tags to only those associated with those Items
            queryset = queryset.filter(
                items__id__in=prefilter_item_ids
            ).distinct()

        # Annotate the queryset with the count of associated items
        queryset = queryset.annotate(
            item_count=Count('items')
        )

        # Order the results by the calculated count in descending order
        return queryset.order_by('-item_count', 'name')

    @swagger_auto_schema(
        method='get',
        operation_description="Extracts and returns a unique list of categories from tags formatted as <category>-<value>.",
        responses={
            200: openapi.Response(
                description="A list of unique category strings.",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_STRING, example="color")
                )
            )
        }
    )
    @action(detail=False, methods=['get'], url_path='categories')
    def get_categories(self, request):
        """
        Extracts and returns a list of unique categories 
        from the tags matching the <category>-<value> format.
        """
        # 1. Reuse your existing filtered/annotated queryset
        queryset = self.get_queryset().order_by()

        # 2. Filter for tags that actually contain a hyphen to avoid errors
        queryset = queryset.filter(name__contains='-')

        # 3. Use Django DB functions to split the string at the first hyphen
        # StrIndex finds the 1-based position of '-'. Substr grabs everything before it.
        categories_queryset = queryset.annotate(
            category=Substr('name', 1, StrIndex('name', Value('-')) - 1)
        ).values_list('category', flat=True).distinct()

        # 4. Convert the queryset to a clean list and return it
        categories_list = sorted(list(categories_queryset))

        return Response(categories_list)

    @swagger_auto_schema(
        method='get',
        operation_description="Extracts and returns a unique list of values, item counts, and full names for a given category. Can be filtered by associated item tags.",
        manual_parameters=[
            openapi.Parameter(
                'category',
                openapi.IN_QUERY,
                description="Category name for which values need to be fetched",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'tag_names',
                openapi.IN_QUERY,
                description="Comma-separated list of tag names to filter items before counting values",
                type=openapi.TYPE_STRING,
                required=False
            ),
        ],
        responses={
            200: openapi.Response(
                description="A list of objects containing the value, item count, and full tag name.",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'name': openapi.Schema(type=openapi.TYPE_STRING, example="color-red"),
                            'value': openapi.Schema(type=openapi.TYPE_STRING, example="red"),
                            'item_count': openapi.Schema(type=openapi.TYPE_INTEGER, example=15)
                        }
                    )
                )
            )
        }
    )
    @action(detail=False, methods=['get'], url_path='category-values')
    def get_category_values(self, request):
        category = request.query_params.get('category')
        if not category:
            return Response({"error": "Category parameter is required."}, status=400)

        # 1. Scope global prefilters safely up front
        if PREFILTER_TAGS:
            valid_items = Item.objects.filter(tags__name__in=PREFILTER_TAGS).distinct()
        else:
            valid_items = Item.objects.all()

        tag_names_param = request.query_params.get('tag_names')
        target_tag_names = []

        if tag_names_param:
            # Clean up input names
            target_tag_names = [n.strip() for n in tag_names_param.split(",") if n.strip()]
            total_target_tags = len(target_tag_names)

            # Step A: Find items matching ALL requested tags using integer counts (Saves SSD)
            # This generates ONE query with a HAVING clause, avoiding looping JOIN chains
            matching_item_ids = list(
                valid_items.filter(tags__name__in=target_tag_names)
                .annotate(match_count=Count('tags'))
                .filter(match_count=total_target_tags)
                .values_list('id', flat=True)
            )

            # If no items match the intersection, abort early without hammering the database
            if not matching_item_ids:
                return Response([])

            # Step B: Get relevant tags. Evaluate filtering against a static Python array of raw IDs.
            queryset = Tag.objects.filter(
                name__startswith=f"{category}-",
                items__id__in=matching_item_ids
            ).annotate(
                item_count=Count('items', filter=Q(items__id__in=matching_item_ids))
            ).values('name', 'item_count').distinct()

        else:
            # No user filters applied: Just fetch tags tied to global prefilters
            if PREFILTER_TAGS:
                # Force evaluate into memory so the database subquery isn't complex
                prefilter_item_ids = list(valid_items.values_list('id', flat=True))
                
                if not prefilter_item_ids:
                    return Response([])

                queryset = Tag.objects.filter(
                    name__startswith=f"{category}-",
                    items__id__in=prefilter_item_ids
                ).annotate(
                    item_count=Count('items', filter=Q(items__id__in=prefilter_item_ids))
                ).values('name', 'item_count').distinct()
            else:
                # Completely unbound fallback
                queryset = Tag.objects.filter(
                    name__startswith=f"{category}-"
                ).annotate(
                    item_count=Count('items')
                ).values('name', 'item_count').distinct()

        # 2. Process light data frame in memory 
        category_values_list = []
        prefix_len = len(category) + 1

        for item in queryset:
            if item["name"] not in target_tag_names:
                category_values_list.append({
                    "name": item['name'],
                    "item_count": item['item_count'],
                    "value": item['name'][prefix_len:]
                })

        category_values_list.sort(key=lambda x: (-x['item_count'], x['name']))
        return Response(category_values_list)


class LinkViewSet(viewsets.ModelViewSet):
    queryset = Link.objects.prefetch_related('media_urls').all()
    serializer_class = LinkSerializer
    permission_classes = [IsAuthenticated]

    def perform_destroy(self, instance):
        item = instance.item
        file_group = FileGroup.objects.filter(item=item).first()

        instance.delete()

        auto_tag_item_from_src(item, None, file_group)


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
            openapi.Parameter(
                "file_types",
                openapi.IN_FORM,
                description="File types corresponding to each file (optional; if not provided, defaults to extension-based logic). Must match the order of 'files'.",
                type=openapi.TYPE_ARRAY,
                items=openapi.Items(type=openapi.TYPE_STRING),
                required=True,
            ),
        ],
        consumes=["multipart/form-data"],
        responses={201: FileGroupSerializer},
    )
    @action(detail=False, methods=["post"], url_path="upload-to-gdrive")
    def upload_to_gdrive(self, request):
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
        # if item.type != "file_group":
        #     return Response({"error": "Item type must be 'file_group'"}, status=status.HTTP_400_BAD_REQUEST)

        # Step 3: Create FileGroup (or reuse if already exists)
        file_group, created = FileGroup.objects.get_or_create(
            item=item,
            defaults={"description": request.data.get("description", "")}
        )

        # Step 4: Handle files and file types
        uploaded_files = request.FILES.getlist("files")
        raw_file_types = request.data.getlist("file_types")

        if raw_file_types and len(raw_file_types) == 1 and "," in raw_file_types[0]:
            file_types = [t.strip() for t in raw_file_types[0].split(",")]
        else:
            file_types = raw_file_types

        total = len(uploaded_files)
        created_files = []

        file_type_count = {"RAW": 0, "ORG": 0, "BON": 0}
        for idx, f in enumerate(uploaded_files, start=1):
            # Generate serial-like filename
            _, file_ext = os.path.splitext(f.name)
            serial_name = f"{uuid.uuid4().hex}{file_ext}"

            # Upload to Google Drive (placeholder)
            drive_url = upload_to_drive_oauth(f, serial_name)

            # File type logic: Use provided file_type if available, else default
            if idx - 1 < len(file_types) and file_types[idx - 1]:
                prefix = "IMG" if file_ext in IMAGE_EXTENSIONS else "VID"
                file_t = file_types[idx - 1]
                file_type_count[file_t] += 1
                suffix = file_type_count[file_t]
                file_type = f"{prefix}_{file_t}_{suffix}"
            else:
                # Fallback to existing logic
                if file_ext in IMAGE_EXTENSIONS:
                    file_type = f"IMG_{idx}"
                elif total == 1 or idx == total:
                    file_type = "VID_ORG_{idx}"
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

        # We trigger this ONLY ONCE after all files are added to the group.
        link = Link.objects.filter(item=item).first()
        link_url = link.url if link else None

        auto_tag_item_from_src(item, link_url, file_group)

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

        file_path = os.path.join(
            settings.GDRIVE_LOCAL_PATH, file_instance.file_name)

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
        response = FileResponse(open(file_path, 'rb'),
                                content_type=content_type)

        # Optional: Force the filename in headers
        response['Content-Disposition'] = f'inline; filename="{smart_str(file_instance.file_name)}"'

        # This signals to the browser that the stream supports seeking.
        # NOTES: Without this, chromium browser doesn't allow seeking.
        response['Accept-Ranges'] = 'bytes'

        return response
