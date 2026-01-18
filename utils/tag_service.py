from items.models.tag import Tag
from utils.url_refiner import refine_url


def auto_tag_item_from_url(item, url):
    """
    Shared logic to sync source, subreddit, and user tags for an Item.
    """

    refined_url_info = refine_url(url)
    current_tags = list(item.tags.all())

    # Filter out any existing src-, subreddit-, or user- tags
    AUTO_PREFIXES = ("src-", "subreddit-", "user-")
    new_tags_list = [
        tag for tag in current_tags
        if not any(tag.name.startswith(pre) for pre in AUTO_PREFIXES)
    ]

    src_auto_tags = []

    # 1. Site name tag
    site_name = refined_url_info.get('url_site_name')
    if site_name:
        src_auto_tags.append(f"src-{site_name}")

    # 2. Host/User tags
    post_host = refined_url_info.get('post_host')
    post_host_name = refined_url_info.get('post_host_name')

    if post_host == 'r':
        src_auto_tags.append(f"subreddit-{post_host_name}")
    elif post_host and post_host_name:
        src_auto_tags.append(f"{post_host}-{post_host_name}")

    # Get or create and append
    for tag_name in src_auto_tags:
        tag_obj, _ = Tag.objects.get_or_create(name=tag_name)
        new_tags_list.append(tag_obj)

    item.tags.set(new_tags_list)
