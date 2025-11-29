from django.db import models
from django.core.exceptions import ValidationError
from items.models.item import Item

class FileGroup(models.Model):
    item = models.OneToOneField(Item, on_delete=models.CASCADE, related_name="file_group")
    description = models.TextField(blank=True)

    def clean(self):
        # Ensure item type matches
        if self.item.type != "file_group":
            raise ValidationError("Item type must be 'file_group' to attach a FileGroup.")

    def save(self, *args, **kwargs):
        self.clean()  # enforce validation before saving
        super().save(*args, **kwargs)

    def __str__(self):
        return f"FileGroup for {self.item.name}"
