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

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields: List[str] = ["id", "name"]

    def validate_name(self, value: str) -> str:
        if "," in value:
            raise serializers.ValidationError("Commas are not allowed in tag names.")
        return value


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
    file_group_id = serializers.SerializerMethodField()

    # make owner optional
    owner = serializers.PrimaryKeyRelatedField(
        queryset=Item._meta.get_field("owner").related_model.objects.all(),
        required=False
    )

    class Meta:
        model = Item
        fields: List[str] = [
            "id", "owner", "name", "type", "date_of_origin",
            "tags", "tag_names", "created_at", "link_id", "file_group_id"
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
        link: Optional[Link] = Link.objects.filter(item=obj).first()
        return link.id if link else None

    def get_file_group_id(self, obj: Item) -> Optional[int]:
        file_group: Optional[FileGroup] = FileGroup.objects.filter(item=obj).first()
        return file_group.id if file_group else None


class MediaURLSerializer(serializers.ModelSerializer):
    hd_url_domain = serializers.SerializerMethodField(read_only=True)
    sd_url_domain = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MediaURL
        fields = ["id", "url", "hd_url", "hd_url_domain", "sd_url", "sd_url_domain", "media_type", "order"]

    def get_hd_url_domain(self, obj: Link) -> Optional[str]:
        if obj.url:
            parsed = urlparse(obj.url)
            return parsed.netloc.lower()
        return None

    def get_sd_url_domain(self, obj: Link) -> Optional[str]:
        if obj.url:
            parsed = urlparse(obj.url)
            return parsed.netloc.lower()
        return None

class LinkSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    media_url = serializers.CharField(read_only=True)
    url_domain = serializers.SerializerMethodField(read_only=True)
    media_url_domain = serializers.SerializerMethodField(read_only=True)

    media_urls = MediaURLSerializer(many=True, read_only=True)

    class Meta:
        model = Link
        fields: List[str] = [
            "id", 
            "item", 
            "url", 
            "url_domain", 
            "media_url",        # Old field (kept for migration)
            "media_url_domain", 
            "media_urls"
        ]

    def validate_url(self, value: str) -> str:
        try:
            # Initialize a list to hold multiple media items
            self._extracted_media = []
            # Refine the URL
            refined = refine_url(value)
            # If it's a reddit or twiiter URL, fetch media details
            parsed = urlparse(refined)
            if parsed.netloc.lower() in REDDIT_DOMAINS + TWITTER_DOMAINS:
                details = get_media_details(refined)
                if details and details.get("media"):
                    # Assuming reddit returns one for now, but we wrap it in a list
                    for each_media in details['media']:
                        self._extracted_media.append(each_media | {'url': each_media['hd_url']})

            if not self._extracted_media:
                 # Optional: raise error if you require at least one media link
                 pass 

            return refined
        except ValueError as e:
            raise serializers.ValidationError(str(e))

    def create(self, validated_data: dict) -> Link:
        # 1. Create the Link instance
        # Still populate old media_url for compatibility during migration
        if hasattr(self, "_extracted_media") and self._extracted_media:
            validated_data["media_url"] = self._extracted_media[0]["url"]

        link = super().create(validated_data)

        # 2. Create the associated MediaURL instances
        if hasattr(self, "_extracted_media"):
            media_objects = [
                MediaURL(
                    link=link,
                    url=m["url"],
                    hd_url=m["hd_url"],
                    sd_url=m["sd_url"],
                    media_type=m.get("media_type", "video"),
                    order=i
                )
                for i, m in enumerate(self._extracted_media)
            ]
            MediaURL.objects.bulk_create(media_objects)

        return link

    def update(self, instance: Link, validated_data: dict) -> Link:
        link = super().update(instance, validated_data)

        # If URL changed, replace the media links
        if hasattr(self, "_extracted_media"):
            # Clear old ones
            instance.media_urls.all().delete()
            # Create new ones
            media_objects = [
                MediaURL(
                    link=link,
                    url=m["url"],
                    hd_url=m["hd_url"],
                    sd_url=m["sd_url"],
                    media_type=m.get("media_type", "video"),
                    order=i
                )
                for i, m in enumerate(self._extracted_media)
            ]
            MediaURL.objects.bulk_create(media_objects)

        return link

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
        fields: List[str] = ["id", "file_name", "file_type", "file_origin", "file_url"]

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
