from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps


@dataclass
class MealImageVariant:
    label: str
    image_bytes: bytes
    mime_type: str
    width: int
    height: int


def prepare_meal_image_variants(image_bytes: bytes, mime_type: str) -> list[MealImageVariant]:
    if not mime_type.startswith("image/"):
        return [MealImageVariant("original", image_bytes, mime_type, 0, 0)]

    with Image.open(BytesIO(image_bytes)) as raw_image:
        image = ImageOps.exif_transpose(raw_image).convert("RGB")
        base = _resize_for_analysis(image)
        variants = [_encode_variant(base, label="original")]

        if min(base.size) >= 768:
            variants.append(_encode_variant(_center_crop(base), label="center_crop"))

        if base.height >= int(base.width * 1.2):
            variants.append(_encode_variant(_lower_focus_crop(base), label="lower_focus"))
        elif base.width >= int(base.height * 1.2):
            variants.append(_encode_variant(_middle_focus_crop(base), label="middle_focus"))

    deduped: list[MealImageVariant] = []
    seen_shapes: set[tuple[int, int, int]] = set()
    for variant in variants:
        key = (len(variant.image_bytes), variant.width, variant.height)
        if key in seen_shapes:
            continue
        seen_shapes.add(key)
        deduped.append(variant)
    return deduped


def _resize_for_analysis(image: Image.Image, max_edge: int = 1568) -> Image.Image:
    if max(image.size) <= max_edge:
        return image.copy()
    resized = image.copy()
    resized.thumbnail((max_edge, max_edge))
    return resized


def _center_crop(image: Image.Image) -> Image.Image:
    width, height = image.size
    crop_size = int(min(width, height) * 0.74)
    left = (width - crop_size) // 2
    top = (height - crop_size) // 2
    return image.crop((left, top, left + crop_size, top + crop_size))


def _lower_focus_crop(image: Image.Image) -> Image.Image:
    width, height = image.size
    crop_height = int(height * 0.68)
    top = max(0, height - crop_height)
    left = int(width * 0.1)
    right = int(width * 0.9)
    return image.crop((left, top, right, height))


def _middle_focus_crop(image: Image.Image) -> Image.Image:
    width, height = image.size
    crop_width = int(width * 0.68)
    left = (width - crop_width) // 2
    top = int(height * 0.12)
    bottom = int(height * 0.88)
    return image.crop((left, top, left + crop_width, bottom))


def _encode_variant(image: Image.Image, *, label: str) -> MealImageVariant:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92, optimize=True)
    payload = buffer.getvalue()
    return MealImageVariant(
        label=label,
        image_bytes=payload,
        mime_type="image/jpeg",
        width=image.width,
        height=image.height,
    )
