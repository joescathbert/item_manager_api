from django.db import transaction
from .media_extractor import get_media_details
from items.models import MediaURL

def refresh_link_media(link_instance):
    """
    Re-runs extraction for a specific Link instance and updates its MediaURLs.
    """
    details = get_media_details(link_instance.url)
    
    if not details.get("media"):
        return False, "No media found"

    with transaction.atomic():
        # 1. Remove old, incomplete MediaURL records for this link
        link_instance.media_urls.all().delete()
        
        # 2. Create new, enriched records
        to_create = []
        for i, m in enumerate(details["media"]):
            to_create.append(MediaURL(
                link=link_instance,
                url=m["hd_url"], # Keep for legacy
                hd_url=m["hd_url"],
                sd_url=m["sd_url"],
                media_type=m["media_type"],
                order=i
            ))
        MediaURL.objects.bulk_create(to_create)
        
        # 3. Optional: update the parent link's main media_url field to the first HD link
        link_instance.media_url = details["media"][0]["hd_url"]
        link_instance.save()
        
    return True, "Success"
