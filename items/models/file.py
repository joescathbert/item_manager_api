from django.db import models
from items.models.file_group import FileGroup

class File(models.Model):
    file_group = models.ForeignKey(FileGroup, on_delete=models.CASCADE, related_name="files")
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50, blank=True)
    file_origin = models.CharField(max_length=255, blank=True)
    file_url = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.file_name
