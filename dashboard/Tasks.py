from celery import shared_task
from moviepy import VideoFileClip
import os
import mimetypes
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def generate_video_thumbnail(self, message_id):
    """
    Generate a thumbnail from the first frame of a video for a specific message.

    Args:
        message_id (int): The ID of the Message instance.

    Returns:
        str: The URL of the generated thumbnail or an error message.
    """
    from dashboard.models import Message  # Import here to avoid circular imports
    try:
        # Fetch the Message instance
        message = Message.objects.get(id=message_id)

        # Check if a thumbnail already exists
        if message.thumbnail_url:
            logger.info(f"Thumbnail already exists for Message ID {message_id}: {message.thumbnail_url}")
            return message.thumbnail_url

        # Validate the attachment
        if not message.attachment or not os.path.exists(message.attachment.path):
            error_message = f"Attachment not found or invalid for Message ID {message_id}"
            logger.error(error_message)
            return error_message

        # Validate that the attachment is a video
        mime_type, _ = mimetypes.guess_type(message.attachment.path)
        if not mime_type or not mime_type.startswith('video/'):
            error_message = f"Attachment is not a video for Message ID {message_id}"
            logger.error(error_message)
            return error_message

        # Define the thumbnail directory
        output_dir = os.path.join(settings.MEDIA_ROOT, 'thumbnails')
        os.makedirs(output_dir, exist_ok=True)

        # Generate the thumbnail
        thumbnail_name = f"{os.path.splitext(os.path.basename(message.attachment.name))[0]}_thumbnail.jpg"
        thumbnail_path = os.path.join(output_dir, thumbnail_name)

        with VideoFileClip(message.attachment.path) as clip:
            clip.save_frame(thumbnail_path, t=0)  # Capture the first frame

        # Convert the thumbnail path to a URL
        thumbnail_url = os.path.join(settings.MEDIA_URL, 'thumbnails', thumbnail_name)

        # Update the Message instance
        message.thumbnail = thumbnail_name
        message.thumbnail_url = thumbnail_url
        message.save(update_fields=['thumbnail', 'thumbnail_url'])

        logger.info(f"Thumbnail generated successfully for Message ID {message_id}: {thumbnail_url}")
        return thumbnail_url

    except Message.DoesNotExist:
        error_message = f"Message with ID {message_id} does not exist."
        logger.error(error_message)
        return error_message

    except Exception as e:
        # Cleanup partial thumbnail file if exists
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)

        logger.error(f"Unexpected error generating thumbnail for Message ID {message_id}: {e}")
        self.retry(exc=e, countdown=5, max_retries=3)  # Retry logic for transient issues
        return f"Error: {e}"