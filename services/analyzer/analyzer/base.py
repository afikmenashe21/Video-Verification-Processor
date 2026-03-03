from __future__ import annotations

import base64
import io

from PIL import Image


def resize_image(img: Image.Image, max_side: int = 512) -> Image.Image:
    w, h = img.size
    if max(w, h) <= max_side:
        return img
    scale = max_side / max(w, h)
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def encode_image_base64(img: Image.Image, max_side: int = 1024) -> str:
    """Resize image and encode to base64 data URI (JPEG)."""
    resized = resize_image(img, max_side=max_side)
    buf = io.BytesIO()
    resized.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def prepare_frames_and_refs(
    frame_images: list[Image.Image],
    ref_images: list[Image.Image],
    max_side: int = 1024,
) -> tuple[list[str], list[str]]:
    """Encode frame images and reference images to base64 data URIs."""
    encoded_frames = [encode_image_base64(img, max_side=max_side) for img in frame_images]
    encoded_refs = [encode_image_base64(img, max_side=max_side) for img in ref_images]
    return encoded_frames, encoded_refs
