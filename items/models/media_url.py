from django.db import models
from items.models.link import Link

class MediaURL(models.Model):
    MEDIA_TYPE_CHOICES = [
        ("video", "Video"),
        ("image", "Image"),
    ]

    # One Link can have multiple MediaURLs
    link = models.ForeignKey(
        Link,
        on_delete=models.CASCADE,
        related_name="media_urls"
    )

    # The actual URL for the media resource
    url = models.URLField()
    hd_url = models.URLField(blank=True, null=True)
    sd_url = models.URLField(blank=True, null=True)

    # The type of media
    media_type = models.CharField(
        max_length=10, 
        choices=MEDIA_TYPE_CHOICES,
        default="video"
    )

    # For sorting or display order
    order = models.PositiveSmallIntegerField(default=0) 

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.link.item.name} - {self.media_type} URL"

