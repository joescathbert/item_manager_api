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

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name"]

class ItemSerializer(serializers.ModelSerializer):
    tags = serializers.SlugRelatedField(
        many=True,
        read_only=True,
        slug_field="name"
    )
    tag_names = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False
    )

    link_id = serializers.SerializerMethodField()
    file_id = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            "id", "owner", "name", "type", "date_of_origin",
            "tags", "tag_names", "created_at", "link_id", "file_id"
        ]

    def create(self, validated_data):
        tag_names = validated_data.pop("tag_names", [])
        item = Item.objects.create(**validated_data)
        tags = [Tag.objects.get_or_create(name=name)[0] for name in tag_names]
        item.tags.set(tags)
        return item

    def update(self, instance, validated_data):
        tag_names = validated_data.pop("tag_names", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if tag_names is not None:
            tags = [Tag.objects.get_or_create(name=name)[0] for name in tag_names]
            instance.tags.set(tags)
        return instance

    def get_link_id(self, obj):
        if obj.type == "link":
            link = Link.objects.filter(item=obj).first()
            return link.id if link else None
        return None

    def get_file_id(self, obj):
        if obj.type == "file":
            file_group = FileGroup.objects.filter(item=obj).first()
            return file_group.id if file_group else None
        return None

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
