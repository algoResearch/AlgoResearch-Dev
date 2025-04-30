# myapp/utils/image_tools.py
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
import io

def generate_group_photo(user_images, size=400):
    """
    Create a square group profile image using 2–4 user profile images.
    """
    num_images = min(len(user_images), 4)
    collage_size = (2, 2) if num_images > 1 else (1, 1)
    tile_width = size // collage_size[0]
    tile_height = size // collage_size[1]

    final_image = Image.new('RGB', (size, size), color='#f0f0f0')

    for idx, image_file in enumerate(user_images[:4]):
        try:
            img = Image.open(image_file).convert('RGB')
        except Exception:
            continue

        img = ImageOps.fit(img, (tile_width, tile_height), Image.ANTIALIAS)

        x = (idx % collage_size[0]) * tile_width
        y = (idx // collage_size[0]) * tile_height
        final_image.paste(img, (x, y))

    buffer = io.BytesIO()
    final_image.save(buffer, format='PNG')
    buffer.seek(0)
    return ContentFile(buffer.read(), name='group_photo.png')
