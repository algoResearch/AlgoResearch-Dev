from PIL import Image, ImageDraw, ImageFont
from django.core.files.base import ContentFile
import io
import math
from typing import List, Optional, Dict, Any  # etc

def generate_group_profile_picture(initial: str = "G", size: int = 200, background_color: str = "#0A58CA") -> ContentFile:
    img = Image.new("RGB", (size, size), color=background_color)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", size=int(size * 0.75))
    except IOError:
        font = ImageFont.load_default()

    text_bbox = draw.textbbox((0, 0), initial, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    text_x = (size - text_width) // 2
    text_y = (size - text_height) // 2

    draw.text((text_x, text_y), initial, font=font, fill="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return ContentFile(buffer.read(), name=f"group_{initial}.png")


def generate_group_initials_picture(initials: List[str], size: int = 400, bg_color: str = "#007bff") -> ContentFile:
    initials = initials[:4]  # Limit to 4 max
    count = len(initials)
    
    grid = (1, 1) if count == 1 else (2, 2)  # 2x2 for 2-4
    tile_w = size // grid[0]
    tile_h = size // grid[1]

    img = Image.new("RGB", (size, size), color=bg_color)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", size=int(tile_w * 0.5))
    except IOError:
        font = ImageFont.load_default()

    for idx, initial in enumerate(initials):
        row = idx // grid[0]
        col = idx % grid[0]
        x = col * tile_w
        y = row * tile_h

        # Center the letter
        text_bbox = draw.textbbox((0, 0), initial, font=font)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        text_x = x + (tile_w - text_w) // 2
        text_y = y + (tile_h - text_h) // 2

        draw.text((text_x, text_y), initial, fill="white", font=font)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return ContentFile(buffer.read(), name="group_initials.png")
