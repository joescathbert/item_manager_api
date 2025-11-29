from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from items.models.tag import Tag

class Item(models.Model):
    TYPE_CHOICES = [
        ("link", "Link"),
        ("file_group", "File Group"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="items"
    )
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    date_of_origin = models.DateField(null=True, blank=True)
    tags = models.ManyToManyField(Tag, related_name="items", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        # If this Item already has a Link, enforce type consistency
        if hasattr(self, "link") and self.type != "link":
            raise ValidationError("Item type must remain 'link' if a Link is attached.")
        # If this Item already has a FileGroup, enforce type consistency
        if hasattr(self, "file_group") and self.type != "file_group":
            raise ValidationError("Item type must remain 'file_group' if a FileGroup is attached.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.type})"
