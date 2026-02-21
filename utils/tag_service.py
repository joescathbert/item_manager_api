from items.models.tag import Tag
from utils.url_refiner import refine_url

def tags_for_url(url):
    if url is None:
        return []

    refined_url_info = refine_url(url)

    src_url_auto_tags = []

    # 1. Site name tag
    site_name = refined_url_info.get('url_site_name')
    if site_name:
        src_url_auto_tags.append(f"src-{site_name}")

    # 2. Host/User tags
    post_host = refined_url_info.get('post_host')
    post_host_name = refined_url_info.get('post_host_name')

    if post_host == 'r':
        src_url_auto_tags.append(f"subreddit-{post_host_name}")
    elif post_host and post_host_name:
        src_url_auto_tags.append(f"{post_host}-{post_host_name}")

    return src_url_auto_tags

def tags_for_file(file_group):
    if not file_group:
        return []

    tags = ["src-file"]
    file_origins = file_group.files.values_list('file_origin', flat=True).distinct()
    for each_origin in file_origins:
        tags.append(f"src-{each_origin}")

    return tags

def auto_tag_item_from_src(item, url, file_group):
    """
    Shared logic to sync source, subreddit, and user tags for an Item.
    """

    current_tags = list(item.tags.all())

    # Filter out any existing src-, subreddit-, or user- tags
    AUTO_PREFIXES = ("src-", "subreddit-", "user-")
    new_tags_list = [
        tag for tag in current_tags
        if not any(tag.name.startswith(pre) for pre in AUTO_PREFIXES)
    ]

    src_auto_tag_names = set(tags_for_url(url) + tags_for_file(file_group))

    # Get or create and append
    for tag_name in src_auto_tag_names:
        tag_obj, _ = Tag.objects.get_or_create(name=tag_name)
        new_tags_list.append(tag_obj)

    item.tags.set(new_tags_list)
