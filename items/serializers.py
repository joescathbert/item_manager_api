from typing import List, Optional
from rest_framework import serializers
from urllib.parse import urlparse
from .models.item import Item
from .models.tag import Tag
from .models.link import Link
from .models.file_group import FileGroup
from .models.file import File

def refine_twitter_url(raw_url: str) -> str:
    """
    Normalize Twitter/X URLs to https://twitter.com/<username>/status/<id>.
    Raises ValueError if format is invalid.
    """
    parsed = urlparse(raw_url.strip())

    path_parts: List[str] = parsed.path.strip("/").split("/")
    if len(path_parts) < 3 or path_parts[1] != "status":
        raise ValueError("URL must be in the format /<username>/status/<id>")

    user_name: str = path_parts[0]
    status_id: str = path_parts[2]

    if not status_id.isdigit():
        raise ValueError("Status ID must be numeric.")

    return f"https://twitter.com/{user_name}/status/{status_id}"

def refine_reddit_url(raw_url: str) -> str:
    """
    Normalize Reddit URLs to https://www.reddit.com/r/<subreddit>/comments/<post_id>.
    Raises ValueError if format is invalid.
    """
    parsed = urlparse(raw_url.strip())

    path_parts: List[str] = parsed.path.strip("/").split("/")
    # Expected: ["r", "<subreddit>", "comments", "<post_id>", ...]
    if len(path_parts) < 4 or path_parts[0] != "r" or path_parts[2] != "comments":
        raise ValueError("URL must be in the format /r/<subreddit>/comments/<post_id>")

    subreddit: str = path_parts[1]
    post_id: str = path_parts[3]

    # Reddit post IDs are alphanumeric (not purely digits like Twitter IDs)
    if not post_id.isalnum():
        raise ValueError("Post ID must be alphanumeric.")

    return f"https://www.reddit.com/r/{subreddit}/comments/{post_id}"

def refine_url(raw_url: str) -> str:
    """
    Dispatches to the correct refiner based on domain.
    """
    parsed = urlparse(raw_url.strip())
    domain = parsed.netloc.lower()

    if domain in ["x.com", "twitter.com"]:
        return refine_twitter_url(raw_url)
    elif domain in ["www.reddit.com", "reddit.com"]:
        return refine_reddit_url(raw_url)
    else:
        raise ValueError("Unsupported domain. Only Twitter/X and Reddit are allowed.")


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
    domain_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Link
        fields: List[str] = ["id", "item", "url", "domain_name"]

    def validate_item(self, value: Item) -> Item:
        if value.type != "link":
            raise serializers.ValidationError("Item type must be 'link' to attach a Link.")
        return value

    def validate_url(self, value: str) -> str:
        try:
            return refine_url(value)
        except ValueError as e:
            raise serializers.ValidationError(str(e))

    def get_domain_name(self, obj: Link) -> Optional[str]:
        if obj.url:
            parsed = urlparse(obj.url)
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
