from rest_framework import serializers
from .models.item import Item
from .models.tag import Tag
from .models.link import Link
from .models.file_group import FileGroup
from .models.file import File

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name"]

class ItemSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Item
        fields = ["id", "owner", "name", "type", "date_of_origin", "tags", "created_at"]


class LinkSerializer(serializers.ModelSerializer):
    # item = ItemSerializer(read_only=True)
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())

    class Meta:
        model = Link
        fields = ["id", "item", "url"]

    def validate_item(self, value):
        # Ensure item type matches
        if value.type != "link":
            raise serializers.ValidationError("Item type must be 'link' to attach a Link.")
        return value

class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = ["id", "file_name", "file_type", "file_origin"]

    def validate_item(self, value):
        # Ensure item type matches
        if value.type != "file_group":
            raise serializers.ValidationError("Item type must be 'file_group' to attach a FileGroup.")
        return value

class FileGroupSerializer(serializers.ModelSerializer):
    # item = ItemSerializer(read_only=True)
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    files = FileSerializer(many=True, read_only=True)

    class Meta:
        model = FileGroup
        fields = ["id", "item", "description", "files"]
