from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from items.models.file_group import FileGroup
from utils.g_drive import rename_local_drive_file, rename_drive_file

class File(models.Model):
    file_group = models.ForeignKey(FileGroup, on_delete=models.CASCADE, related_name="files")
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50, blank=True)
    file_origin = models.CharField(max_length=255, blank=True)
    file_url = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.file_name

@receiver(pre_delete, sender=File)
def rename_file_before_delete(sender, instance, **kwargs):
    """
    This runs every time a File record is about to be deleted, 
    including via cascade from Item or FileGroup.
    """
    if instance.file_origin == 'gdrive':
        prefix = "DELETED_"
        new_name = f"{prefix}{instance.file_name}"

        # 1. Try local rename
        rename_status = rename_local_drive_file(instance.file_name, new_name)

        # 2. API Fallback
        if not rename_status and instance.file_url:
            try:
                parts = instance.file_url.rstrip('/').split('/')
                if 'd' in parts:
                    file_id = parts[parts.index('d') + 1]
                    rename_drive_file(file_id, new_name)
            except Exception as e:
                print(f"Signal Rename failed: {e}")
