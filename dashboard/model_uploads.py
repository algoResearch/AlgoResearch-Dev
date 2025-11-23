import uuid
from django.db import models
from django.conf import settings

class UploadSession(models.Model):
    """Tracks a chunked upload until completed."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey("dashboard.Conversation", on_delete=models.CASCADE)
    filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    total_size = models.BigIntegerField()
    part_size = models.IntegerField()  # e.g., 2MB
    total_parts = models.IntegerField()
    received_parts = models.IntegerField(default=0)
    storage_backend = models.CharField(max_length=10, default="local")  # "local" | "s3"
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

class Attachments(models.Model):
    conversation = models.ForeignKey("dashboard.Conversation", on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    file = models.FileField(upload_to="attachments/")
    thumbnail = models.ImageField(upload_to="attachments/thumbs/", null=True, blank=True)
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    size = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)