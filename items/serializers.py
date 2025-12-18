from typing import List, Optional
from rest_framework import serializers
from urllib.parse import urlparse
from .models.item import Item
from .models.tag import Tag
from .models.link import Link
from .models.file_group import FileGroup
from .models.file import File
from utils.url_refiner import refine_url
from utils.reddit_api import get_reddit_link_details

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields: List[str] = ["id", "name"]


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

    # make owner optional
    owner = serializers.PrimaryKeyRelatedField(
        queryset=Item._meta.get_field("owner").related_model.objects.all(),
        required=False
    )

    class Meta:
        model = Item
        fields: List[str] = [
            "id", "owner", "name", "type", "date_of_origin",
            "tags", "tag_names", "created_at", "link_id", "file_id"
        ]

    def create(self, validated_data: dict) -> Item:
        tag_names: List[str] = validated_data.pop("tag_names", [])
        # inject request.user if owner not provided
        if "owner" not in validated_data:
            request = self.context.get("request")
            if request and hasattr(request, "user"):
                validated_data["owner"] = request.user
        item: Item = Item.objects.create(**validated_data)
        tags: List[Tag] = [Tag.objects.get_or_create(name=name)[0] for name in tag_names]
        item.tags.set(tags)
        return item

    def update(self, instance: Item, validated_data: dict) -> Item:
        tag_names: Optional[List[str]] = validated_data.pop("tag_names", None)
        # same logic if you want to allow defaulting owner on update
        if "owner" not in validated_data:
            request = self.context.get("request")
            if request and hasattr(request, "user"):
                validated_data["owner"] = request.user
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if tag_names is not None:
            tags: List[Tag] = [Tag.objects.get_or_create(name=name)[0] for name in tag_names]
            instance.tags.set(tags)
        return instance

    def get_link_id(self, obj: Item) -> Optional[int]:
        if obj.type == "link":
            link: Optional[Link] = Link.objects.filter(item=obj).first()
            return link.id if link else None
        return None

    def get_file_id(self, obj: Item) -> Optional[int]:
        if obj.type == "file":
            file_group: Optional[FileGroup] = FileGroup.objects.filter(item=obj).first()
            return file_group.id if file_group else None
        return None


class LinkSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    media_url = serializers.CharField(read_only=True)
    url_domain = serializers.SerializerMethodField(read_only=True)
    media_url_domain = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Link
        fields: List[str] = ["id", "item", "url", "url_domain", "media_url", "media_url_domain"]

    def validate_item(self, value: Item) -> Item:
        if value.type != "link":
            raise serializers.ValidationError("Item type must be 'link' to attach a Link.")
        return value

    def validate_url(self, value: str) -> str:
        try:
            refined = refine_url(value)

            # If it's a reddit URL, fetch media details
            parsed = urlparse(refined)
            if parsed.netloc.lower() in ["www.reddit.com", "reddit.com"]:
                details = get_reddit_link_details(refined)
                if not details or not details.get("url"):
                    raise serializers.ValidationError("Could not extract media URL from Reddit link.")
                # stash media_url into serializer context so we can save it later
                self._media_url = details["url"]

            return refined
        except ValueError as e:
            raise serializers.ValidationError(str(e))

    def create(self, validated_data: dict) -> Link:
        if hasattr(self, "_media_url"):
            validated_data["media_url"] = self._media_url
        return super().create(validated_data)

    def update(self, instance: Link, validated_data: dict) -> Link:
        if hasattr(self, "_media_url"):
            validated_data["media_url"] = self._media_url
        return super().update(instance, validated_data)

    def get_url_domain(self, obj: Link) -> Optional[str]:
        if obj.url:
            parsed = urlparse(obj.url)
            return parsed.netloc.lower()
        return None

    def get_media_url_domain(self, obj: Link) -> Optional[str]:
        if obj.media_url:
            parsed = urlparse(obj.media_url)
            return parsed.netloc.lower()
        return None


class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields: List[str] = ["id", "file_name", "file_type", "file_origin"]

    def validate_item(self, value: Item) -> Item:
        if value.type != "file_group":
            raise serializers.ValidationError("Item type must be 'file_group' to attach a FileGroup.")
        return value


class FileGroupSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    files = FileSerializer(many=True, read_only=True)

    class Meta:
        model = FileGroup
        fields: List[str] = ["id", "item", "description", "files"]
