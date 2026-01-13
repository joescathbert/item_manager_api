from django.db import models
from items.models.item import Item

class Link(models.Model):
    item = models.OneToOneField(Item, on_delete=models.CASCADE, related_name="link")
    url = models.URLField(unique=True)
    media_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return f"Link: {self.url}"

    # --- NEW Method for accessing current media ---
    # This method allows your application code to seamlessly switch 
    # to the new model while the old field still exists.
    @property
    def current_media(self):
        """
        Returns the media from the new MediaURL model, 
        or falls back to the old media_url field if no new ones exist.
        """
        if self.media_urls.exists():
            # Returns a queryset or the primary media object
            return self.media_urls.all() 
        elif self.media_url:
            # For temporary use during migration
            return [{"url": self.media_url, "type": "video"}] 
        return []
