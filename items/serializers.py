from typing import List, Optional
from rest_framework import serializers
from urllib.parse import urlparse
from .models.item import Item
from .models.tag import Tag
from .models.link import Link
from .models.media_url import MediaURL
from .models.file_group import FileGroup
from .models.file import File
from utils.url_refiner import refine_url
from utils.media_extractor import get_media_details
from utils.domain_urls import REDDIT_DOMAINS, TWITTER_DOMAINS
from utils.tag_service import auto_tag_item_from_src

# --- 1. Basic Serializers ---


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields: List[str] = ["id", "name"]

    def validate_name(self, value: str) -> str:
        if "," in value:
            raise serializers.ValidationError(
                "Commas are not allowed in tag names.")
        return value


class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields: List[str] = ["id", "file_name",
                             "file_type", "file_origin", "file_url"]

# --- 2. Relationship Serializers (Moved up to be used by Item) ---


class FileGroupSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    files = FileSerializer(many=True, read_only=True)

    class Meta:
        model = FileGroup
        fields: List[str] = ["id", "item", "description", "files"]


class MediaURLSerializer(serializers.ModelSerializer):
    link = serializers.PrimaryKeyRelatedField(queryset=Link.objects.all())
    hd_url_domain = serializers.SerializerMethodField(read_only=True)
    sd_url_domain = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MediaURL
        fields = ["id", "link", "url", "hd_url", "hd_url_domain",
                  "sd_url", "sd_url_domain", "media_type", "order"]

    def _get_domain(self, url: Optional[str]) -> Optional[str]:
        if url:
            return urlparse(url).netloc.lower()
        return None

    def get_hd_url_domain(self, obj: MediaURL) -> Optional[str]:
        return self._get_domain(obj.hd_url)

    def get_sd_url_domain(self, obj: MediaURL) -> Optional[str]:
        return self._get_domain(obj.sd_url)


class LinkSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    url_domain = serializers.SerializerMethodField(read_only=True)
    media_url_domain = serializers.SerializerMethodField(read_only=True)
    media_urls = MediaURLSerializer(many=True, read_only=True)

    class Meta:
        model = Link
        fields: List[str] = [
            "id", "item", "url", "url_domain",
            "media_url", "media_url_domain", "media_urls"
        ]

    def get_url_domain(self, obj: Link) -> Optional[str]:
        return urlparse(obj.url).netloc.lower() if obj.url else None

    def get_media_url_domain(self, obj: Link) -> Optional[str]:
        return urlparse(obj.media_url).netloc.lower() if obj.media_url else None

    def validate_url(self, value: str) -> str:
        try:
            self._extracted_media = []
            refined_url_info = refine_url(value)
            refined = refined_url_info.get('url')
            parsed = urlparse(refined)
            if parsed.netloc.lower() in REDDIT_DOMAINS + TWITTER_DOMAINS:
                details = get_media_details(refined)
                if details and details.get("media"):
                    for each_media in details['media']:
                        self._extracted_media.append(
                            each_media | {'url': each_media['hd_url']})
            return refined
        except ValueError as e:
            raise serializers.ValidationError(str(e))

    def create(self, validated_data: dict) -> Link:
        if hasattr(self, "_extracted_media") and self._extracted_media:
            validated_data["media_url"] = self._extracted_media[0]["url"]
        link = super().create(validated_data)
        file_group = FileGroup.objects.filter(item=link.item).first()
        auto_tag_item_from_src(link.item, link.url, file_group)

        if hasattr(self, "_extracted_media"):
            media_objects = [
                MediaURL(link=link, url=m["url"], hd_url=m["hd_url"], sd_url=m["sd_url"],
                         media_type=m.get("media_type", "video"), order=i)
                for i, m in enumerate(self._extracted_media)
            ]
            MediaURL.objects.bulk_create(media_objects)
        return link

    def update(self, instance: Link, validated_data: dict) -> Link:
        link = super().update(instance, validated_data)
        file_group = FileGroup.objects.filter(item=link.item).first()
        auto_tag_item_from_src(link.item, link.url, file_group)

        if hasattr(self, "_extracted_media"):
            instance.media_urls.all().delete()
            media_objects = [
                MediaURL(link=link, url=m["url"], hd_url=m["hd_url"], sd_url=m["sd_url"],
                         media_type=m.get("media_type", "video"), order=i)
                for i, m in enumerate(self._extracted_media)
            ]
            MediaURL.objects.bulk_create(media_objects)
        return link

# --- 3. Main Item Serializer ---


class ItemSerializer(serializers.ModelSerializer):
    tags = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="name")
    tag_names = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=False)

    # Nested Detail Data (Read-Only)
    # Using SerializerMethodField allows us to pick just the .first() record
    link_details = serializers.SerializerMethodField()
    file_group_details = serializers.SerializerMethodField()

    link_id = serializers.SerializerMethodField()
    file_group_id = serializers.SerializerMethodField()

    owner = serializers.PrimaryKeyRelatedField(
        queryset=Item._meta.get_field("owner").related_model.objects.all(),
        required=False
    )

    class Meta:
        model = Item
        fields: List[str] = [
            "id", "owner", "name", "type", "date_of_origin",
            "tags", "tag_names", "created_at", "link_id", "file_group_id",
            "link_details", "file_group_details"
        ]

    def get_link_details(self, obj: Item) -> Optional[dict]:
        link = Link.objects.filter(item=obj).first()
        return LinkSerializer(link).data if link else None

    def get_file_group_details(self, obj: Item) -> Optional[dict]:
        fg = FileGroup.objects.filter(item=obj).first()
        return FileGroupSerializer(fg).data if fg else None

    def get_link_id(self, obj: Item) -> Optional[int]:
        link = Link.objects.filter(item=obj).only('id').first()
        return link.id if link else None

    def get_file_group_id(self, obj: Item) -> Optional[int]:
        fg = FileGroup.objects.filter(item=obj).only('id').first()
        return fg.id if fg else None

    def create(self, validated_data: dict) -> Item:
        tag_names = validated_data.pop("tag_names", [])
        if "owner" not in validated_data:
            request = self.context.get("request")
            if request and hasattr(request, "user"):
                validated_data["owner"] = request.user
        item = super().create(validated_data)
        if tag_names:
            tags = [Tag.objects.get_or_create(
                name=name)[0] for name in tag_names]
            item.tags.set(tags)
        return item

    def update(self, instance: Item, validated_data: dict) -> Item:
        tag_names = validated_data.pop("tag_names", None)
        if "owner" not in validated_data:
            request = self.context.get("request")
            if request and hasattr(request, "user"):
                validated_data["owner"] = request.user
        instance = super().update(instance, validated_data)
        if tag_names is not None:
            tags = [Tag.objects.get_or_create(
                name=name)[0] for name in tag_names]
            instance.tags.set(tags)

        link = Link.objects.filter(item=instance).first()
        file_group = FileGroup.objects.filter(item=instance).first()
        if link or file_group:
            auto_tag_item_from_src(
                instance, link.url if link else None, file_group)
        return instance

class ItemDetailResponseSerializer(ItemSerializer):
    prev_id = serializers.IntegerField(allow_null=True, read_only=True)
    next_id = serializers.IntegerField(allow_null=True, read_only=True)

    class Meta(ItemSerializer.Meta):
        # This keeps all your Item fields and appends the new ones
        fields = list(ItemSerializer.Meta.fields) + ['prev_id', 'next_id']
