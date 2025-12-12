from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models.item import Item
from .models.tag import Tag
from .models.link import Link
from .models.file_group import FileGroup
from .models.file import File
from .serializers import (
    ItemSerializer, TagSerializer, LinkSerializer,
    FileGroupSerializer, FileSerializer
)

class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    permission_classes = [IsAuthenticated]   # 👈 Only authenticated users can create/update/delete

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
