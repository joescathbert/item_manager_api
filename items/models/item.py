from django.db import models
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

    def __str__(self):
        return f"{self.name} ({self.type})"
