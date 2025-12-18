from django.db import models
from django.core.exceptions import ValidationError
from items.models.item import Item

class Link(models.Model):
    item = models.OneToOneField(Item, on_delete=models.CASCADE, related_name="link")
    url = models.URLField()
    media_url = models.URLField(blank=True, null=True)

    def clean(self):
        # Ensure item type matches
        if self.item.type != "link":
            raise ValidationError("Item type must be 'link' to attach a Link.")

    def save(self, *args, **kwargs):
        self.clean()  # enforce validation before saving
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Link: {self.url}"
